"""Weather payload validation (D6). Weather is only ever stored from n8n input."""
from __future__ import annotations

from app.utils.validators import (FieldError, Validator, aware_datetime, date_, integer, list_of,
                                  number, optional_string)

MAX_DAILY = 16


def _current(v):
    if not isinstance(v, dict):
        raise FieldError("must be an object")
    out = (Validator(v)
           .field("temperature_c", number(-90, 70), required=True)
           .field("weather_code", integer(0, 99), nullable=True)
           .field("observed_at", aware_datetime, nullable=True))
    if out.errors:
        raise FieldError("; ".join(f"{k} {m}" for k, m in out.errors.items()))
    res = out.out
    return {
        "temperature_c": res["temperature_c"],
        "weather_code": res.get("weather_code"),
        "observed_at": res["observed_at"].isoformat() if res.get("observed_at") else None,
    }


def _daily_item(v):
    if not isinstance(v, dict):
        raise FieldError("must be an object")
    out = (Validator(v)
           .field("date", date_, required=True)
           .field("temp_max_c", number(-90, 70), required=True)
           .field("temp_min_c", number(-90, 70), required=True)
           .field("precip_prob_max", number(0, 100), nullable=True)
           .field("weather_code", integer(0, 99), nullable=True))
    if out.errors:
        raise FieldError("; ".join(f"{k} {m}" for k, m in out.errors.items()))
    r = out.out
    hi, lo = r["temp_max_c"], r["temp_min_c"]
    if hi < lo:  # D6: guarantee high >= low
        hi, lo = lo, hi
    return {
        "date": r["date"].isoformat(),
        "temp_max_c": hi,
        "temp_min_c": lo,
        "precip_prob_max": r.get("precip_prob_max"),
        "weather_code": r.get("weather_code"),
    }


def validate_weather_payload(data: dict) -> dict:
    """Return ``{"weather": dict | None, "weather_message": str | None}``."""
    v = (Validator(data)
         .field("location_name", optional_string(100), nullable=True)
         .field("current", _current, nullable=True)
         .field("daily", list_of(_daily_item, max_items=MAX_DAILY), default=list)
         .field("weather_message", optional_string(200), nullable=True))
    out = v.finish()
    daily = sorted(out.get("daily") or [], key=lambda d: d["date"])
    dates = [d["date"] for d in daily]
    if len(dates) != len(set(dates)):
        v.error("daily", "contains duplicate dates")
        v.finish()
    current = out.get("current")
    weather = None
    if daily or current:
        weather = {
            "location_name": out.get("location_name"),
            "current": current,
            "daily": daily,
        }
    return {"weather": weather, "weather_message": out.get("weather_message")}
