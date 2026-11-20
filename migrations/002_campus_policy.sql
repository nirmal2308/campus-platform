-- Campus-specific policy + sync support. Additive only: no column is dropped or
-- rewritten, so existing bookings, tickets and audit rows remain readable.
CREATE TABLE booking_policies (
  kind TEXT PRIMARY KEY, max_hours INTEGER NOT NULL);
INSERT INTO booking_policies VALUES ('lab', 3), ('hall', 6), ('classroom', 4), ('meeting_room', 2);
CREATE TABLE sensor_thresholds (
  kind TEXT PRIMARY KEY, threshold REAL NOT NULL);
INSERT INTO sensor_thresholds VALUES ('temperature', 28.0), ('humidity', 65.0), ('power_kw', 45.0);
ALTER TABLE bookings ADD COLUMN calendar_sync TEXT NOT NULL DEFAULT 'not_required';
ALTER TABLE tickets ADD COLUMN external_issue_id TEXT;
CREATE TABLE sync_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
  target TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
  idem_key TEXT UNIQUE NOT NULL, last_error TEXT);
UPDATE schema_version SET version = 2;
