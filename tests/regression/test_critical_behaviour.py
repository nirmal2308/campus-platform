"""Regression tests (R01-R06): behaviour that was correct in release 1.0.0 and must stay correct."""
from datetime import timedelta

import pytest

from tests.conftest import Client, rows

pytestmark = pytest.mark.regression


@pytest.fixture(params=[1], ids=["schema1"])
def rapi(request, make_app):
    app = make_app(request.param)
    c = Client(app.test_client())
    c.app = app
    return c


def test_r01_back_to_back_bookings_are_both_accepted(rapi):
    a = rapi.post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"})
    b = rapi.post("/api/bookings", "u-stu2", {"facility_id": 1, "start": "2026-12-02T10:00", "end": "2026-12-02T11:00"})
    assert a.status_code == 201 and b.status_code == 201


def test_r02_booking_of_exactly_maximum_duration_is_still_accepted(rapi):
    r = rapi.post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T13:00"})
    assert r.status_code == 201


def test_r03_resolving_exactly_at_sla_deadline_is_not_a_breach(make_app, clock):
    app = make_app(1)
    api = Client(app.test_client())
    t = api.post("/api/tickets", "u-stu", {"title": "Leak", "description": "Block B", "impact": 1, "urgency": 1}).json
    for state in ("assigned", "in_progress"):
        assert api.post(f"/api/tickets/{t['id']}/transition", "u-tech", {"to": state}).status_code == 200
    clock["now"] = clock["now"] + timedelta(hours=4)  # P1 SLA = 4 h exactly
    r = api.post(f"/api/tickets/{t['id']}/transition", "u-tech", {"to": "resolved"})
    assert r.json["sla_breached"] is False


def test_r04_closed_ticket_can_never_be_reopened(rapi):
    t = rapi.post("/api/tickets", "u-stu", {"title": "x", "description": "y", "impact": 3, "urgency": 3}).json["id"]
    for state in ("assigned", "in_progress", "resolved", "closed"):
        assert rapi.post(f"/api/tickets/{t}/transition", "u-tech", {"to": state}).status_code == 200
    assert rapi.post(f"/api/tickets/{t}/transition", "u-tech", {"to": "in_progress"}).status_code == 409


def test_r05_audit_history_is_retained_after_approval(rapi):
    bid = rapi.post("/api/bookings", "u-stu", {"facility_id": 3, "start": "2026-12-03T09:00", "end": "2026-12-03T10:00"}).json["id"]
    rapi.post(f"/api/bookings/{bid}/approve", "u-appr")
    actions = [r["action"] for r in rows(rapi.app, "SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["booking.create", "booking.approve"]


def test_r06_priority_p1_for_high_impact_high_urgency_ticket(rapi):
    r = rapi.post("/api/tickets", "u-stu", {"title": "Fire alarm", "description": "Lab", "impact": 1, "urgency": 1})
    assert r.json["priority"] == 1
