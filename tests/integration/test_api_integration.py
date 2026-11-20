"""Integration tests (I01-I06): real Flask app + real SQLite file per test."""
import pytest

from tests.conftest import rows

pytestmark = pytest.mark.integration
BOOK = {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T11:00"}


def test_i01_confirmed_booking_is_persisted_and_audited(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    r = api.post("/api/bookings", "u-stu", BOOK)
    assert r.status_code == 201 and r.json["status"] == "confirmed"
    assert len(rows(app, "SELECT * FROM bookings")) == 1
    audit = rows(app, "SELECT * FROM audit_log WHERE action='booking.create'")
    assert len(audit) == 1 and audit[0]["actor"] == "u-stu"


def test_i02_overlapping_booking_rejected_and_not_stored(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    assert api.post("/api/bookings", "u-stu", BOOK).status_code == 201
    clash = {"facility_id": 1, "start": "2026-12-02T08:00", "end": "2026-12-02T09:30"}
    r = api.post("/api/bookings", "u-stu2", clash)
    assert r.status_code == 409
    assert len(rows(app, "SELECT * FROM bookings")) == 1


def test_i03_restricted_lab_needs_approval_by_permitted_role(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    r = api.post("/api/bookings", "u-stu", {"facility_id": 3, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"})
    assert r.status_code == 201 and r.json["status"] == "pending_approval"
    bid = r.json["id"]
    assert api.post(f"/api/bookings/{bid}/approve", "u-stu").status_code == 403
    assert api.post(f"/api/bookings/{bid}/approve", "u-fac").status_code == 403
    ok = api.post(f"/api/bookings/{bid}/approve", "u-appr")
    assert ok.status_code == 200
    assert rows(app, "SELECT status, approved_by FROM bookings WHERE id=?", (bid,))[0] == \
        {"status": "confirmed", "approved_by": "u-appr"}


def test_i04_retried_ticket_submission_creates_exactly_one_ticket(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    body = {"title": "Projector dead", "description": "Room A101", "impact": 2, "urgency": 2}
    h = {"Idempotency-Key": "retry-123"}
    first = api.post("/api/tickets", "u-stu", body, headers=h)
    second = api.post("/api/tickets", "u-stu", body, headers=h)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json["id"] == second.json["id"] and second.json["duplicate"] is True
    assert len(rows(app, "SELECT * FROM tickets")) == 1


def test_i05_sensor_boundary_creates_ticket_and_duplicate_event_is_ignored(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    ev = {"event_id": "e-1", "facility_id": 1, "kind": "temperature", "value": 30.0}
    r1 = api.post("/api/sensor-events", "sensor-gw", ev)
    assert r1.status_code == 201 and r1.json["alert"] is True and r1.json["ticket_id"]
    r2 = api.post("/api/sensor-events", "sensor-gw", ev)  # gateway retry
    assert r2.status_code == 200 and r2.json["duplicate"] is True
    assert len(rows(app, "SELECT * FROM tickets")) == 1
    below = api.post("/api/sensor-events", "sensor-gw", {**ev, "event_id": "e-2", "value": 29.9})
    assert below.json["alert"] is False and len(rows(app, "SELECT * FROM tickets")) == 1


def test_i06_missing_booking_or_ticket_details_return_400_and_store_nothing(make_app):
    app = make_app(1)
    from tests.conftest import Client
    api = Client(app.test_client())
    assert api.post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00"}).status_code == 400
    assert api.post("/api/tickets", "u-stu", {"title": "x", "impact": 1, "urgency": 1}).status_code == 400
    assert rows(app, "SELECT * FROM bookings") == [] and rows(app, "SELECT * FROM tickets") == []
