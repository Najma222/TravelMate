"""``@internal_only``: shared-secret authentication for n8n -> Flask calls."""
from __future__ import annotations

import hmac
from functools import wraps

from flask import current_app, request

from app.utils.errors import Unauthorized


def verify_webhook_secret(provided: str | None) -> bool:
    expected = current_app.config.get("INTERNAL_WEBHOOK_SECRET") or ""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def internal_only(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not verify_webhook_secret(request.headers.get("X-Webhook-Secret")):
            from app.services import audit

            audit.record("internal_auth_failed", "denied", actor="n8n",
                         trip_id=kwargs.get("trip_id"),
                         meta={"path": request.path, "method": request.method})
            raise Unauthorized("Invalid or missing webhook secret")
        return fn(*args, **kwargs)

    wrapper._internal_only = True  # type: ignore[attr-defined]
    return wrapper
