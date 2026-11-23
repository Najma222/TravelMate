"""Weather (D6): WMO mapping, storage and the public weather response.

Weather is never fabricated: it only comes from n8n (callback or internal PUT). When
nothing is stored the response says so explicitly.
"""
from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Trip
from app.utils.dates import iso, now_utc
from app.utils.errors import NotFound

DEFAULT_UNAVAILABLE_MESSAGE = "Forecast not available yet"

# WMO weather interpretation codes (Open-Meteo convention).
WMO_LABELS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def condition_label(code) -> str:
    if code is None:
        return "Unknown"
    try:
        return WMO_LABELS.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def min_forecast_temp(weather: dict | None) -> float | None:
    if not weather:
        return None
    lows = [d.get("temp_min_c") for d in weather.get("daily") or [] if d.get("temp_min_c") is not None]
    return min(lows) if lows else None


def build_weather_response(trip) -> dict:
    w = trip.weather or {}
    daily = w.get("daily") or []
    current = w.get("current")
    if not daily and not current:
        return {
            "available": False,
            "daily": [],
            "message": trip.weather_message or DEFAULT_UNAVAILABLE_MESSAGE,
        }
    out_daily = []
    for d in daily:
        hi, lo = d.get("temp_max_c"), d.get("temp_min_c")
        if hi is not None and lo is not None and hi < lo:
            hi, lo = lo, hi  # guarantee high_c >= low_c even for legacy rows
        out_daily.append({
            "date": d.get("date"),
            "high_c": hi,
            "low_c": lo,
            "precip_prob_max": d.get("precip_prob_max"),
            "weather_code": d.get("weather_code"),
            "condition": condition_label(d.get("weather_code")),
        })
    out = {
        "available": True,
        "location_name": w.get("location_name"),
        "current": None,
        "daily": out_daily,
        "message": trip.weather_message,
        "updated_at": iso(trip.weather_updated_at),
    }
    if current:
        out["current"] = {
            "temperature_c": current.get("temperature_c"),
            "weather_code": current.get("weather_code"),
            "condition": condition_label(current.get("weather_code")),
            "observed_at": current.get("observed_at"),
        }
    return out


def apply_weather(trip, parsed: dict) -> None:
    """Apply validated weather to a trip (caller owns the transaction)."""
    trip.weather = parsed.get("weather")  # None clears a stale forecast
    trip.weather_updated_at = now_utc()
    if "weather_message" in parsed:
        trip.weather_message = parsed.get("weather_message")


def update_trip_weather(trip_id: int, parsed: dict) -> Trip:
    """Internal PUT /internal/trips/{id}/weather."""
    try:
        trip = db.session.execute(
            select(Trip).where(Trip.id == trip_id).with_for_update()
        ).scalar_one_or_none()
        if trip is None:
            raise NotFound("Trip not found")
        apply_weather(trip, parsed)
        db.session.commit()
        return trip
    except Exception:
        db.session.rollback()
        raise
