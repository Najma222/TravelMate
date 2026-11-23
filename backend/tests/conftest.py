"""Pytest fixtures.

Tests run against a real PostgreSQL 16 (JSONB, FOR UPDATE, deferrable constraints and
partial indexes are all PostgreSQL-specific). The schema is built by running the
Alembic migration, so every test run also verifies ``0001_initial_schema``.

    docker run -d --name travelmate-test-db -e POSTGRES_USER=travelmate \
      -e POSTGRES_PASSWORD=travelmate -e POSTGRES_DB=travelmate_test -p 55432:5432 postgres:16

Override the URL with ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.extensions import db, limiter  # noqa: E402

ORIGIN = "http://localhost:5173"
TABLES = ("audit_logs", "notifications", "packing_items", "expenses", "bookings", "itineraries",
          "trip_days", "trip_stops", "trips", "discover_destinations", "users")


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    with application.app_context():
        db.session.execute(text("DROP SCHEMA public CASCADE"))
        db.session.execute(text("CREATE SCHEMA public"))
        db.session.commit()
        from flask_migrate import upgrade

        upgrade()
        db.session.remove()
    yield application


@pytest.fixture(autouse=True)
def _clean_state(app, tmp_path):
    with app.app_context():
        db.session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        db.session.commit()
        db.session.remove()
    limiter.reset()
    app.config["UPLOAD_DIR"] = str(tmp_path / "uploads")
    yield


class ApiClient:
    """Test client that behaves like the SPA: same-origin header + JSON content type."""

    def __init__(self, flask_client):
        self.c = flask_client

    def _headers(self, headers, json_body=True):
        h = {"Origin": ORIGIN}
        if json_body:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        return h

    def get(self, path, headers=None, **kw):
        return self.c.get(path, headers=headers or {}, **kw)

    def post(self, path, json=None, headers=None, **kw):
        return self.c.post(path, json=json if json is not None else {}, headers=self._headers(headers), **kw)

    def put(self, path, json=None, headers=None, **kw):
        return self.c.put(path, json=json if json is not None else {}, headers=self._headers(headers), **kw)

    def delete(self, path, json=None, headers=None, **kw):
        if json is not None:
            return self.c.delete(path, json=json, headers=self._headers(headers), **kw)
        return self.c.delete(path, headers=self._headers(headers), **kw)

    def upload(self, path, data, headers=None):
        h = {"Origin": ORIGIN}
        h.update(headers or {})
        return self.c.post(path, data=data, headers=h, content_type="multipart/form-data")

    def raw(self):
        return self.c


@pytest.fixture
def client(app):
    return ApiClient(app.test_client())


@pytest.fixture
def make_client(app):
    return lambda: ApiClient(app.test_client())


@pytest.fixture
def internal(app):
    """Client for n8n -> Flask internal routes."""
    c = app.test_client()

    class Internal:
        secret = app.config["INTERNAL_WEBHOOK_SECRET"]

        def _h(self, headers):
            h = {"X-Webhook-Secret": self.secret}
            h.update(headers or {})
            return h

        def get(self, path, headers=None):
            return c.get(path, headers=self._h(headers))

        def post(self, path, json=None, headers=None):
            return c.post(path, json=json, headers=self._h(headers))

        def put(self, path, json=None, headers=None):
            return c.put(path, json=json, headers=self._h(headers))

    return Internal()


@pytest.fixture
def sql(app):
    """Run raw SQL in a short-lived app context (for test setup / assertions)."""
    def run(statement, **params):
        with app.app_context():
            res = db.session.execute(text(statement), params)
            rows = res.fetchall() if res.returns_rows else None
            db.session.commit()
            db.session.remove()
            return rows
    return run
