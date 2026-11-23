"""Itinerary items and day titles."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.schemas.itinerary import (serialize_itinerary_item, validate_itinerary_create,
                                   validate_itinerary_update)
from app.schemas.trip_day import serialize_day, validate_day_update
from app.services import itinerary_service, trip_rules
from app.utils.auth import current_user, login_required
from app.utils.validators import json_body

bp = Blueprint("itinerary", __name__, url_prefix="/api/v1")


@bp.get("/trips/<int:trip_id>/itinerary")
@login_required
def get_itinerary(trip_id: int):
    trip, days, stops, items = itinerary_service.get_itinerary(current_user().id, trip_id)
    by_day: dict[int, list] = {}
    for it in items:
        by_day.setdefault(it.day_number, []).append(serialize_itinerary_item(it))
    out_days = []
    for n in range(1, trip_rules.duration_days(trip.start_date, trip.end_date) + 1):
        d = days.get(n)
        stop = stops.get(d.stop_id) if d and d.stop_id else None
        out_days.append(serialize_day(trip, n, d, stop, by_day.get(n, [])))
    return jsonify({"trip_id": trip.id, "status": trip.status,
                    "itinerary_stale": trip.itinerary_stale, "days": out_days}), 200


@bp.post("/trips/<int:trip_id>/itinerary")
@login_required
def create_item(trip_id: int):
    data = validate_itinerary_create(json_body(required=True))
    item = itinerary_service.create_item(current_user().id, trip_id, data)
    return jsonify({"item": serialize_itinerary_item(item)}), 201


@bp.put("/itinerary/<int:item_id>")
@login_required
def update_item(item_id: int):
    validator = validate_itinerary_update(json_body(required=True))
    item = itinerary_service.update_item(current_user().id, item_id, validator)
    return jsonify({"item": serialize_itinerary_item(item)}), 200


@bp.delete("/itinerary/<int:item_id>")
@login_required
def delete_item(item_id: int):
    itinerary_service.delete_item(current_user().id, item_id)
    return jsonify({"deleted": True, "id": item_id}), 200


@bp.put("/trips/<int:trip_id>/days/<int:day_number>")
@login_required
def update_day(trip_id: int, day_number: int):
    data = validate_day_update(json_body(required=True))
    trip, day, stop = itinerary_service.update_day(current_user().id, trip_id, day_number, data)
    return jsonify({"day": serialize_day(trip, day_number, day, stop)}), 200
