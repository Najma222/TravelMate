"""D10 booking -> expense synchronisation. Runs inside the caller's transaction."""
from __future__ import annotations

from sqlalchemy import delete, select

from app.extensions import db
from app.models import Booking, Expense
from app.utils.dates import to_app_date, today

TYPE_LABELS = {"hotel": "Hotel", "flight": "Flight", "train": "Train", "bus": "Bus"}


def category_for(booking_type: str) -> str:
    return "accommodation" if booking_type == "hotel" else "transport"


def _description(b: Booking) -> str:
    parts = [TYPE_LABELS.get(b.booking_type, b.booking_type.title())]
    if b.provider:
        parts.append(b.provider)
    if b.from_location and b.to_location:
        parts.append(f"{b.from_location} → {b.to_location}")
    text = " · ".join(parts)
    if b.booking_reference:
        text += f" ({b.booking_reference})"
    return text[:200]


def sync_booking_expense(booking: Booking) -> Expense | None:
    """Upsert or delete the single linked expense for ``booking``.

    Confirmed with amount > 0 -> exactly one confirmed ``source='booking'`` expense.
    Anything else -> no linked expense.
    """
    db.session.flush()  # booking.id must exist
    existing = db.session.execute(
        select(Expense).where(Expense.booking_id == booking.id).with_for_update()
    ).scalar_one_or_none()
    if booking.status == "Confirmed" and booking.amount is not None and booking.amount > 0:
        expense_date = to_app_date(booking.start_at) or booking.booked_on or today()
        if existing is None:
            existing = Expense(trip_id=booking.trip_id, booking_id=booking.id)
            db.session.add(existing)
        existing.category = category_for(booking.booking_type)
        existing.amount = booking.amount
        existing.description = _description(booking)
        existing.is_confirmed = True
        existing.source = "booking"
        existing.expense_date = expense_date
        return existing
    if existing is not None:
        db.session.execute(delete(Expense).where(Expense.id == existing.id))
    return None
