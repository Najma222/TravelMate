"""TravelMate Flask application factory."""
from __future__ import annotations

from flask import Flask

from config import get_config


def create_app(config_name: str | None = None) -> Flask:
    cfg = get_config(config_name)
    cfg.validate()

    app = Flask(__name__)
    app.config.from_object(cfg)
    app.json.sort_keys = False

    if app.config.get("TRUSTED_PROXIES", 0) > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    from app.extensions import bcrypt, db, limiter, migrate
    from app.middleware.origin_check import init_origin_check
    from app.middleware.request_id import init_request_id
    from app.middleware.request_logging import configure_logging, init_request_logging

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db, directory=_migrations_dir())
    bcrypt.init_app(app)
    limiter.init_app(app)

    from app import models  # noqa: F401  (register mappers for Alembic)

    # Order matters: request id -> timing -> CSRF/origin guard.
    init_request_id(app)
    init_request_logging(app)
    init_origin_check(app)

    from app.blueprints import (auth, bookings, dashboard, discover, expenses, health, internal,
                                itinerary, media, notifications, overview, packing, trips)

    for module in (health, media, auth, trips, overview, itinerary, expenses, bookings, packing,
                   notifications, dashboard, discover, internal):
        app.register_blueprint(module.bp)

    from app.utils.errors import register_error_handlers

    register_error_handlers(app)

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    from app.cli import register_cli

    register_cli(app)
    return app


def _migrations_dir() -> str:
    import os

    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
