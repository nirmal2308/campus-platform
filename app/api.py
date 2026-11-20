import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request, g

from . import db, rules, sync

RESTRICTED_VIEW_ROLES = {"admin", "facility_manager", "department_approver", "maintenance_technician"}


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DB_PATH=os.environ.get("CAMPUS_DB_PATH", "campus.db"),
        APP_VERSION=os.environ.get("APP_VERSION", "dev"),
        CLOCK=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        SYNC_TRANSPORT=sync.default_transport,
    )
    app.config.update(config or {})

    def conn():
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close(_):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    def err(msg, code):
        return jsonify({"error": msg}), code

    def current_user():
        """Role is ALWAYS read from the database, never from a client header, so a
        caller cannot impersonate a different role by sending X-Role."""
        uid = request.headers.get("X-User-Id")
        if not uid:
            return None
        row = conn().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

    def schema():
        return db.current_version(conn())

    def max_hours_for(kind):
        if schema() >= 2:
            r = conn().execute("SELECT max_hours FROM booking_policies WHERE kind=?", (kind,)).fetchone()
            if r:
                return r[0]
        return rules.DEFAULT_MAX_BOOKING_HOURS

    def thresholds():
        if schema() >= 2:
            return {r["kind"]: r["threshold"] for r in conn().execute("SELECT * FROM sensor_thresholds")}
        return rules.SENSOR_DEFAULT_THRESHOLDS

    def enqueue(entity, eid):
        if schema() >= 2:
            sync.enqueue(conn(), entity, eid)

    # ---------------------------------------------------------------- health
    @app.get("/health")
    def health():
        return jsonify(status="ok", version=app.config["APP_VERSION"], schema=schema())

    # ------------------------------------------------------------ facilities
    @app.get("/api/facilities")
    def list_facilities():
        u = current_user()
        if not u:
            return err("authentication required", 401)
        q = "SELECT * FROM facilities" if u["role"] in RESTRICTED_VIEW_ROLES \
            else "SELECT * FROM facilities WHERE restricted=0"
        return jsonify([dict(r) for r in conn().execute(q)])

    @app.get("/api/facilities/<int:fid>")
    def get_facility(fid):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        f = conn().execute("SELECT * FROM facilities WHERE id=?", (fid,)).fetchone()
        if not f:
            return err("facility not found", 404)
        if f["restricted"] and u["role"] not in RESTRICTED_VIEW_ROLES:
            return err("forbidden", 403)
        return jsonify(dict(f))

    # -------------------------------------------------------------- bookings
    def create_booking(start_key, end_key):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        d = request.get_json(silent=True) or {}
        if not d.get("facility_id") or not d.get(start_key) or not d.get(end_key):
            return err(f"facility_id, {start_key} and {end_key} are required", 400)
        c = conn()
        f = c.execute("SELECT * FROM facilities WHERE id=?", (d["facility_id"],)).fetchone()
        if not f:
            return err("facility not found", 404)
        try:
            s, e = rules.validate_booking_window(d[start_key], d[end_key], max_hours_for(f["kind"]))
        except rules.RuleError as exc:
            return err(str(exc), 422)
        c.execute("BEGIN IMMEDIATE")
        try:
            for row in c.execute(
                    "SELECT start_time, end_time FROM bookings WHERE facility_id=? "
                    "AND status IN ('confirmed','pending_approval')", (f["id"],)).fetchall():
                if rules.intervals_overlap(s, e, datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1])):
                    c.rollback()
                    return err("booking overlaps an existing reservation", 409)
            status = "pending_approval" if f["restricted"] else "confirmed"
            cur = c.execute(
                "INSERT INTO bookings(facility_id,user_id,start_time,end_time,status) VALUES (?,?,?,?,?)",
                (f["id"], u["id"], s.isoformat(), e.isoformat(), status))
            bid = cur.lastrowid
            db.audit(c, u["id"], "booking.create", "booking", bid, status)
            enqueue("booking", bid)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return jsonify(id=bid, status=status, start=s.isoformat(), end=e.isoformat()), 201

    @app.post("/api/bookings")
    def booking_v1():
        return create_booking("start", "end")

    @app.post("/api/v2/bookings")
    def booking_v2():
        return create_booking("start_time", "end_time")

    @app.get("/api/bookings/<int:bid>")
    def get_booking(bid):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        b = conn().execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if not b:
            return err("booking not found", 404)
        if b["user_id"] != u["id"] and u["role"] not in RESTRICTED_VIEW_ROLES:
            return err("forbidden", 403)
        return jsonify(dict(b))

    @app.post("/api/bookings/<int:bid>/approve")
    def approve(bid):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        if not rules.can_approve(u["role"]):
            return err("role not permitted to approve", 403)
        c = conn()
        b = c.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if not b:
            return err("booking not found", 404)
        if b["status"] != "pending_approval":
            return err("booking is not awaiting approval", 409)
        c.execute("UPDATE bookings SET status='confirmed', approved_by=? WHERE id=?", (u["id"], bid))
        db.audit(c, u["id"], "booking.approve", "booking", bid)
        c.commit()
        return jsonify(id=bid, status="confirmed", approved_by=u["id"])

    # --------------------------------------------------------------- tickets
    def new_ticket(c, reporter, title, desc, impact, urgency, idem=None):
        pr = rules.priority_from(impact, urgency)
        now = app.config["CLOCK"]()
        dl = rules.sla_deadline(now, pr)
        cur = c.execute(
            "INSERT INTO tickets(title,description,reporter_id,impact,urgency,priority,status,"
            "created_at,sla_deadline,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (title, desc, reporter, impact, urgency, pr, "new", now.isoformat(), dl.isoformat(), idem))
        tid = cur.lastrowid
        db.audit(c, reporter, "ticket.create", "ticket", tid, f"P{pr}")
        enqueue("ticket", tid)
        return tid, pr, dl

    @app.post("/api/tickets")
    def create_ticket():
        u = current_user()
        if not u:
            return err("authentication required", 401)
        d = request.get_json(silent=True) or {}
        if not all(d.get(k) not in (None, "") for k in ("title", "description", "impact", "urgency")):
            return err("title, description, impact and urgency are required", 400)
        c = conn()
        idem = request.headers.get("Idempotency-Key")
        if idem:
            ex = c.execute("SELECT id, priority FROM tickets WHERE idempotency_key=?", (idem,)).fetchone()
            if ex:
                return jsonify(id=ex["id"], priority=ex["priority"], duplicate=True), 200
        try:
            tid, pr, dl = new_ticket(c, u["id"], d["title"], d["description"], d["impact"], d["urgency"], idem)
        except rules.RuleError as exc:
            return err(str(exc), 422)
        c.commit()
        return jsonify(id=tid, priority=pr, sla_deadline=dl.isoformat(), status="new"), 201

    @app.get("/api/tickets/<int:tid>")
    def get_ticket(tid):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        t = conn().execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not t:
            return err("ticket not found", 404)
        if t["reporter_id"] != u["id"] and u["role"] not in rules.STAFF_ROLES | {"department_approver"}:
            return err("forbidden", 403)
        return jsonify(dict(t))

    @app.post("/api/tickets/<int:tid>/transition")
    def transition(tid):
        u = current_user()
        if not u:
            return err("authentication required", 401)
        if u["role"] not in rules.STAFF_ROLES:
            return err("role not permitted to change ticket state", 403)
        target = (request.get_json(silent=True) or {}).get("to")
        c = conn()
        t = c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not t:
            return err("ticket not found", 404)
        if not rules.can_transition(t["status"], target):
            return err(f"illegal transition {t['status']} -> {target}", 409)
        now = app.config["CLOCK"]() if target == "resolved" else None
        c.execute("UPDATE tickets SET status=?, resolved_at=COALESCE(?, resolved_at) WHERE id=?",
                  (target, now.isoformat() if now else None, tid))
        db.audit(c, u["id"], "ticket.transition", "ticket", tid, f"{t['status']}->{target}")
        c.commit()
        out = {"id": tid, "status": target}
        if now:
            out["sla_breached"] = rules.sla_breached(datetime.fromisoformat(t["created_at"]), t["priority"], now)
        return jsonify(out)

    # --------------------------------------------------------------- sensors
    @app.post("/api/sensor-events")
    def sensor_event():
        u = current_user()
        if not u:
            return err("authentication required", 401)
        if u["role"] not in {"sensor", "admin", "maintenance_technician"}:
            return err("role not permitted to submit sensor events", 403)
        d = request.get_json(silent=True) or {}
        if not all(k in d for k in ("event_id", "facility_id", "kind", "value")):
            return err("event_id, facility_id, kind and value are required", 400)
        c = conn()
        if c.execute("SELECT 1 FROM sensor_events WHERE event_id=?", (d["event_id"],)).fetchone():
            return jsonify(duplicate=True), 200
        try:
            alert = rules.sensor_alert(d["kind"], d["value"], thresholds())
        except rules.RuleError as exc:
            return err(str(exc), 422)
        tid = None
        if alert:
            tid, _, _ = new_ticket(c, "system", f"Sensor alert: {d['kind']}={d['value']}",
                                   f"Facility {d['facility_id']} exceeded threshold", 2, 1)
        c.execute("INSERT INTO sensor_events VALUES (?,?,?,?,?,?)",
                  (d["event_id"], d["facility_id"], d["kind"], d["value"], int(alert), tid))
        c.commit()
        return jsonify(alert=alert, ticket_id=tid), 201

    # ----------------------------------------------------------- audit, sync
    @app.get("/api/audit")
    def audit_log():
        u = current_user()
        if not u:
            return err("authentication required", 401)
        if u["role"] != "admin":
            return err("forbidden", 403)
        return jsonify([dict(r) for r in conn().execute("SELECT * FROM audit_log ORDER BY id")])

    @app.post("/api/sync/run")
    def run_sync():
        u = current_user()
        if not u:
            return err("authentication required", 401)
        if u["role"] not in {"admin", "facility_manager"}:
            return err("forbidden", 403)
        return jsonify(sync.process_outbox(conn(), app.config["SYNC_TRANSPORT"]))

    return app
