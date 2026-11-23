"""GET /health (public, unversioned)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.services import health_service
from app.utils.auth import public

bp = Blueprint("health", __name__)


@bp.get("/health")
@public
def health():
    db_ok = health_service.database_ok()
    body = {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable"}
    return jsonify(body), 200 if db_ok else 503
