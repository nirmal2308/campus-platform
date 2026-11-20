CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE facilities (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  kind TEXT NOT NULL, restricted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE bookings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, facility_id INTEGER NOT NULL,
  user_id TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
  status TEXT NOT NULL, approved_by TEXT,
  FOREIGN KEY(facility_id) REFERENCES facilities(id));
CREATE TABLE tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
  reporter_id TEXT NOT NULL, impact INTEGER NOT NULL, urgency INTEGER NOT NULL,
  priority INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
  sla_deadline TEXT NOT NULL, resolved_at TEXT, idempotency_key TEXT UNIQUE);
CREATE TABLE sensor_events (
  event_id TEXT PRIMARY KEY, facility_id INTEGER NOT NULL, kind TEXT NOT NULL,
  value REAL NOT NULL, alert INTEGER NOT NULL, ticket_id INTEGER);
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT, detail TEXT);
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
