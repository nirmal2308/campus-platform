"""Start-up bootstrap: migrate + seed exactly once, even when several worker
processes start at the same moment (fixes the v1.0.0 start-up race)."""
import fcntl

from . import db, seed


def bootstrap(path):
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)           # serialise concurrent workers
        try:
            conn = db.connect(path)
            try:
                db.migrate(conn)
                seed.seed(conn)
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
