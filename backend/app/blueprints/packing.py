"""Packing list CRUD."""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.schemas.packing import (serialize_packing_item, validate_packing_create,
                                 validate_packing_update)
from app.services import packing_service
from app.utils.auth import current_user, login_required
from app.utils.validators import json_body

bp = Blueprint("packing", __name__, url_prefix="/api/v1")


@bp.get("/trips/<int:trip_id>/packing")
@login_required
def list_items(trip_id: int):
    trip, items = packing_service.list_items(current_user().id, trip_id)
    packed = sum(1 for i in items if i.is_packed)
    return jsonify({"trip_id": trip.id, "total": len(items), "packed": packed,
                    "items": [serialize_packing_item(i) for i in items]}), 200


@bp.post("/trips/<int:trip_id>/packing")
@login_required
def create_item(trip_id: int):
    data = validate_packing_create(json_body(required=True))
    item = packing_service.create_item(current_user().id, trip_id, data)
    return jsonify({"item": serialize_packing_item(item)}), 201


@bp.put("/packing/<int:item_id>")
@login_required
def update_item(item_id: int):
    data = validate_packing_update(json_body(required=True))
    item = packing_service.update_item(current_user().id, item_id, data)
    return jsonify({"item": serialize_packing_item(item)}), 200


@bp.delete("/packing/<int:item_id>")
@login_required
def delete_item(item_id: int):
    packing_service.delete_item(current_user().id, item_id)
    return jsonify({"deleted": True, "id": item_id}), 200
