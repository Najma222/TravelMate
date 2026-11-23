"""Trip day validation and serialization (D7: date computed, never stored)."""
from __future__ import annotations

from app.utils.dates import trip_day_date
from app.utils.validators import Validator, integer, optional_string, string


def default_day_title(day_number: int) -> str:
    return f"Day {day_number}"


def validate_day_update(data: dict) -> dict:
    return (Validator(data, partial=True)
            .field("title", string(120, min_len=1))
            .field("summary", optional_string(300), nullable=True)
            .field("stop_id", integer(1), nullable=True)
            .finish())


def serialize_day(trip, day_number: int, day=None, stop=None, items=None) -> dict:
    out = {
        "day_number": day_number,
        "date": trip_day_date(trip.start_date, day_number).isoformat(),
        "title": day.title if day else default_day_title(day_number),
        "summary": day.summary if day else None,
        "stop": {"id": stop.id, "name": stop.name} if stop else None,
    }
    if items is not None:
        out["items"] = items
    return out
