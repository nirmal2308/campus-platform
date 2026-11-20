"""Outbox-based synchronisation with external calendar / issue tracker.
Local records are always committed first; external delivery is retried safely using
an idempotency key, so an outage never loses or duplicates data."""
import os

MAX_ATTEMPTS = 5


def default_transport(entity, entity_id, idem_key):
    """Stand-in for the real HTTP call. With no CAMPUS_SYNC_URL configured it behaves
    like a healthy external service (synthetic reference data only)."""
    if not os.environ.get("CAMPUS_SYNC_URL"):
        return f"EXT-{entity.upper()}-{entity_id}"
    raise ConnectionError("real external integration is out of scope for this assignment")


def enqueue(conn, entity, entity_id):
    target = "calendar" if entity == "booking" else "issue_tracker"
    conn.execute(
        "INSERT OR IGNORE INTO sync_outbox(entity, entity_id, target, idem_key) VALUES (?,?,?,?)",
        (entity, entity_id, target, f"{entity}:{entity_id}"))
    if entity == "booking":
        conn.execute("UPDATE bookings SET calendar_sync='pending' WHERE id=?", (entity_id,))


def process_outbox(conn, transport):
    delivered = failed = 0
    rows = conn.execute("SELECT * FROM sync_outbox WHERE status='pending'").fetchall()
    for r in rows:
        try:
            ext = transport(r["entity"], r["entity_id"], r["idem_key"])
        except ConnectionError as exc:
            attempts = r["attempts"] + 1
            status = "dead" if attempts >= MAX_ATTEMPTS else "pending"
            conn.execute("UPDATE sync_outbox SET attempts=?, status=?, last_error=? WHERE id=?",
                         (attempts, status, str(exc), r["id"]))
            failed += 1
            continue
        conn.execute("UPDATE sync_outbox SET status='synced', attempts=attempts+1 WHERE id=?", (r["id"],))
        if r["entity"] == "booking":
            conn.execute("UPDATE bookings SET calendar_sync='synced' WHERE id=?", (r["entity_id"],))
        else:
            conn.execute("UPDATE tickets SET external_issue_id=? WHERE id=?", (ext, r["entity_id"]))
        delivered += 1
    conn.commit()
    return {"delivered": delivered, "failed": failed}
