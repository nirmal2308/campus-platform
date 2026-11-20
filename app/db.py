import glob
import os
import sqlite3


def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def current_version(conn):
    try:
        return conn.execute("SELECT version FROM schema_version").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def migrate(conn, target=None, migrations_dir=None):
    """Apply numbered migrations in order. Each runs in a transaction and is
    recorded, so a failed migration leaves the previous version intact."""
    migrations_dir = migrations_dir or os.path.join(os.path.dirname(__file__), "..", "migrations")
    files = sorted(f for f in glob.glob(os.path.join(migrations_dir, "[0-9][0-9][0-9]_*.sql"))
                   if not f.endswith("_rollback.sql"))
    for f in files:
        num = int(os.path.basename(f)[:3])
        if num <= current_version(conn) or (target and num > target):
            continue
        script = open(f).read()
        try:
            conn.executescript("BEGIN;\n" + script + "\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
    return current_version(conn)


def audit(conn, actor, action, entity, entity_id=None, detail=""):
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO audit_log(ts, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), actor, action, entity, str(entity_id), detail))
