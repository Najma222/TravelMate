"""GET /api/v1/trips/{id}/overview — aggregated trip page with ETag / 304 support."""
from __future__ import annotations

import hashlib
import json

from flask import Blueprint, Response, jsonify, request

from app.services import overview_service
from app.utils.auth import current_user, login_required

bp = Blueprint("overview", __name__, url_prefix="/api/v1")


@bp.get("/trips/<int:trip_id>/overview")
@login_required
def overview(trip_id: int):
    body = overview_service.build_overview(current_user().id, trip_id)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    etag = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    if request.if_none_match.contains_weak(etag):
        resp = Response(status=304)
    else:
        resp = jsonify(body)
    resp.set_etag(etag, weak=True)
    resp.headers["Cache-Control"] = "private, no-cache"
    return resp
