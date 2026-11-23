"""Security audit log writer.

Audit rows are written on a *separate* connection (autonomous transaction) so they
persist even when the caller's business transaction rolls back, and so writing an
audit row never commits the caller's pending work.

Never put passwords, cookies, secrets or raw payloads into ``meta``.
"""
from __future__ import annotations

import hashlib
import logging

from flask import g, has_request_context, request
from sqlalchemy import insert

from app.extensions import db
from app.models import AuditLog

log = logging.getLogger("travelmate.audit")

ACTORS = {"user", "anon", "n8n", "system"}


def email_fingerprint(email: str) -> str:
    """Stable, non-reversible identifier for an email used in audit meta."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def record(action: str, outcome: str, *, actor: str = "system", user_id: int | None = None,
           trip_id: int | None = None, meta: dict | None = None) -> None:
    if actor not in ACTORS:
        actor = "system"
    request_id = ip = None
    if has_request_context():
        request_id = getattr(g, "request_id", None)
        ip = request.remote_addr
    values = {
        "user_id": user_id,
        "trip_id": trip_id,
        "actor": actor,
        "action": action[:40],
        "outcome": outcome[:10],
        "request_id": request_id,
        "ip": ip,
        "meta": meta or {},
    }
    try:
        with db.engine.begin() as conn:
            conn.execute(insert(AuditLog).values(**values))
    except Exception:  # audit must never break the request path
        log.exception("audit_write_failed action=%s", action)
    log.info("audit", extra={"fields": {k: v for k, v in values.items() if k != "meta"}})
