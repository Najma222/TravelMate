"""Standard error envelope and global error handlers.

Every error response has the shape::

    {"error": {"code": "<snake_case>", "message": "<human text>", "details": {...}}}
"""
from __future__ import annotations

import logging

from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException

log = logging.getLogger("travelmate.errors")


class APIError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Bad request"

    def __init__(self, message: str | None = None, *, details: dict | None = None,
                 code: str | None = None, headers: dict | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}
        if code:
            self.code = code
        self.headers = headers or {}


class ValidationError(APIError):
    status_code = 400
    code = "validation_error"
    message = "Request validation failed"


class Unauthorized(APIError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required"


class Forbidden(APIError):
    status_code = 403
    code = "forbidden"
    message = "Request forbidden"


class NotFound(APIError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class Conflict(APIError):
    status_code = 409
    code = "conflict"
    message = "Request conflicts with current state"


class PayloadTooLarge(APIError):
    status_code = 413
    code = "payload_too_large"
    message = "Payload too large"


class UnsupportedMediaType(APIError):
    status_code = 415
    code = "unsupported_media_type"
    message = "Unsupported media type"


class RateLimited(APIError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests"


class UpstreamError(APIError):
    status_code = 502
    code = "upstream_error"
    message = "Upstream service failed"


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(code: str, message: str, status: int, details: dict | None = None,
                   headers: dict | None = None):
    resp = jsonify(error_body(code, message, details))
    resp.status_code = status
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def _api_error(err: APIError):
        return error_response(err.code, err.message, err.status_code, err.details, err.headers)

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        status = err.code or 500
        code = _HTTP_CODES.get(status, "http_error")
        headers = {}
        message = err.description or err.name
        if status == 413:
            message = "Upload exceeds the 2 MB limit"
        if status == 429:
            message = "Too many requests. Please slow down."
            retry_after = None
            if err.response is not None:
                retry_after = err.response.headers.get("Retry-After")
            if retry_after:
                headers["Retry-After"] = retry_after
        if status == 405:
            message = "Method not allowed"
        return error_response(code, message, status, None, headers)

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):  # pragma: no cover - exercised via tests with forced errors
        log.exception("unhandled_exception request_id=%s", getattr(g, "request_id", "-"))
        return error_response("internal_error", "An unexpected error occurred", 500)
