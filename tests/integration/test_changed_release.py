"""Q6 - adapted checks for release 2.0.0 (campus policies, revised booking API,
migration 002, intermittent synchronisation). Codes C01-C08."""
import os
import shutil
import sqlite3

import pytest

from app import db
from tests.conftest import Client, rows

pytestmark = pytest.mark.integration
MIG = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")


def v2(start, end, fid=1):
    return {"facility_id": fid, "start_time": start, "end_time": end}


def test_c01_migration_preserves_existing_bookings_tickets_and_audit(make_app):
    app = make_app(1)
    api = Client(app.test_client())
    api.post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"})
    api.post("/api/tickets", "u-stu", {"title": "t", "description": "d", "impact": 2, "urgency": 2})
    before = {t: rows(app, f"SELECT * FROM {t} ORDER BY id") for t in ("bookings", "tickets", "audit_log")}
    c = db.connect(app.db_path)
    assert db.migrate(c) == 2
    c.close()
    for table, old in before.items():
        new = rows(app, f"SELECT * FROM {table} ORDER BY id")
        assert len(new) == len(old)
        for o, n in zip(old, new):
            assert all(n[k] == v for k, v in o.items())  # every original column unchanged
    assert rows(app, "SELECT calendar_sync FROM bookings")[0]["calendar_sync"] == "not_required"


@pytest.mark.parametrize("fid,end,code", [(3, "2026-12-02T12:00", 201),   # lab: exactly 3 h
                                          (3, "2026-12-02T12:01", 422),   # lab: 3 h 1 min
                                          (2, "2026-12-02T15:00", 201),   # hall: 6 h
                                          (4, "2026-12-02T11:01", 422)])  # meeting room: 2 h 1 min
def test_c02_campus_specific_duration_limits_by_facility_type(api2, fid, end, code):
    start = "2026-12-02T09:00" if fid != 4 else "2026-12-02T09:00"
    r = api2.post("/api/v2/bookings", "u-stu", v2(start, end, fid))
    assert r.status_code == code


def test_c03_legacy_v1_booking_endpoint_still_works_after_migration(api2):
    r = api2.post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"})
    assert r.status_code == 201


def test_c04_v2_api_requires_new_field_names(api2):
    assert api2.post("/api/v2/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}).status_code == 400


def test_c05_campus_sensor_threshold_is_28_degrees(api2):
    ev = {"event_id": "a", "facility_id": 1, "kind": "temperature", "value": 28.0}
    assert api2.post("/api/sensor-events", "sensor-gw", ev).json["alert"] is True
    assert api2.post("/api/sensor-events", "sensor-gw", {**ev, "event_id": "b", "value": 27.9}).json["alert"] is False


def test_c06_calendar_outage_keeps_booking_and_retries_to_dead_letter(make_app):
    def down(*a):
        raise ConnectionError("calendar unavailable")
    app = make_app(2, transport=down)
    api = Client(app.test_client())
    bid = api.post("/api/v2/bookings", "u-stu", v2("2026-12-02T09:00", "2026-12-02T10:00")).json["id"]
    assert rows(app, "SELECT calendar_sync FROM bookings WHERE id=?", (bid,))[0]["calendar_sync"] == "pending"
    for _ in range(5):
        api.post("/api/sync/run", "u-admin")
    ob = rows(app, "SELECT status, attempts FROM sync_outbox")[0]
    assert ob == {"status": "dead", "attempts": 5}
    assert rows(app, "SELECT status FROM bookings WHERE id=?", (bid,))[0]["status"] == "confirmed"


def test_c07_rollback_script_restores_schema_1_without_data_loss(make_app):
    app = make_app(2)
    api = Client(app.test_client())
    api.post("/api/v2/bookings", "u-stu", v2("2026-12-02T09:00", "2026-12-02T10:00"))
    c = db.connect(app.db_path)
    c.executescript(open(os.path.join(MIG, "002_rollback.sql")).read())
    c.close()
    assert rows(app, "SELECT version FROM schema_version")[0]["version"] == 1
    assert len(rows(app, "SELECT * FROM bookings")) == 1
    assert Client(app.test_client()).get("/health").json["schema"] == 1


def test_c08_failed_migration_leaves_previous_version_and_data_intact(tmp_path, make_app):
    app = make_app(1)
    Client(app.test_client()).post("/api/bookings", "u-stu", {"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"})
    bad = tmp_path / "mig"
    bad.mkdir()
    shutil.copy(os.path.join(MIG, "001_initial.sql"), bad)
    (bad / "002_broken.sql").write_text("CREATE TABLE ok_table (x INTEGER);\nALTER TABLE no_such_table ADD COLUMN y TEXT;\n")
    c = db.connect(app.db_path)
    with pytest.raises(sqlite3.Error):
        db.migrate(c, migrations_dir=str(bad))
    assert db.current_version(c) == 1
    assert c.execute("SELECT name FROM sqlite_master WHERE name='ok_table'").fetchone() is None  # fully rolled back
    assert c.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1
    c.close()
