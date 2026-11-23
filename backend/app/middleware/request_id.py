"""Assigns a request id (``g.request_id``) and echoes it as ``X-Request-ID``."""
from __future__ import annotations

import re
import uuid

from flask import Flask, g, request

_SAFE_ID = re.compile(r"^[A-Za-z0-9-]{8,36}$")


def init_request_id(app: Flask) -> None:
    @app.before_request
    def _assign_request_id():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _SAFE_ID.match(incoming) else str(uuid.uuid4())

    @app.after_request
    def _echo_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response
