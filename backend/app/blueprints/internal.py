"""/api/v1/internal — n8n -> Flask endpoints, authenticated by ``X-Webhook-Secret``."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.schemas.notification import serialize_notification, validate_internal_notification
from app.schemas.weather import validate_weather_payload
from app.services import (callback_service, notification_service, reminder_queries,
                          trip_service, weather)
from app.utils.errors import ValidationError
from app.utils.internal_auth import internal_only
from app.utils.validators import json_body

bp = Blueprint("internal", __name__, url_prefix="/api/v1/internal")


def _days_arg(default: int = 3, maximum: int = 60) -> int:
    raw = request.args.get("days", default)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = -1
    if days < 0 or days > maximum:
        raise ValidationError("Invalid days parameter",
                              details={"fields": {"days": f"must be between 0 and {maximum}"}})
    return days


@bp.post("/trips/<int:trip_id>/result")
@internal_only
def generation_result(trip_id: int):
    result = callback_service.process_callback(trip_id, json_body(required=True))
    return jsonify(result.body), result.status_code


@bp.put("/trips/<int:trip_id>/weather")
@internal_only
def put_weather(trip_id: int):
    parsed = validate_weather_payload(json_body(required=True))
    trip = weather.update_trip_weather(trip_id, parsed)
    return jsonify({"trip_id": trip.id, "weather": weather.build_weather_response(trip)}), 200


@bp.get("/upcoming-trips")
@internal_only
def upcoming_trips():
    days = _days_arg()
    return jsonify({"days": days, "items": reminder_queries.upcoming_trips(days)}), 200


@bp.get("/active-trips")
@internal_only
def active_trips():
    return jsonify({"items": reminder_queries.active_trips()}), 200


@bp.get("/booking-gaps")
@internal_only
def booking_gaps():
    days = _days_arg(default=14)
    return jsonify({"days": days, "items": reminder_queries.booking_gaps(days)}), 200


@bp.post("/notifications")
@internal_only
def record_notification():
    data = validate_internal_notification(json_body(required=True))
    n, status = notification_service.record_delivery(data)
    return jsonify({"notification": serialize_notification(n), "created": status == 201}), status


@bp.post("/sweep-stuck")
@internal_only
def sweep_stuck():
    ids = trip_service.sweep_stuck()
    return jsonify({"swept": len(ids), "trip_ids": ids}), 200
