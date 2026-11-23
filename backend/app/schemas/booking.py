"""Booking validation and serialization (D10)."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from app.models import BOOKING_STATUSES, BOOKING_TYPES
from app.schemas.common import fmt_money, iso
from app.utils.validators import (Validator, choice, date_, datetime_, iana_timezone, money,
                                  optional_string)


def _fields(v: Validator, creating: bool) -> Validator:
    return (v.field("booking_type", choice(BOOKING_TYPES, case_insensitive=True), required=creating)
             .field("provider", optional_string(100), nullable=True)
             .field("booking_reference", optional_string(60), nullable=True)
             .field("amount", money())
             .field("booked_on", date_, nullable=True)
             .field("status", choice(BOOKING_STATUSES, case_insensitive=True))
             .field("from_location", optional_string(100), nullable=True)
             .field("to_location", optional_string(100), nullable=True)
             .field("start_at", datetime_, nullable=True)
             .field("end_at", datetime_, nullable=True)
             .field("start_tz", iana_timezone, nullable=True)
             .field("end_tz", iana_timezone, nullable=True)
             .field("notes", optional_string(500), nullable=True))


def localize(v: Validator, dt_key: str, tz_key: str, tz_fallback: str | None) -> None:
    """Naive datetimes are interpreted in the given IANA zone; otherwise rejected."""
    dt = v.out.get(dt_key)
    if dt is None or dt.tzinfo is not None:
        return
    tz = v.out.get(tz_key) or tz_fallback
    if not tz:
        v.error(dt_key, "must include a timezone offset or provide " + tz_key)
        return
    v.out[dt_key] = dt.replace(tzinfo=ZoneInfo(tz))


def validate_booking_create(data: dict) -> dict:
    v = _fields(Validator(data), creating=True)
    v.out.setdefault("amount", money()("0"))
    v.out.setdefault("status", "Not Booked")
    localize(v, "start_at", "start_tz", None)
    localize(v, "end_at", "end_tz", None)
    s, e = v.out.get("start_at"), v.out.get("end_at")
    if s and e and getattr(s, "tzinfo", None) and getattr(e, "tzinfo", None) and e < s:
        v.error("end_at", "must be at or after start_at")
    return v.finish()


def validate_booking_update(data: dict, existing) -> dict:
    v = _fields(Validator(data, partial=True), creating=False)
    localize(v, "start_at", "start_tz", existing.start_tz)
    localize(v, "end_at", "end_tz", existing.end_tz)
    s = v.out.get("start_at", existing.start_at)
    e = v.out.get("end_at", existing.end_at)
    if s and e and s.tzinfo and e.tzinfo and e < s:
        v.error("end_at", "must be at or after start_at")
    return v.finish()


def serialize_booking(b, expense_id: int | None = None) -> dict:
    return {
        "id": b.id,
        "trip_id": b.trip_id,
        "booking_type": b.booking_type,
        "provider": b.provider,
        "booking_reference": b.booking_reference,
        "amount": fmt_money(b.amount),
        "booked_on": b.booked_on.isoformat() if b.booked_on else None,
        "status": b.status,
        "from_location": b.from_location,
        "to_location": b.to_location,
        "start_at": iso(b.start_at),
        "end_at": iso(b.end_at),
        "start_tz": b.start_tz,
        "end_tz": b.end_tz,
        "notes": b.notes,
        "linked_expense_id": expense_id,
        "created_at": iso(b.created_at),
        "updated_at": iso(b.updated_at),
    }
