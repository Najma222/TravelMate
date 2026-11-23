"""GET /api/v1/dashboard."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.services import overview_service
from app.utils.auth import current_user, login_required

bp = Blueprint("dashboard", __name__, url_prefix="/api/v1")


@bp.get("/dashboard")
@login_required
def dashboard():
    return jsonify(overview_service.build_dashboard(current_user())), 200
