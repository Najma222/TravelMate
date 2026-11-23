"""Pure (DB-free) trip rules from D13 — phase, scopes and countdown ring.

Phase and ring are computed in APP_TIMEZONE on every read and never stored.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MAX_TRIP_DAYS = 60


def duration_days(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def phase(start_date: date, end_date: date, today: date) -> str:
    if today < start_date:
        return "upcoming"
    if today > end_date:
        return "past"
    return "ongoing"


def ring_percent(created_date: date, start_date: date, end_date: date, today: date) -> float:
    """clamp((today - created) / (start - created) * 100, 0, 100).

    100 when ongoing/past or when the trip was created on its start date.
    """
    if phase(start_date, end_date, today) != "upcoming":
        return 100.0
    span = (start_date - created_date).days
    if span <= 0:
        return 100.0
    elapsed = (today - created_date).days
    pct = (Decimal(elapsed) / Decimal(span) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(min(Decimal(100), max(Decimal(0), pct)))


def in_upcoming_scope(status: str, end_date: date, today: date) -> bool:
    return status != "Cancelled" and end_date >= today


def in_archive_scope(status: str, end_date: date, today: date) -> bool:
    return status == "Cancelled" or end_date < today
