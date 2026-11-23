"""Trip validation and serialization."""
from __future__ import annotations

from decimal import Decimal

from app.models import ACCOMMODATION_PREFERENCES, CURRENCIES, TRANSPORT_PREFERENCES
from app.schemas.common import coord, fmt_money, iso
from app.services import trip_rules
from app.utils.dates import to_app_date, today
from app.utils.validators import (Validator, choice, coordinate, date_, integer, money,
                                  optional_string, string)

TRIP_FIELDS_AFFECTING_GENERATION = {
    "origin", "destination", "start_date", "end_date", "traveller_count", "budget",
    "preferences", "transport_preference", "accommodation_preference",
}


def _common(v: Validator, creating: bool) -> Validator:
    req = creating
    return (v.field("origin", string(100, min_len=1), required=req)
             .field("destination", string(100, min_len=1), required=req)
             .field("start_date", date_, required=req)
             .field("end_date", date_, required=req)
             .field("traveller_count", integer(1, 50), default=1)
             .field("budget", money(Decimal("0"), allow_equal_min=False), required=req)
             .field("currency", choice(CURRENCIES, case_insensitive=True), default="INR")
             .field("preferences", optional_string(500), nullable=True)
             .field("transport_preference", choice(TRANSPORT_PREFERENCES), default="any")
             .field("accommodation_preference", choice(ACCOMMODATION_PREFERENCES), default="any")
             .field("latitude", coordinate("lat"), nullable=True)
             .field("longitude", coordinate("lon"), nullable=True)
             .field("hero_quote", optional_string(200), nullable=True)
             .field("hero_quote_author", optional_string(80), nullable=True))


def check_dates(v: Validator, start, end, *, start_changed: bool) -> None:
    """Cross-field date rules shared by create and update."""
    if start is None or end is None:
        return
    if start_changed and start < today():
        v.error("start_date", "must not be in the past")
    if end < start:
        v.error("end_date", "must be on or after start_date")
    elif trip_rules.duration_days(start, end) > trip_rules.MAX_TRIP_DAYS:
        v.error("end_date", f"trip may not exceed {trip_rules.MAX_TRIP_DAYS} days")


def validate_trip_create(data: dict) -> dict:
    v = _common(Validator(data), creating=True)
    check_dates(v, v.out.get("start_date"), v.out.get("end_date"), start_changed=True)
    return v.finish()


def validate_trip_update(data: dict) -> Validator:
    """Returns the (unfinished) validator so the service can add cross-field errors."""
    v = Validator(data, partial=True)
    return _common(v, creating=False)


def parse_scope(raw: str | None) -> str:
    scope = (raw or "all").lower()
    if scope not in ("upcoming", "archive", "all"):
        from app.utils.errors import ValidationError

        raise ValidationError("Invalid scope", details={"fields": {
            "scope": "must be one of: upcoming, archive, all"}})
    return scope


def serialize_trip(trip, *, today_date=None) -> dict:
    t = today_date or today()
    created = to_app_date(trip.created_at) or t
    days_until = (trip.start_date - t).days
    return {
        "id": trip.id,
        "origin": trip.origin,
        "destination": trip.destination,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "duration_days": trip_rules.duration_days(trip.start_date, trip.end_date),
        "traveller_count": trip.traveller_count,
        "budget": fmt_money(trip.budget),
        "currency": trip.currency,
        "preferences": trip.preferences,
        "transport_preference": trip.transport_preference,
        "accommodation_preference": trip.accommodation_preference,
        "status": trip.status,
        "error_message": trip.error_message,
        "itinerary_stale": trip.itinerary_stale,
        "latitude": coord(trip.latitude),
        "longitude": coord(trip.longitude),
        "cover_image_url": trip.cover_image_url,
        "hero_quote": trip.hero_quote,
        "hero_quote_author": trip.hero_quote_author,
        "phase": trip_rules.phase(trip.start_date, trip.end_date, t),
        "ring_percent": trip_rules.ring_percent(created, trip.start_date, trip.end_date, t),
        "days_until_start": max(0, days_until),
        "created_at": iso(trip.created_at),
        "updated_at": iso(trip.updated_at),
    }


def serialize_trip_status(trip) -> dict:
    return {
        "id": trip.id,
        "status": trip.status,
        "error_message": trip.error_message,
        "generation_id": str(trip.generation_id) if trip.generation_id else None,
        "processing_started_at": iso(trip.processing_started_at),
        "itinerary_stale": trip.itinerary_stale,
        "updated_at": iso(trip.updated_at),
    }
