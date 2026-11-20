"""Unit tests (U01-U16): pure business rules, no database, no HTTP."""
from datetime import datetime, timedelta

import pytest

from app import rules

pytestmark = pytest.mark.unit
T0 = datetime(2026, 12, 1, 9, 0)


def test_u01_valid_booking_window_is_accepted():
    s, e = rules.validate_booking_window("2026-12-01T09:00", "2026-12-01T10:30")
    assert e - s == timedelta(minutes=90)


@pytest.mark.parametrize("start,end", [("2026-12-01T10:00", "2026-12-01T09:00"),
                                       ("2026-12-01T10:00", "2026-12-01T10:00")])
def test_u02_end_not_after_start_is_rejected(start, end):
    with pytest.raises(rules.RuleError):
        rules.validate_booking_window(start, end)


def test_u03_duration_exactly_at_maximum_is_accepted():
    rules.validate_booking_window("2026-12-01T09:00", "2026-12-01T13:00")  # 4 h


def test_u04_one_minute_over_maximum_is_rejected():
    with pytest.raises(rules.RuleError):
        rules.validate_booking_window("2026-12-01T09:00", "2026-12-01T13:01")


@pytest.mark.parametrize("bad", [None, "", "tomorrow", "2026-13-45T99:00"])
def test_u05_missing_or_malformed_datetime_is_rejected(bad):
    with pytest.raises(rules.RuleError):
        rules.validate_booking_window(bad, "2026-12-01T10:00")


def test_u06_back_to_back_intervals_do_not_overlap():
    assert not rules.intervals_overlap(T0, T0 + timedelta(hours=1), T0 + timedelta(hours=1), T0 + timedelta(hours=2))


def test_u07_new_booking_starting_earlier_but_ending_inside_overlaps():
    # existing 10:00-12:00, new 09:00-10:30
    assert rules.intervals_overlap(T0, T0 + timedelta(minutes=90), T0 + timedelta(hours=1), T0 + timedelta(hours=3))


def test_u08_new_booking_fully_containing_existing_overlaps():
    assert rules.intervals_overlap(T0, T0 + timedelta(hours=4), T0 + timedelta(hours=1), T0 + timedelta(hours=2))


@pytest.mark.parametrize("impact,urgency,expected",
                         [(1, 1, 1), (1, 2, 2), (2, 1, 2), (2, 2, 3), (1, 3, 3), (3, 1, 3), (2, 3, 4), (3, 3, 5)])
def test_u09_priority_matrix(impact, urgency, expected):
    assert rules.priority_from(impact, urgency) == expected


@pytest.mark.parametrize("impact,urgency", [(0, 1), (4, 1), (1, 0), (1, 4), (None, 1), (1, "high"), (True, 1)])
def test_u10_invalid_impact_or_urgency_rejected(impact, urgency):
    with pytest.raises(rules.RuleError):
        rules.priority_from(impact, urgency)


@pytest.mark.parametrize("priority,hours", [(1, 4), (2, 8), (3, 24), (4, 72), (5, 120)])
def test_u11_sla_deadline_per_priority(priority, hours):
    assert rules.sla_deadline(T0, priority) == T0 + timedelta(hours=hours)


def test_u12_sla_boundary_at_deadline_is_not_a_breach_one_second_later_is():
    dl = rules.sla_deadline(T0, 1)
    assert rules.sla_breached(T0, 1, dl) is False
    assert rules.sla_breached(T0, 1, dl + timedelta(seconds=1)) is True


def test_u13_sensor_value_equal_to_threshold_raises_alert():
    assert rules.sensor_alert("temperature", 30.0) is True
    assert rules.sensor_alert("temperature", 29.99) is False


def test_u14_sensor_unknown_kind_or_non_numeric_value_rejected():
    with pytest.raises(rules.RuleError):
        rules.sensor_alert("radiation", 1)
    with pytest.raises(rules.RuleError):
        rules.sensor_alert("temperature", "hot")


@pytest.mark.parametrize("cur,to,ok", [("new", "assigned", True), ("assigned", "in_progress", True),
                                       ("in_progress", "resolved", True), ("resolved", "closed", True),
                                       ("resolved", "in_progress", True), ("new", "closed", False),
                                       ("closed", "in_progress", False), ("assigned", "resolved", False)])
def test_u15_ticket_state_machine(cur, to, ok):
    assert rules.can_transition(cur, to) is ok


@pytest.mark.parametrize("role,ok", [("admin", True), ("facility_manager", True), ("department_approver", True),
                                     ("faculty", False), ("student", False), ("maintenance_technician", False)])
def test_u16_only_approver_roles_may_approve(role, ok):
    assert rules.can_approve(role) is ok
