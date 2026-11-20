"""Probe every sensitive endpoint as every role, straight at the API (no UI involved).
Prints an HTTP status matrix; 2xx = allowed, 401 = unauthenticated, 403 = forbidden."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, seed
from app.api import create_app

ROLES = [("anonymous", None), ("student", "u-stu"), ("faculty", "u-fac"), ("technician", "u-tech"),
         ("dept approver", "u-appr"), ("facility mgr", "u-fm"), ("admin", "u-admin"), ("sensor gw", "sensor-gw")]
PROBES = ["GET restricted facility", "GET other user's ticket", "POST approve booking", "POST ticket transition",
          "POST sensor event", "GET audit log", "POST sync run"]
out = {}
for label, uid in ROLES:
    d = tempfile.mkdtemp(); p = os.path.join(d, "c.db")
    c = db.connect(p); db.migrate(c); seed.seed(c); c.close()
    cl = create_app({"DB_PATH": p, "TESTING": True}).test_client()
    A = {"X-User-Id": "u-stu2"}
    bid = cl.post("/api/bookings", json={"facility_id": 3, "start": "2026-12-02T09:00", "end": "2026-12-02T10:00"}, headers=A).json["id"]
    tid = cl.post("/api/tickets", json={"title": "t", "description": "d", "impact": 2, "urgency": 2}, headers=A).json["id"]
    H = {"X-User-Id": uid} if uid else {}
    codes = [cl.get("/api/facilities/3", headers=H).status_code,
             cl.get(f"/api/tickets/{tid}", headers=H).status_code,
             cl.post(f"/api/bookings/{bid}/approve", headers=H).status_code,
             cl.post(f"/api/tickets/{tid}/transition", json={"to": "assigned"}, headers=H).status_code,
             cl.post("/api/sensor-events", json={"event_id": "e1", "facility_id": 1, "kind": "temperature", "value": 20}, headers=H).status_code,
             cl.get("/api/audit", headers=H).status_code,
             cl.post("/api/sync/run", headers=H).status_code]
    out[label] = codes
json.dump({"probes": PROBES, "matrix": out}, open(sys.argv[1] if len(sys.argv) > 1 else "/dev/stdout", "w"))
w = max(len(p) for p in PROBES)
print(f"{'':{w}} " + " ".join(f"{r[0][:9]:>9}" for r in ROLES))
for i, pr in enumerate(PROBES):
    print(f"{pr:{w}} " + " ".join(f"{out[r[0]][i]:>9}" for r in ROLES))
