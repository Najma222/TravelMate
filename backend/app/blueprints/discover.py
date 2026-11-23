"""GET /api/v1/discover/destinations (public)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.schemas.common import paginated
from app.schemas.discover import parse_discover_query, serialize_destination
from app.services import discover_service
from app.utils.auth import public
from app.utils.pagination import get_page_args, page_meta

bp = Blueprint("discover", __name__, url_prefix="/api/v1/discover")


@bp.get("/destinations")
@public
def destinations():
    filters = parse_discover_query()
    page, per_page = get_page_args()
    items, total = discover_service.search(filters, page, per_page)
    resp = jsonify(paginated([serialize_destination(d) for d in items],
                             page_meta(page, per_page, total)))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp, 200
