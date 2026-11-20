"""Unit tests (U17-U19) for the outbox logic, using a minimal in-memory database
so the module is tested in isolation from the REST layer."""
import sqlite3

import pytest

from app import sync

pytestmark = pytest.mark.unit


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE bookings (id INTEGER PRIMARY KEY, calendar_sync TEXT);
      CREATE TABLE tickets (id INTEGER PRIMARY KEY, external_issue_id TEXT);
      CREATE TABLE sync_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT, entity_id INTEGER,
        target TEXT, attempts INTEGER DEFAULT 0, status TEXT DEFAULT 'pending',
        idem_key TEXT UNIQUE, last_error TEXT);
      INSERT INTO bookings VALUES (1, 'not_required'); INSERT INTO tickets VALUES (7, NULL);""")
    return c


def test_u17_enqueue_is_idempotent_and_marks_booking_pending(con):
    sync.enqueue(con, "booking", 1)
    sync.enqueue(con, "booking", 1)  # duplicate enqueue must not create a second row
    assert con.execute("SELECT COUNT(*) FROM sync_outbox").fetchone()[0] == 1
    assert con.execute("SELECT calendar_sync FROM bookings").fetchone()[0] == "pending"


def test_u18_failed_delivery_increments_attempts_then_goes_dead_after_limit(con):
    sync.enqueue(con, "ticket", 7)

    def down(*a):
        raise ConnectionError("down")
    for _ in range(sync.MAX_ATTEMPTS):
        sync.process_outbox(con, down)
    row = con.execute("SELECT status, attempts FROM sync_outbox").fetchone()
    assert (row["status"], row["attempts"]) == ("dead", sync.MAX_ATTEMPTS)
    assert sync.process_outbox(con, down) == {"delivered": 0, "failed": 0}  # dead rows are not retried


def test_u19_successful_delivery_records_external_reference(con):
    sync.enqueue(con, "ticket", 7)
    sync.enqueue(con, "booking", 1)
    out = sync.process_outbox(con, lambda e, i, k: f"EXT-{e}-{i}")
    assert out == {"delivered": 2, "failed": 0}
    assert con.execute("SELECT external_issue_id FROM tickets").fetchone()[0] == "EXT-ticket-7"
    assert con.execute("SELECT calendar_sync FROM bookings").fetchone()[0] == "synced"
