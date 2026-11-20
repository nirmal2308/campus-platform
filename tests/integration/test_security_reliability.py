"""Security and reliability checks (S01-S09) exercised directly against the API,
independently of any user-interface control."""
import pytest

from tests.conftest import Client, rows

pytestmark = [pytest.mark.integration, pytest.mark.security]
BOOK = {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}
TICKET = {"title": "Door jammed", "description": "Block C", "impact": 2, "urgency": 2}


def test_s01_student_cannot_read_restricted_facility(api):
    assert api.get("/api/facilities/3", "u-stu").status_code == 403
    names = [f["name"] for f in api.get("/api/facilities", "u-stu").json]
    assert "Chemistry Lab" not in names
    assert api.get("/api/facilities/3", "u-appr").status_code == 200


def test_s02_student_cannot_read_another_users_ticket_or_booking(api):
    tid = api.post("/api/tickets", "u-stu", TICKET).json["id"]
    bid = api.post("/api/bookings", "u-stu", BOOK).json["id"]
    assert api.get(f"/api/tickets/{tid}", "u-stu2").status_code == 403
    assert api.get(f"/api/bookings/{bid}", "u-stu2").status_code == 403
    assert api.get(f"/api/tickets/{tid}", "u-stu").status_code == 200


def test_s03_role_header_cannot_be_used_to_impersonate_another_role(api):
    bid = api.post("/api/bookings", "u-stu", {"facility_id": 3, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}).json["id"]
    spoof = {"X-Role": "admin", "X-User-Role": "admin"}
    assert api.post(f"/api/bookings/{bid}/approve", "u-stu", headers=spoof).status_code == 403
    assert api.get("/api/audit", "u-stu", headers=spoof).status_code == 403


def test_s04_unauthenticated_and_unknown_callers_get_401(api):
    assert api.get("/api/facilities").status_code == 401
    assert api.get("/api/facilities", "ghost").status_code == 401
    assert api.get("/api/facilities", "' OR 1=1 --").status_code == 401


def test_s05_student_cannot_change_ticket_state_or_inject_sensor_events(api):
    tid = api.post("/api/tickets", "u-stu", TICKET).json["id"]
    assert api.post(f"/api/tickets/{tid}/transition", "u-stu", {"to": "assigned"}).status_code == 403
    ev = {"event_id": "x", "facility_id": 1, "kind": "temperature", "value": 99}
    assert api.post("/api/sensor-events", "u-stu", ev).status_code == 403


def test_s06_hostile_text_is_stored_as_data_not_executed(make_app):
    app = make_app(1)
    api = Client(app.test_client())
    evil = "x'); DROP TABLE tickets;--"
    assert api.post("/api/tickets", "u-stu", {**TICKET, "title": evil}).status_code == 201
    assert rows(app, "SELECT title FROM tickets")[0]["title"] == evil


def test_s07_double_submit_of_same_booking_stores_one_row(make_app):
    app = make_app(1)
    api = Client(app.test_client())
    codes = [api.post("/api/bookings", "u-stu", BOOK).status_code for _ in range(3)]
    assert codes == [201, 409, 409]
    assert len(rows(app, "SELECT * FROM bookings")) == 1



def test_s09_audit_log_readable_only_by_admin(api):
    api.post("/api/tickets", "u-stu", TICKET)
    assert api.get("/api/audit", "u-fm").status_code == 403
    assert len(api.get("/api/audit", "u-admin").json) == 1
