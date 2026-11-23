"""Read-only queries backing the internal n8n reminder endpoints."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, case, func, select

from app.extensions import db
from app.models import Booking, PackingItem, Trip, User
from app.utils.dates import iso, today


def _user_block(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "notify_email": u.notify_email,
        "notify_telegram": u.notify_telegram,
        "telegram_chat_id": u.telegram_chat_id,
    }


def _trip_block(t: Trip, t0) -> dict:
    return {
        "id": t.id,
        "origin": t.origin,
        "destination": t.destination,
        "start_date": t.start_date.isoformat(),
        "end_date": t.end_date.isoformat(),
        "status": t.status,
        "days_until_start": (t.start_date - t0).days,
    }


def upcoming_trips(days_ahead: int) -> list[dict]:
    """Non-cancelled trips starting within ``days_ahead`` days (APP_TIMEZONE)."""
    t0 = today()
    unpacked = (select(PackingItem.trip_id, func.count(PackingItem.id).label("unpacked"))
                .where(PackingItem.is_packed.is_(False)).group_by(PackingItem.trip_id).subquery())
    rows = db.session.execute(
        select(Trip, User, func.coalesce(unpacked.c.unpacked, 0))
        .join(User, User.id == Trip.user_id)
        .outerjoin(unpacked, unpacked.c.trip_id == Trip.id)
        .where(Trip.status != "Cancelled",
               Trip.start_date >= t0,
               Trip.start_date <= t0 + timedelta(days=days_ahead))
        .order_by(Trip.start_date, Trip.id)).all()
    return [{**_trip_block(t, t0), "unpacked_items": int(n), "user": _user_block(u)}
            for t, u, n in rows]


def active_trips() -> list[dict]:
    """Ongoing, non-cancelled trips (start_date <= today <= end_date)."""
    t0 = today()
    rows = db.session.execute(
        select(Trip, User).join(User, User.id == Trip.user_id)
        .where(Trip.status != "Cancelled", Trip.start_date <= t0, Trip.end_date >= t0)
        .order_by(Trip.start_date, Trip.id)).all()
    out = []
    for t, u in rows:
        block = _trip_block(t, t0)
        block["day_number"] = (t0 - t.start_date).days + 1
        block["latitude"] = float(t.latitude) if t.latitude is not None else None
        block["longitude"] = float(t.longitude) if t.longitude is not None else None
        block["weather_updated_at"] = iso(t.weather_updated_at)
        out.append({**block, "user": _user_block(u)})
    return out


def booking_gaps(days_ahead: int) -> list[dict]:
    """Upcoming trips lacking a Confirmed hotel and/or a Confirmed transport booking."""
    t0 = today()
    confirmed = Booking.status == "Confirmed"
    agg = (select(
        Booking.trip_id,
        func.count(case((and_(confirmed, Booking.booking_type == "hotel"), 1))).label("hotel"),
        func.count(case((and_(confirmed, Booking.booking_type != "hotel"), 1))).label("transport"),
    ).group_by(Booking.trip_id).subquery())
    rows = db.session.execute(
        select(Trip, User, func.coalesce(agg.c.hotel, 0), func.coalesce(agg.c.transport, 0))
        .join(User, User.id == Trip.user_id)
        .outerjoin(agg, agg.c.trip_id == Trip.id)
        .where(Trip.status != "Cancelled",
               Trip.start_date >= t0,
               Trip.start_date <= t0 + timedelta(days=days_ahead))
        .order_by(Trip.start_date, Trip.id)).all()
    out = []
    for t, u, hotels, transports in rows:
        missing = []
        if not hotels:
            missing.append("hotel")
        if not transports:
            missing.append("transport")
        if missing:
            out.append({**_trip_block(t, t0), "missing": missing, "user": _user_block(u)})
    return out
