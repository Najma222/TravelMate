"""/api/v1/trips — trip CRUD, generation, status, cover, weather, places and stops."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.schemas.common import coord, paginated
from app.schemas.media import serialize_upload
from app.schemas.trip import (parse_scope, serialize_trip, serialize_trip_status,
                              validate_trip_create, validate_trip_update)
from app.schemas.trip_stop import (serialize_stop, validate_stop_create, validate_stop_order,
                                   validate_stop_update)
from app.services import generation_service, trip_service, upload_service
from app.services.weather import build_weather_response
from app.utils.auth import current_user, login_required
from app.utils.pagination import get_page_args, page_meta
from app.utils.validators import json_body

bp = Blueprint("trips", __name__, url_prefix="/api/v1")


@bp.post("/trips")
@login_required
def create_trip():
    data = validate_trip_create(json_body(required=True))
    trip = trip_service.create_trip(current_user().id, data)
    return jsonify({"trip": serialize_trip(trip)}), 201


@bp.get("/trips")
@login_required
def list_trips():
    scope = parse_scope(request.args.get("scope"))
    page, per_page = get_page_args()
    items, total = trip_service.list_trips(current_user().id, scope, page, per_page)
    return jsonify({**paginated([serialize_trip(t) for t in items], page_meta(page, per_page, total)),
                    "scope": scope}), 200


@bp.get("/trips/<int:trip_id>")
@login_required
def get_trip(trip_id: int):
    trip = trip_service.get_trip(current_user().id, trip_id)
    return jsonify({"trip": serialize_trip(trip)}), 200


@bp.put("/trips/<int:trip_id>")
@login_required
def update_trip(trip_id: int):
    validator = validate_trip_update(json_body(required=True))
    trip = trip_service.update_trip(current_user().id, trip_id, validator)
    return jsonify({"trip": serialize_trip(trip)}), 200


@bp.delete("/trips/<int:trip_id>")
@login_required
def delete_trip(trip_id: int):
    cover = trip_service.delete_trip(current_user().id, trip_id)
    upload_service.delete_media(cover)
    return jsonify({"deleted": True, "id": trip_id}), 200


@bp.post("/trips/<int:trip_id>/generate")
@login_required
def generate(trip_id: int):
    trip = generation_service.start_generation(current_user().id, trip_id)
    return jsonify({"trip": serialize_trip_status(trip)}), 202


@bp.post("/trips/<int:trip_id>/cancel")
@login_required
def cancel(trip_id: int):
    trip = trip_service.cancel_trip(current_user().id, trip_id)
    return jsonify({"trip": serialize_trip(trip)}), 200


@bp.get("/trips/<int:trip_id>/status")
@login_required
def status(trip_id: int):
    trip = trip_service.get_status(current_user().id, trip_id)
    return jsonify({"trip": serialize_trip_status(trip)}), 200


@bp.post("/trips/<int:trip_id>/cover")
@login_required
def upload_cover(trip_id: int):
    trip_service.get_trip(current_user().id, trip_id)  # 404 before doing any image work
    url = upload_service.process_image(request.files.get("file"), "covers")
    try:
        trip, old = trip_service.set_cover(current_user().id, trip_id, url)
    except Exception:
        upload_service.delete_media(url)
        raise
    upload_service.delete_media(old)
    return jsonify({"trip": serialize_trip(trip), "upload": serialize_upload("cover", url)}), 200


@bp.get("/trips/<int:trip_id>/weather")
@login_required
def weather(trip_id: int):
    trip = trip_service.get_trip(current_user().id, trip_id)
    return jsonify({"trip_id": trip.id, "weather": build_weather_response(trip)}), 200


@bp.get("/trips/<int:trip_id>/places")
@login_required
def places(trip_id: int):
    trip, stops, items = trip_service.get_places(current_user().id, trip_id)
    return jsonify({
        "trip_id": trip.id,
        "destination": {"name": trip.destination, "latitude": coord(trip.latitude),
                        "longitude": coord(trip.longitude)},
        "stops": [serialize_stop(s) for s in stops],
        "places": [{
            "itinerary_id": i.id,
            "day_number": i.day_number,
            "name": i.activity_name,
            "location": i.location,
            "latitude": coord(i.latitude),
            "longitude": coord(i.longitude),
        } for i in items],
    }), 200


# --------------------------------------------------------------------------- stops

@bp.post("/trips/<int:trip_id>/stops")
@login_required
def add_stop(trip_id: int):
    data = validate_stop_create(json_body(required=True))
    stop = trip_service.add_stop(current_user().id, trip_id, data)
    return jsonify({"stop": serialize_stop(stop)}), 201


@bp.put("/stops/<int:stop_id>")
@login_required
def update_stop(stop_id: int):
    data = validate_stop_update(json_body(required=True))
    stop = trip_service.update_stop(current_user().id, stop_id, data)
    return jsonify({"stop": serialize_stop(stop)}), 200


@bp.delete("/stops/<int:stop_id>")
@login_required
def delete_stop(stop_id: int):
    trip_service.delete_stop(current_user().id, stop_id)
    return jsonify({"deleted": True, "id": stop_id}), 200


@bp.put("/trips/<int:trip_id>/stops/order")
@login_required
def reorder_stops(trip_id: int):
    stop_ids = validate_stop_order(json_body(required=True))
    stops = trip_service.reorder_stops(current_user().id, trip_id, stop_ids)
    return jsonify({"stops": [serialize_stop(s) for s in stops]}), 200
