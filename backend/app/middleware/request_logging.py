"""Structured (JSON) access logging with timing.

Only method, path (no query string), status, duration, request id and user id are
logged — never bodies, cookies, or secret headers.
"""
from __future__ import annotations

import json
import logging
import sys
import time

from flask import Flask, g, request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(app: Flask) -> None:
    root = logging.getLogger("travelmate")
    root.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    if not any(getattr(h, "_travelmate", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._travelmate = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.propagate = False


access_log = logging.getLogger("travelmate.access")


def init_request_logging(app: Flask) -> None:
    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _log_request(response):
        t0 = getattr(g, "_t0", None)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2) if t0 else None
        user = getattr(g, "current_user", None)
        access_log.info(
            "request",
            extra={"fields": {
                "request_id": getattr(g, "request_id", None),
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(user, "id", None),
            }},
        )
        return response
