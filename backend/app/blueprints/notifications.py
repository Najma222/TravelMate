"""User notification inbox and preferences."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.schemas.common import paginated
from app.schemas.notification import (serialize_notification, serialize_preferences,
                                      validate_preferences, validate_unread_filter)
from app.services import notification_service
from app.utils.auth import current_user, login_required
from app.utils.pagination import get_page_args, page_meta
from app.utils.validators import json_body

bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@bp.get("")
@login_required
def list_notifications():
    unread = validate_unread_filter(request.args.get("unread"))
    page, per_page = get_page_args()
    items, total, unread_count = notification_service.list_for_user(
        current_user().id, unread, page, per_page)
    body = paginated([serialize_notification(n) for n in items], page_meta(page, per_page, total))
    body["unread_count"] = unread_count
    return jsonify(body), 200


@bp.put("/<int:notification_id>/read")
@login_required
def mark_read(notification_id: int):
    n = notification_service.mark_read(current_user().id, notification_id)
    return jsonify({"notification": serialize_notification(n)}), 200


@bp.post("/read-all")
@login_required
def read_all():
    count = notification_service.mark_all_read(current_user().id)
    return jsonify({"marked_read": count}), 200


@bp.get("/preferences")
@login_required
def get_preferences():
    return jsonify({"preferences": serialize_preferences(current_user())}), 200


@bp.put("/preferences")
@login_required
def update_preferences():
    data = validate_preferences(json_body(required=True))
    user = notification_service.update_preferences(current_user(), data)
    return jsonify({"preferences": serialize_preferences(user)}), 200
