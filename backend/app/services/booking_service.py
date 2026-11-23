"""Booking CRUD; every write syncs the linked expense in the SAME transaction (D10)."""
from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Booking, Expense
from app.schemas.booking import validate_booking_update
from app.services import booking_sync
from app.services.ownership import get_owned_child, get_owned_trip


def linked_expense_ids(booking_ids: list[int]) -> dict[int, int]:
    if not booking_ids:
        return {}
    rows = db.session.execute(
        select(Expense.booking_id, Expense.id).where(Expense.booking_id.in_(booking_ids))).all()
    return {b: e for b, e in rows}


def list_bookings(user_id: int, trip_id: int):
    trip = get_owned_trip(user_id, trip_id)
    items = list(db.session.execute(
        select(Booking).where(Booking.trip_id == trip.id)
        .order_by(Booking.start_at.asc().nulls_last(), Booking.id)).scalars())
    return trip, items, linked_expense_ids([b.id for b in items])


def create_booking(user_id: int, trip_id: int, data: dict) -> tuple[Booking, int | None]:
    try:
        trip = get_owned_trip(user_id, trip_id)
        booking = Booking(trip_id=trip.id, **data)
        db.session.add(booking)
        expense = booking_sync.sync_booking_expense(booking)
        db.session.flush()
        expense_id = expense.id if expense else None
        db.session.commit()
        return booking, expense_id
    except Exception:
        db.session.rollback()
        raise


def update_booking(user_id: int, booking_id: int, payload: dict) -> tuple[Booking, int | None]:
    """Lock the booking row, validate against its current values, apply and sync."""
    try:
        booking, _trip = get_owned_child(Booking, user_id, booking_id, label="Booking",
                                         for_update=True)
        data = validate_booking_update(payload, booking)
        for k, v in data.items():
            setattr(booking, k, v)
        expense = booking_sync.sync_booking_expense(booking)
        db.session.flush()
        expense_id = expense.id if expense else None
        db.session.commit()
        return booking, expense_id
    except Exception:
        db.session.rollback()
        raise


def delete_booking(user_id: int, booking_id: int) -> None:
    try:
        booking, _trip = get_owned_child(Booking, user_id, booking_id, label="Booking",
                                         for_update=True)
        db.session.delete(booking)  # linked expense removed by ON DELETE CASCADE
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
