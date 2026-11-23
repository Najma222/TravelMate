"""n8n generation-callback payload validation.

Two levels:

* **Envelope** (``validate_callback_envelope``): types and row caps. Failure => 400 and the
  Processing trip is marked Failed.
* **Rows** (``clean_*``): an invalid itinerary/expense/day/stop row is *dropped*, never
  repaired with invented data.
"""
from __future__ import annotations

from decimal import Decimal

from app.schemas.expense import normalize_category
from app.schemas.weather import validate_weather_payload
from app.utils.errors import ValidationError
from app.utils.validators import (FieldError, Validator, choice, coordinate, integer, money,
                                  string, time_, uuid_)

MAX_ITINERARY_ROWS = 200
MAX_EXPENSE_ROWS = 50
MAX_DAY_ROWS = 366
MAX_STOP_ROWS = 50


def parse_generation_id(data: dict):
    """Returns the UUID or raises ValidationError (no state change for unattributable payloads)."""
    if not isinstance(data, dict) or "generation_id" not in data:
        raise ValidationError("generation_id is required",
                              details={"fields": {"generation_id": "is required"}})
    try:
        return uuid_(data["generation_id"])
    except FieldError as e:
        raise ValidationError("generation_id is invalid",
                              details={"fields": {"generation_id": str(e)}})


def _rows(max_items: int):
    def parse(v):
        if not isinstance(v, list):
            raise FieldError("must be a list")
        if len(v) > max_items:
            raise FieldError(f"must contain at most {max_items} rows")
        return v
    return parse


def validate_callback_envelope(data: dict) -> dict:
    v = (Validator(data)
         .field("status", choice(("Completed", "Failed")), required=True)
         .field("error_message", string(500), nullable=True)
         .field("itinerary", _rows(MAX_ITINERARY_ROWS), default=list)
         .field("expenses", _rows(MAX_EXPENSE_ROWS), default=list)
         .field("days", _rows(MAX_DAY_ROWS), default=list)
         .field("stops", _rows(MAX_STOP_ROWS), default=list)
         .field("latitude", coordinate("lat"), nullable=True)
         .field("longitude", coordinate("lon"), nullable=True)
         .field("hero_quote", string(200), nullable=True)
         .field("hero_quote_author", string(80), nullable=True))
    weather_raw = data.get("weather") if isinstance(data, dict) else None
    out = v.finish()
    if weather_raw is not None:
        if not isinstance(weather_raw, dict):
            raise ValidationError("Request validation failed",
                                  details={"fields": {"weather": "must be an object"}})
        payload = dict(weather_raw)
        if "weather_message" in data and "weather_message" not in payload:
            payload["weather_message"] = data["weather_message"]
        try:
            out["weather"] = validate_weather_payload(payload)
        except ValidationError as e:
            raise ValidationError("Request validation failed",
                                  details={"fields": {"weather": e.details.get("fields", {})}})
    return out


def _truncate(value, limit: int):
    if value is None:
        return None
    if not isinstance(value, str):
        raise FieldError("must be a string")
    value = value.strip()
    return value[:limit] or None


def clean_activity(row, max_day: int) -> dict | None:
    """Return a cleaned activity or ``None`` when the row is invalid (dropped)."""
    if not isinstance(row, dict):
        return None
    try:
        name = _truncate(row.get("activity_name"), 200)
        if not name:
            return None
        day = integer(1, max_day)(row.get("day_number"))
        start = time_(row["start_time"]) if row.get("start_time") not in (None, "") else None
        end = time_(row["end_time"]) if row.get("end_time") not in (None, "") else None
        if start and end and end < start:
            return None
        cost_raw = row.get("estimated_cost")
        cost = money()(cost_raw) if cost_raw is not None else Decimal("0.00")
        lat = coordinate("lat")(row["latitude"]) if row.get("latitude") is not None else None
        lon = coordinate("lon")(row["longitude"]) if row.get("longitude") is not None else None
        if (lat is None) != (lon is None):
            lat = lon = None
        sort_order = integer(0, 1000)(row["sort_order"]) if row.get("sort_order") is not None else None
        return {
            "day_number": day,
            "activity_name": name,
            "description": _truncate(row.get("description"), 2000),
            "location": _truncate(row.get("location"), 200),
            "start_time": start,
            "end_time": end,
            "estimated_cost": cost,
            "latitude": lat,
            "longitude": lon,
            "sort_order": sort_order,
        }
    except (FieldError, KeyError, TypeError):
        return None


def clean_expense(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    try:
        amount = money(Decimal("0"), allow_equal_min=False)(row.get("amount"))
        return {
            "category": normalize_category(row.get("category")),
            "description": _truncate(row.get("description"), 200),
            "amount": amount,
        }
    except (FieldError, TypeError):
        return None


def clean_day(row, max_day: int) -> dict | None:
    if not isinstance(row, dict):
        return None
    try:
        day = integer(1, max_day)(row.get("day_number"))
        return {
            "day_number": day,
            "title": _truncate(row.get("title"), 120),
            "summary": _truncate(row.get("summary"), 300),
            "stop_name": _truncate(row.get("stop_name"), 100),
        }
    except (FieldError, TypeError):
        return None


def clean_stop(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    try:
        name = _truncate(row.get("name"), 100)
        if not name:
            return None
        lat = coordinate("lat")(row["latitude"]) if row.get("latitude") is not None else None
        lon = coordinate("lon")(row["longitude"]) if row.get("longitude") is not None else None
        if (lat is None) != (lon is None):
            lat = lon = None
        return {"name": name, "latitude": lat, "longitude": lon}
    except (FieldError, KeyError, TypeError):
        return None
