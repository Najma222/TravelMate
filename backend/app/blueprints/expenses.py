"""Expenses and the D3 budget summary."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.models import EXPENSE_CATEGORIES
from app.schemas.expense import (serialize_budget, serialize_expense, validate_expense_create,
                                 validate_expense_update)
from app.services import budget, expense_service, trip_service
from app.utils.auth import current_user, login_required
from app.utils.errors import ValidationError
from app.utils.validators import json_body

bp = Blueprint("expenses", __name__, url_prefix="/api/v1")


@bp.get("/trips/<int:trip_id>/expenses")
@login_required
def list_expenses(trip_id: int):
    category = request.args.get("category")
    if category is not None and category not in EXPENSE_CATEGORIES:
        raise ValidationError("Invalid category filter", details={"fields": {
            "category": "must be one of: " + ", ".join(EXPENSE_CATEGORIES)}})
    trip, items = expense_service.list_expenses(current_user().id, trip_id, category)
    return jsonify({"trip_id": trip.id, "currency": trip.currency,
                    "items": [serialize_expense(e) for e in items]}), 200


@bp.post("/trips/<int:trip_id>/expenses")
@login_required
def create_expense(trip_id: int):
    data = validate_expense_create(json_body(required=True))
    exp = expense_service.create_expense(current_user().id, trip_id, data)
    return jsonify({"expense": serialize_expense(exp)}), 201


@bp.put("/expenses/<int:expense_id>")
@login_required
def update_expense(expense_id: int):
    data = validate_expense_update(json_body(required=True))
    exp = expense_service.update_expense(current_user().id, expense_id, data)
    return jsonify({"expense": serialize_expense(exp)}), 200


@bp.delete("/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id: int):
    expense_service.delete_expense(current_user().id, expense_id)
    return jsonify({"deleted": True, "id": expense_id}), 200


@bp.get("/trips/<int:trip_id>/budget")
@login_required
def get_budget(trip_id: int):
    trip = trip_service.get_trip(current_user().id, trip_id)
    summary = budget.trip_budget(trip)
    return jsonify({"trip_id": trip.id, "budget": serialize_budget(summary, trip.currency)}), 200
