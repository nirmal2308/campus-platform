-- Manual rollback of 002. SQLite cannot DROP COLUMN safely on older engines, so the
-- added columns are left in place (harmless, nullable/defaulted); only new tables go.
DROP TABLE IF EXISTS booking_policies;
DROP TABLE IF EXISTS sensor_thresholds;
DROP TABLE IF EXISTS sync_outbox;
UPDATE schema_version SET version = 1;
