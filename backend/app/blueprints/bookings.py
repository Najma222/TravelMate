"""Bookings (D10) and outbound booking search links."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.schemas.booking import serialize_booking, validate_booking_create
from app.services import booking_links, booking_service, trip_service
from app.utils.auth import current_user, login_required
from app.utils.validators import json_body

bp = Blueprint("bookings", __name__, url_prefix="/api/v1")


@bp.get("/trips/<int:trip_id>/bookings")
@login_required
def list_bookings(trip_id: int):
    trip, items, linked = booking_service.list_bookings(current_user().id, trip_id)
    return jsonify({"trip_id": trip.id, "currency": trip.currency,
                    "items": [serialize_booking(b, linked.get(b.id)) for b in items]}), 200


@bp.post("/trips/<int:trip_id>/bookings")
@login_required
def create_booking(trip_id: int):
    data = validate_booking_create(json_body(required=True))
    booking, expense_id = booking_service.create_booking(current_user().id, trip_id, data)
    return jsonify({"booking": serialize_booking(booking, expense_id)}), 201


@bp.put("/bookings/<int:booking_id>")
@login_required
def update_booking(booking_id: int):
    booking, expense_id = booking_service.update_booking(current_user().id, booking_id,
                                                         json_body(required=True))
    return jsonify({"booking": serialize_booking(booking, expense_id)}), 200


@bp.delete("/bookings/<int:booking_id>")
@login_required
def delete_booking(booking_id: int):
    booking_service.delete_booking(current_user().id, booking_id)
    return jsonify({"deleted": True, "id": booking_id}), 200


@bp.get("/trips/<int:trip_id>/booking-links")
@login_required
def links(trip_id: int):
    trip = trip_service.get_trip(current_user().id, trip_id)
    return jsonify(booking_links.build_links(trip)), 200
