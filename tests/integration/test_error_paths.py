"""Error-path tests (E01-E10) added after the first coverage gate failure (88% < 90%)."""
import pytest

from tests.conftest import Client

pytestmark = pytest.mark.integration
OK = {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}


def test_e01_health_reports_version_and_schema(api):
    assert api.get("/health").json["schema"] == 1


def test_e02_booking_for_unknown_facility_is_404_and_bad_window_is_422(api):
    assert api.post("/api/bookings", "u-stu", {**OK, "facility_id": 99}).status_code == 404
    assert api.post("/api/bookings", "u-stu", {**OK, "end": "2026-12-02T08:00"}).status_code == 422
    assert api.post("/api/bookings", "u-stu", {**OK, "end": "2026-12-02T14:00"}).status_code == 422  # 5 h > 4 h


def test_e03_unknown_booking_ticket_facility_return_404(api):
    assert api.get("/api/bookings/999", "u-admin").status_code == 404
    assert api.get("/api/tickets/999", "u-admin").status_code == 404
    assert api.get("/api/facilities/999", "u-admin").status_code == 404
    assert api.post("/api/bookings/999/approve", "u-appr").status_code == 404
    assert api.post("/api/tickets/999/transition", "u-tech", {"to": "assigned"}).status_code == 404


def test_e04_approving_a_confirmed_booking_is_a_409(api):
    bid = api.post("/api/bookings", "u-stu", OK).json["id"]  # classroom -> already confirmed
    assert api.post(f"/api/bookings/{bid}/approve", "u-appr").status_code == 409


def test_e05_invalid_ticket_priority_inputs_are_422(api):
    bad = {"title": "t", "description": "d", "impact": 7, "urgency": 1}
    assert api.post("/api/tickets", "u-stu", bad).status_code == 422


def test_e06_illegal_ticket_transition_is_409(api):
    tid = api.post("/api/tickets", "u-stu", {"title": "t", "description": "d", "impact": 2, "urgency": 2}).json["id"]
    assert api.post(f"/api/tickets/{tid}/transition", "u-tech", {"to": "closed"}).status_code == 409


def test_e07_sensor_event_validation(api):
    assert api.post("/api/sensor-events", "sensor-gw", {"event_id": "x"}).status_code == 400
    bad = {"event_id": "y", "facility_id": 1, "kind": "radiation", "value": 1}
    assert api.post("/api/sensor-events", "sensor-gw", bad).status_code == 422


def test_e08_unauthenticated_calls_rejected_on_every_write_endpoint(api):
    for method, url in [("post", "/api/bookings"), ("post", "/api/tickets"), ("post", "/api/sensor-events"),
                        ("post", "/api/bookings/1/approve"), ("post", "/api/tickets/1/transition"),
                        ("get", "/api/bookings/1"), ("get", "/api/tickets/1"), ("get", "/api/facilities/1"),
                        ("get", "/api/audit"), ("post", "/api/sync/run"), ("post", "/api/v2/bookings")]:
        assert getattr(api, method)(url).status_code == 401, url



def test_e10_sync_transport_without_url_vs_with_url(monkeypatch):
    from app import sync
    assert sync.default_transport("ticket", 5, "k") == "EXT-TICKET-5"
    monkeypatch.setenv("CAMPUS_SYNC_URL", "https://tracker.invalid")
    with pytest.raises(ConnectionError):
        sync.default_transport("ticket", 5, "k")
