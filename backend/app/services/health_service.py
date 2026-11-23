"""Readiness probe."""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.extensions import db

log = logging.getLogger("travelmate.health")


def database_ok() -> bool:
    try:
        db.session.execute(text("SELECT 1"))
        db.session.rollback()
        return True
    except Exception:
        db.session.rollback()
        log.warning("health_db_unavailable")
        return False
