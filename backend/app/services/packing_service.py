"""Packing list CRUD with D11 reminder validation."""
from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.models import PackingItem, Trip
from app.services.ownership import get_owned_child, get_owned_trip
from app.utils.dates import end_of_day, now_utc
from app.utils.errors import Conflict, ValidationError

MAX_ITEMS = 300


def _check_remind_at(trip: Trip, remind_at) -> None:
    """remind_at must be in the future and no later than the trip's end date (APP_TIMEZONE)."""
    if remind_at is None:
        return
    if remind_at <= now_utc():
        raise ValidationError("Reminder must be in the future",
                              details={"fields": {"remind_at": "must be in the future"}})
    if remind_at >= end_of_day(trip.end_date):
        raise ValidationError("Reminder must be on or before the trip end date",
                              details={"fields": {"remind_at": "must be on or before the trip end date"}})


def list_items(user_id: int, trip_id: int):
    trip = get_owned_trip(user_id, trip_id)
    items = list(db.session.execute(
        select(PackingItem).where(PackingItem.trip_id == trip.id)
        .order_by(PackingItem.sort_order, PackingItem.id)).scalars())
    return trip, items


def create_item(user_id: int, trip_id: int, data: dict) -> PackingItem:
    try:
        trip = get_owned_trip(user_id, trip_id, for_update=True)
        _check_remind_at(trip, data.get("remind_at"))
        count, max_order = db.session.execute(
            select(func.count(PackingItem.id), func.coalesce(func.max(PackingItem.sort_order), -1))
            .where(PackingItem.trip_id == trip.id)).one()
        if count >= MAX_ITEMS:
            raise Conflict(f"A trip may have at most {MAX_ITEMS} packing items")
        data = dict(data)
        if data.get("sort_order") is None:
            data["sort_order"] = min(int(max_order) + 1, 1000)
        item = PackingItem(trip_id=trip.id, source="user", **data)
        db.session.add(item)
        db.session.commit()
        return item
    except Exception:
        db.session.rollback()
        raise


def update_item(user_id: int, item_id: int, data: dict) -> PackingItem:
    try:
        item, trip = get_owned_child(PackingItem, user_id, item_id, label="Packing item",
                                     for_update=True)
        if "remind_at" in data:
            _check_remind_at(trip, data["remind_at"])
        for k, v in data.items():
            setattr(item, k, v)
        db.session.commit()
        return item
    except Exception:
        db.session.rollback()
        raise


def delete_item(user_id: int, item_id: int) -> None:
    try:
        item, _trip = get_owned_child(PackingItem, user_id, item_id, label="Packing item",
                                      for_update=True)
        db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
