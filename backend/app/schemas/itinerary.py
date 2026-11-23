"""Itinerary item validation and serialization."""
from __future__ import annotations

from decimal import Decimal

from app.schemas.common import coord, fmt_money, iso
from app.utils.validators import (Validator, coordinate, integer, money, optional_string,
                                  string, time_)


def _fields(v: Validator, creating: bool) -> Validator:
    return (v.field("day_number", integer(1, 366), required=creating)
             .field("activity_name", string(200, min_len=1), required=creating)
             .field("description", optional_string(2000), nullable=True)
             .field("location", optional_string(200), nullable=True)
             .field("start_time", time_, nullable=True)
             .field("end_time", time_, nullable=True)
             .field("estimated_cost", money(), default=Decimal("0.00"))
             .field("latitude", coordinate("lat"), nullable=True)
             .field("longitude", coordinate("lon"), nullable=True)
             .field("sort_order", integer(0, 1000)))


def check_times(v: Validator, start, end) -> None:
    if start is not None and end is not None and end < start:
        v.error("end_time", "must be at or after start_time")


def validate_itinerary_create(data: dict) -> dict:
    v = _fields(Validator(data), creating=True)
    check_times(v, v.out.get("start_time"), v.out.get("end_time"))
    return v.finish()


def validate_itinerary_update(data: dict) -> Validator:
    return _fields(Validator(data, partial=True), creating=False)


def serialize_itinerary_item(item) -> dict:
    return {
        "id": item.id,
        "trip_id": item.trip_id,
        "day_number": item.day_number,
        "activity_name": item.activity_name,
        "description": item.description,
        "location": item.location,
        "start_time": item.start_time.strftime("%H:%M") if item.start_time else None,
        "end_time": item.end_time.strftime("%H:%M") if item.end_time else None,
        "estimated_cost": fmt_money(item.estimated_cost),
        "latitude": coord(item.latitude),
        "longitude": coord(item.longitude),
        "is_edited": item.is_edited,
        "sort_order": item.sort_order,
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
    }
