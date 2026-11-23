"""Ownership-scoped loaders. Anything not owned by the user is a 404 (no enumeration)."""
from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Trip
from app.utils.errors import NotFound


def get_owned_trip(user_id: int, trip_id: int, *, for_update: bool = False) -> Trip:
    stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    trip = db.session.execute(stmt).scalar_one_or_none()
    if trip is None:
        raise NotFound("Trip not found")
    return trip


def get_owned_child(model, user_id: int, child_id: int, *, label: str, for_update: bool = False):
    """Load a trip child row (stop, itinerary, expense, booking, packing) owned via its trip.

    Returns ``(child, trip)``.
    """
    stmt = (select(model, Trip)
            .join(Trip, Trip.id == model.trip_id)
            .where(model.id == child_id, Trip.user_id == user_id))
    if for_update:
        stmt = stmt.with_for_update(of=model)
    row = db.session.execute(stmt).first()
    if row is None:
        raise NotFound(f"{label} not found")
    return row[0], row[1]
