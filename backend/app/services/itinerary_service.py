"""Itinerary items and trip days."""
from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Itinerary, Trip, TripDay, TripStop
from app.schemas.itinerary import check_times
from app.schemas.trip_day import default_day_title
from app.services import trip_rules
from app.services.ownership import get_owned_child, get_owned_trip
from app.utils.errors import Conflict, ValidationError


def _assert_editable(trip: Trip) -> None:
    if trip.status == "Processing":
        raise Conflict("Itinerary is being generated; try again when generation finishes",
                       details={"status": trip.status})


def _assert_day_in_range(trip: Trip, day_number: int, field: str = "day_number") -> None:
    max_day = trip_rules.duration_days(trip.start_date, trip.end_date)
    if day_number > max_day:
        raise ValidationError("Day is outside the trip dates",
                              details={"fields": {field: f"must be between 1 and {max_day}"}})


def get_itinerary(user_id: int, trip_id: int):
    """Returns (trip, days, stops_by_id, items) — 4 queries regardless of size."""
    trip = get_owned_trip(user_id, trip_id)
    max_day = trip_rules.duration_days(trip.start_date, trip.end_date)
    days = {d.day_number: d for d in db.session.execute(
        select(TripDay).where(TripDay.trip_id == trip.id, TripDay.day_number <= max_day)).scalars()}
    stops = {s.id: s for s in db.session.execute(
        select(TripStop).where(TripStop.trip_id == trip.id)).scalars()}
    items = list(db.session.execute(
        select(Itinerary)
        .where(Itinerary.trip_id == trip.id, Itinerary.day_number <= max_day)
        .order_by(Itinerary.day_number, Itinerary.sort_order,
                  Itinerary.start_time.asc().nulls_last(), Itinerary.id)).scalars())
    return trip, days, stops, items


def create_item(user_id: int, trip_id: int, data: dict) -> Itinerary:
    try:
        trip = get_owned_trip(user_id, trip_id, for_update=True)
        _assert_editable(trip)
        _assert_day_in_range(trip, data["day_number"])
        if data.get("sort_order") is None:
            data = {**data, "sort_order": 0}
        item = Itinerary(trip_id=trip.id, is_edited=True, **data)
        db.session.add(item)
        db.session.commit()
        return item
    except Exception:
        db.session.rollback()
        raise


def update_item(user_id: int, item_id: int, validator) -> Itinerary:
    try:
        item, trip = get_owned_child(Itinerary, user_id, item_id, label="Itinerary item",
                                     for_update=True)
        data = validator.out
        check_times(validator, data.get("start_time", item.start_time),
                    data.get("end_time", item.end_time))
        validator.finish()
        _assert_editable(trip)
        if "day_number" in data:
            _assert_day_in_range(trip, data["day_number"])
        for k, v in data.items():
            setattr(item, k, v)
        item.is_edited = True
        db.session.commit()
        return item
    except Exception:
        db.session.rollback()
        raise


def delete_item(user_id: int, item_id: int) -> None:
    try:
        item, trip = get_owned_child(Itinerary, user_id, item_id, label="Itinerary item",
                                     for_update=True)
        _assert_editable(trip)
        db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def update_day(user_id: int, trip_id: int, day_number: int, data: dict):
    try:
        trip = get_owned_trip(user_id, trip_id, for_update=True)
        _assert_editable(trip)
        if day_number < 1:
            raise ValidationError(details={"fields": {"day_number": "must be >= 1"}})
        _assert_day_in_range(trip, day_number)
        stop = None
        if data.get("stop_id") is not None:
            stop = db.session.execute(select(TripStop).where(
                TripStop.id == data["stop_id"], TripStop.trip_id == trip.id)).scalar_one_or_none()
            if stop is None:
                raise ValidationError("Stop not found on this trip",
                                      details={"fields": {"stop_id": "must be a stop of this trip"}})
        day = db.session.execute(select(TripDay).where(
            TripDay.trip_id == trip.id, TripDay.day_number == day_number)).scalar_one_or_none()
        if day is None:
            day = TripDay(trip_id=trip.id, day_number=day_number, title=default_day_title(day_number))
            db.session.add(day)
        for k, v in data.items():
            setattr(day, k, v)
        db.session.commit()
        if stop is None and day.stop_id:
            stop = db.session.get(TripStop, day.stop_id)
        return trip, day, stop
    except Exception:
        db.session.rollback()
        raise
