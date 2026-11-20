"""R07 - regression test born from the deployment failure observed on v1.0.0:
several workers booting at once must not crash on migration."""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.regression
CODE = "import sys; from app.bootstrap import bootstrap; bootstrap(sys.argv[1])"


def test_r07_concurrent_worker_startup_migrates_exactly_once(tmp_path):
    db = str(tmp_path / "campus.db")
    procs = [subprocess.Popen([sys.executable, "-c", CODE, db], stderr=subprocess.PIPE) for _ in range(6)]
    results = [(p.wait(), p.stderr.read().decode()) for p in procs]
    assert all(code == 0 for code, _ in results), results
    import sqlite3
    c = sqlite3.connect(db)
    assert c.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 4
