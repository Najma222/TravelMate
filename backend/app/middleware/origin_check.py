"""D12 CSRF defence for user-facing unsafe methods.

``POST``/``PUT``/``PATCH``/``DELETE`` under ``/api/v1/`` (excluding ``/api/v1/internal/``,
which is authenticated by shared secret instead) must:

* carry an ``Origin`` (or, if absent, a ``Referer``) whose origin is in
  ``ALLOWED_ORIGINS``; and
* use ``Content-Type: application/json`` — or ``multipart/form-data`` on the upload
  routes only.

Violations return ``403 forbidden`` with the standard envelope and are audit-logged.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from flask import Flask, current_app, request

from app.utils.errors import error_response

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
UPLOAD_ROUTES = (
    re.compile(r"^/api/v1/auth/avatar/?$"),
    re.compile(r"^/api/v1/trips/\d+/cover/?$"),
)


def _origin_of(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_upload_route(path: str) -> bool:
    return any(p.match(path) for p in UPLOAD_ROUTES)


def check_request(method: str, path: str, headers) -> str | None:
    """Return a rejection reason, or ``None`` when the request is acceptable."""
    if method not in UNSAFE_METHODS:
        return None
    if not path.startswith("/api/v1/") or path.startswith("/api/v1/internal/"):
        return None
    allowed = {o.lower() for o in current_app.config.get("ALLOWED_ORIGINS", [])}
    origin = headers.get("Origin")
    if origin and origin != "null":
        if origin.rstrip("/").lower() not in allowed:
            return "origin_not_allowed"
    else:
        referer = headers.get("Referer")
        if not referer:
            return "origin_missing"
        if _origin_of(referer) not in allowed:
            return "referer_not_allowed"

    mimetype = (request.mimetype or "").lower()
    if mimetype == "application/json":
        return None
    if mimetype == "multipart/form-data" and is_upload_route(path):
        return None
    return "content_type_not_allowed"


_MESSAGES = {
    "origin_not_allowed": "Request origin is not allowed",
    "origin_missing": "Origin or Referer header is required",
    "referer_not_allowed": "Request referer is not allowed",
    "content_type_not_allowed": "Content-Type must be application/json",
}


def init_origin_check(app: Flask) -> None:
    @app.before_request
    def _origin_guard():
        reason = check_request(request.method, request.path, request.headers)
        if reason is None:
            return None
        from app.services import audit  # local import: avoid cycles at app import

        audit.record("csrf_rejected", "denied", actor="anon",
                     meta={"reason": reason, "path": request.path, "method": request.method})
        return error_response("forbidden", _MESSAGES[reason], 403, {"reason": reason})
