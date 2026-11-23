"""Timezone helpers. Business dates (phase, scopes, scheduled_for) use APP_TIMEZONE."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context

DEFAULT_TZ = "Asia/Kolkata"


def app_tz() -> ZoneInfo:
    name = current_app.config.get("APP_TIMEZONE", DEFAULT_TZ) if has_app_context() else DEFAULT_TZ
    return ZoneInfo(name)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    """Current calendar date in APP_TIMEZONE."""
    return now_utc().astimezone(app_tz()).date()


def to_app_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(app_tz()).date()


def end_of_day(d: date) -> datetime:
    """Last instant (exclusive bound) of ``d`` in APP_TIMEZONE, as aware datetime."""
    return datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=app_tz())


def iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return dt.isoformat()


def trip_day_date(start_date: date, day_number: int) -> date:
    """D7: a day's calendar date is computed, never stored."""
    return start_date + timedelta(days=day_number - 1)
