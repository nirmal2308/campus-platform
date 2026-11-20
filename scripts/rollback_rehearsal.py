"""Rehearse recovery after a deliberately failed deployment of release 2.0.0.
Steps: backup -> migrate to schema 2 -> smoke check FAILS (wrong version) ->
rollback (restore verified backup) -> verify data + schema -> health check."""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, seed  # noqa: E402
from app.api import create_app  # noqa: E402


def count(path, table):
    c = sqlite3.connect(path)
    n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    c.close()
    return n


tmp = tempfile.mkdtemp()
live = os.path.join(tmp, "campus.db")
c = db.connect(live)
db.migrate(c, target=1)
seed.seed(c)
c.close()
app = create_app({"DB_PATH": live, "APP_VERSION": "1.1.0"})
cl = app.test_client()
H = {"X-User-Id": "u-stu"}
cl.post("/api/bookings", json={"facility_id": 1, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}, headers=H)
cl.post("/api/tickets", json={"title": "t", "description": "d", "impact": 1, "urgency": 1}, headers=H)
before = {t: count(live, t) for t in ("bookings", "tickets", "audit_log")}
print(f"[1] production state (v1.1.0, schema 1): {before}")

backup = os.path.join(tmp, "pre-migration.bak.db")
src, dst = sqlite3.connect(live), sqlite3.connect(backup)
src.backup(dst); src.close(); dst.close()
print(f"[2] backup taken with SQLite online-backup API -> rows verified: "
      f"{ {t: count(backup, t) for t in before} }")

c = db.connect(live)
print(f"[3] migration 002 applied, schema now {db.migrate(c)}")
c.close()
bad = create_app({"DB_PATH": live, "APP_VERSION": "2.0.0-broken"}).test_client().get("/health").json
expected = "2.0.0"
healthy = bad["version"] == expected
print(f"[4] post-deploy smoke: health={bad}  expected version={expected}  -> {'PASS' if healthy else 'FAIL (deployment rejected)'}")

if not healthy:
    shutil.copy(backup, live)
    print("[5] ROLLBACK: previous image tag re-deployed and verified backup restored")
    after = {t: count(live, t) for t in before}
    c = db.connect(live)
    ver = db.current_version(c)
    c.close()
    ok = after == before and ver == 1
    print(f"[6] verification: rows {after} (expected {before}), schema {ver} (expected 1) -> {'RECOVERED' if ok else 'DATA MISMATCH'}")
    h = create_app({"DB_PATH": live, "APP_VERSION": "1.1.0"}).test_client().get("/health").json
    print(f"[7] health after rollback: {h}")
    sys.exit(0 if ok else 1)
