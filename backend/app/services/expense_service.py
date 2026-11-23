"""User expense CRUD. Booking-linked expenses are read-only here (D10 -> 409)."""
from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Expense
from app.services.ownership import get_owned_child, get_owned_trip
from app.utils.dates import today
from app.utils.errors import Conflict, ValidationError

LOCKED_MESSAGE = "This expense is managed by its booking; edit the booking instead"


def list_expenses(user_id: int, trip_id: int, category: str | None = None):
    trip = get_owned_trip(user_id, trip_id)
    stmt = select(Expense).where(Expense.trip_id == trip.id)
    if category:
        stmt = stmt.where(Expense.category == category)
    items = db.session.execute(
        stmt.order_by(Expense.expense_date.desc(), Expense.id.desc())).scalars().all()
    return trip, list(items)


def create_expense(user_id: int, trip_id: int, data: dict) -> Expense:
    try:
        trip = get_owned_trip(user_id, trip_id)
        data = dict(data)
        data.setdefault("expense_date", today())
        exp = Expense(trip_id=trip.id, source="user", **data)
        db.session.add(exp)
        db.session.commit()
        return exp
    except Exception:
        db.session.rollback()
        raise


def update_expense(user_id: int, expense_id: int, data: dict) -> Expense:
    try:
        exp, _trip = get_owned_child(Expense, user_id, expense_id, label="Expense", for_update=True)
        if exp.booking_id is not None:
            raise Conflict(LOCKED_MESSAGE, details={"booking_id": exp.booking_id})
        if "expense_date" in data and data["expense_date"] is None:
            raise ValidationError(details={"fields": {"expense_date": "may not be null"}})
        for k, v in data.items():
            setattr(exp, k, v)
        db.session.commit()
        return exp
    except Exception:
        db.session.rollback()
        raise


def delete_expense(user_id: int, expense_id: int) -> None:
    try:
        exp, _trip = get_owned_child(Expense, user_id, expense_id, label="Expense", for_update=True)
        if exp.booking_id is not None:
            raise Conflict(LOCKED_MESSAGE, details={"booking_id": exp.booking_id})
        db.session.delete(exp)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
