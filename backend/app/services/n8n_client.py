"""HTTP client for the n8n trip-generation webhook.

* Timeout: ``N8N_TIMEOUT_SECONDS`` (10 s).
* Exactly one retry, and only for *connection* errors (connection refused / DNS / reset
  before a response). Timeouts are never retried — the request may already be running
  in n8n, and a retry could start a duplicate generation.
* The shared secret is sent in ``X-Webhook-Secret`` and never logged.
"""
from __future__ import annotations

import logging

import requests
from flask import current_app

log = logging.getLogger("travelmate.n8n")


class N8NError(Exception):
    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def trigger_generation(payload: dict) -> None:
    url = current_app.config.get("N8N_TRIP_WEBHOOK_URL")
    secret = current_app.config.get("INTERNAL_WEBHOOK_SECRET") or ""
    timeout = current_app.config.get("N8N_TIMEOUT_SECONDS", 10)
    if not url:
        raise N8NError("webhook_url_not_configured")
    headers = {"X-Webhook-Secret": secret, "Content-Type": "application/json"}

    attempts = 0
    while True:
        attempts += 1
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            # Includes ConnectTimeout (a subclass of both Timeout and ConnectionError):
            # checked first so timeouts are never retried.
            log.warning("n8n_timeout attempt=%s trip_id=%s", attempts, payload.get("trip_id"))
            raise N8NError("timeout")
        except requests.exceptions.ConnectionError:
            log.warning("n8n_connection_error attempt=%s trip_id=%s", attempts, payload.get("trip_id"))
            if attempts < 2:
                continue
            raise N8NError("connection_error")
        except requests.exceptions.RequestException:
            raise N8NError("request_error")
        if 200 <= resp.status_code < 300:
            return
        log.warning("n8n_bad_status status=%s trip_id=%s", resp.status_code, payload.get("trip_id"))
        raise N8NError("bad_status", status=resp.status_code)
