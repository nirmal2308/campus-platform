"""Pure business rules. No I/O, so they can be unit tested in isolation."""
from datetime import datetime, timedelta

# --- Planning assumptions (documented in the report, section 1.4) ----------
DEFAULT_MAX_BOOKING_HOURS = 4
SLA_HOURS = {1: 4, 2: 8, 3: 24, 4: 72, 5: 120}
SENSOR_DEFAULT_THRESHOLDS = {"temperature": 30.0, "humidity": 70.0, "power_kw": 50.0}

TICKET_TRANSITIONS = {
    "new": {"assigned"},
    "assigned": {"in_progress"},
    "in_progress": {"resolved"},
    "resolved": {"closed", "in_progress"},  # reopen allowed
    "closed": set(),
}
STAFF_ROLES = {"admin", "facility_manager", "maintenance_technician"}
APPROVER_ROLES = {"admin", "facility_manager", "department_approver", "faculty"}


class RuleError(ValueError):
    """Raised when a business rule rejects an input."""


def parse_dt(value):
    if not value:
        raise RuleError("missing datetime")
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise RuleError(f"invalid datetime: {value!r}")


def validate_booking_window(start, end, max_hours=DEFAULT_MAX_BOOKING_HOURS):
    s, e = parse_dt(start), parse_dt(end)
    if e <= s:
        raise RuleError("end must be after start")
    if (e - s) > timedelta(hours=max_hours):
        raise RuleError(f"duration exceeds {max_hours} hours")
    return s, e


def intervals_overlap(a_start, a_end, b_start, b_end):
    """Half-open intervals [start, end): back-to-back bookings do NOT overlap."""
    return b_start <= a_start < b_end


def priority_from(impact, urgency):
    """ITIL-style matrix. impact/urgency: 1 (high) .. 3 (low). Returns P1..P5."""
    for name, v in (("impact", impact), ("urgency", urgency)):
        if not isinstance(v, int) or isinstance(v, bool) or v not in (1, 2, 3):
            raise RuleError(f"{name} must be 1, 2 or 3")
    return impact + urgency - 1


def sla_deadline(created_at, priority):
    if priority not in SLA_HOURS:
        raise RuleError("unknown priority")
    return created_at + timedelta(hours=SLA_HOURS[priority])


def sla_breached(created_at, priority, resolved_at):
    """Resolving exactly at the deadline is NOT a breach."""
    return resolved_at > sla_deadline(created_at, priority)


def sensor_alert(kind, value, thresholds=None):
    t = (thresholds or SENSOR_DEFAULT_THRESHOLDS)
    if kind not in t:
        raise RuleError(f"unknown sensor kind: {kind}")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RuleError("sensor value must be numeric")
    return value > t[kind]


def can_transition(current, target):
    return target in TICKET_TRANSITIONS.get(current, set())


def can_approve(role):
    return role in APPROVER_ROLES
