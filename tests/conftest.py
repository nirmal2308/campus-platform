from datetime import datetime

import pytest

from app import db, seed
from app.api import create_app

FIXED_NOW = datetime(2026, 12, 1, 8, 0, 0)


class Client:
    """Thin helper that sends the caller identity header the API trusts."""
    def __init__(self, flask_client):
        self.c = flask_client

    def req(self, method, url, user=None, json=None, headers=None):
        h = dict(headers or {})
        if user:
            h["X-User-Id"] = user
        return getattr(self.c, method)(url, json=json, headers=h)

    def get(self, url, user=None, **kw):
        return self.req("get", url, user, **kw)

    def post(self, url, user=None, json=None, **kw):
        return self.req("post", url, user, json=json, **kw)


@pytest.fixture
def clock():
    state = {"now": FIXED_NOW}
    state["fn"] = lambda: state["now"]
    return state


@pytest.fixture(params=[1], ids=["schema1"])
def schema_version(request):
    return request.param


@pytest.fixture
def make_app(tmp_path, clock):
    """Factory: isolated database per test, migrated to the requested schema."""
    def _make(schema=1, transport=None):
        path = str(tmp_path / f"campus-v{schema}.db")
        conn = db.connect(path)
        db.migrate(conn, target=schema)
        seed.seed(conn)
        conn.close()
        cfg = {"DB_PATH": path, "CLOCK": clock["fn"], "TESTING": True}
        if transport:
            cfg["SYNC_TRANSPORT"] = transport
        app = create_app(cfg)
        app.db_path = path
        return app
    return _make


@pytest.fixture
def api(make_app):
    return Client(make_app(1).test_client())


@pytest.fixture
def api2(make_app):
    return Client(make_app(2).test_client())


def rows(app, sql, args=()):
    conn = db.connect(app.db_path)
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()
