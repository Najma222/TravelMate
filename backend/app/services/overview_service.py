"""Trip overview (≤ 8 queries incl. the auth lookup) and the user dashboard."""
from __future__ import annotations

from sqlalchemy import and_, case, func, or_, select

from app.extensions import db
from app.models import Booking, Expense, Itinerary, Notification, PackingItem, Trip, TripDay, TripStop
from app.schemas.booking import serialize_booking
from app.schemas.dashboard import serialize_trip_card
from app.schemas.expense import serialize_budget
from app.schemas.itinerary import serialize_itinerary_item
from app.schemas.notification import serialize_notification
from app.schemas.trip import serialize_trip
from app.schemas.trip_day import serialize_day
from app.schemas.trip_stop import serialize_stop
from app.services import budget as budget_svc
from app.services import trip_rules
from app.services.ownership import get_owned_trip
from app.services.weather import build_weather_response
from app.utils.dates import today


def build_overview(user_id: int, trip_id: int) -> dict:
    t0 = today()
    trip = get_owned_trip(user_id, trip_id)                                              # q1
    max_day = trip_rules.duration_days(trip.start_date, trip.end_date)
    stops = list(db.session.execute(select(TripStop).where(TripStop.trip_id == trip.id)
                                    .order_by(TripStop.position)).scalars())             # q2
    days = {d.day_number: d for d in db.session.execute(
        select(TripDay).where(TripDay.trip_id == trip.id,
                              TripDay.day_number <= max_day)).scalars()}                 # q3
    items = list(db.session.execute(
        select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.day_number <= max_day)
        .order_by(Itinerary.day_number, Itinerary.sort_order,
                  Itinerary.start_time.asc().nulls_last(), Itinerary.id)).scalars())     # q4
    budget = budget_svc.compute_budget(trip.budget, budget_svc.aggregate_rows([trip.id])[trip.id])  # q5
    booking_rows = db.session.execute(
        select(Booking, Expense.id).outerjoin(Expense, Expense.booking_id == Booking.id)
        .where(Booking.trip_id == trip.id)
        .order_by(Booking.start_at.asc().nulls_last(), Booking.id)).all()                # q6
    total_items, packed = db.session.execute(
        select(func.count(PackingItem.id),
               func.count(case((PackingItem.is_packed.is_(True), 1))))
        .where(PackingItem.trip_id == trip.id)).one()                                    # q7

    stop_by_id = {s.id: s for s in stops}
    per_day: dict[int, list] = {}
    for it in items:
        per_day.setdefault(it.day_number, []).append(it)

    phase = trip_rules.phase(trip.start_date, trip.end_date, t0)
    focus_day = (t0 - trip.start_date).days + 1 if phase == "ongoing" else 1
    day_cards = []
    for n in range(1, max_day + 1):
        d = days.get(n)
        card = serialize_day(trip, n, d, stop_by_id.get(d.stop_id) if d and d.stop_id else None)
        card["activity_count"] = len(per_day.get(n, []))
        day_cards.append(card)

    status_counts: dict[str, int] = {}
    for b, _ in booking_rows:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1

    return {
        "trip": serialize_trip(trip, today_date=t0),
        "weather": build_weather_response(trip),
        "budget": serialize_budget(budget, trip.currency),
        "stops": [serialize_stop(s) for s in stops],
        "itinerary": {
            "total_activities": len(items),
            "focus_day": focus_day if items else None,
            "focus_items": [serialize_itinerary_item(i) for i in per_day.get(focus_day, [])],
            "days": day_cards,
        },
        "bookings": {
            "items": [serialize_booking(b, eid) for b, eid in booking_rows],
            "status_counts": status_counts,
        },
        "packing": {
            "total": int(total_items),
            "packed": int(packed),
            "percent": round(int(packed) * 100 / int(total_items), 1) if total_items else 0.0,
        },
    }


def build_dashboard(user) -> dict:
    t0 = today()
    not_cancelled = Trip.status != "Cancelled"
    counts = db.session.execute(
        select(
            func.count(case((and_(not_cancelled, Trip.start_date > t0), 1))),
            func.count(case((and_(not_cancelled, Trip.start_date <= t0, Trip.end_date >= t0), 1))),
            func.count(case((and_(not_cancelled, Trip.end_date < t0), 1))),
            func.count(case((Trip.status == "Cancelled", 1))),
            func.count(Trip.id),
        ).where(Trip.user_id == user.id)).one()
    upcoming = list(db.session.execute(
        select(Trip).where(Trip.user_id == user.id, not_cancelled, Trip.end_date >= t0)
        .order_by(Trip.start_date, Trip.id).limit(5)).scalars())
    past = list(db.session.execute(
        select(Trip).where(Trip.user_id == user.id, or_(Trip.status == "Cancelled", Trip.end_date < t0))
        .order_by(Trip.end_date.desc(), Trip.id.desc()).limit(5)).scalars())
    trip_ids = [t.id for t in upcoming + past]
    rows = budget_svc.aggregate_rows(trip_ids)
    budgets = {t.id: budget_svc.compute_budget(t.budget, rows[t.id]) for t in upcoming + past}
    recent = list(db.session.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(5)).scalars())
    unread = db.session.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))).scalar_one()
    pending_bookings = db.session.execute(
        select(func.count(Booking.id)).join(Trip, Trip.id == Booking.trip_id)
        .where(Trip.user_id == user.id, not_cancelled, Trip.end_date >= t0,
               Booking.status.in_(("Not Booked", "Pending")))).scalar_one()

    upcoming_cards = [serialize_trip_card(t, budgets[t.id], t0) for t in upcoming]
    return {
        "user": {"id": user.id, "name": user.name, "avatar_url": user.avatar_url},
        "counts": {
            "upcoming": counts[0], "ongoing": counts[1], "past": counts[2],
            "cancelled": counts[3], "total": counts[4],
        },
        "next_trip": upcoming_cards[0] if upcoming_cards else None,
        "upcoming_trips": upcoming_cards,
        "recent_trips": [serialize_trip_card(t, budgets[t.id], t0) for t in past],
        "notifications": {
            "unread_count": unread,
            "recent": [serialize_notification(n) for n in recent],
        },
        "pending_bookings": pending_bookings,
    }
