"""Idempotent n8n generation callback (AGENTS.md §3).

Flow:
1. (blueprint) ``@internal_only`` verified ``X-Webhook-Secret`` with ``hmac.compare_digest``.
2. ``SELECT ... FOR UPDATE`` the trip row.
3. Ignore (200) when Cancelled, stale ``generation_id`` or not Processing.
4. Validate envelope; invalid => mark *this* generation Failed in a separate transaction, 400.
5. Completed: drop invalid activity rows; zero valid => Failed ("No valid places found").
   Otherwise in ONE transaction replace itineraries, trip_days, unconfirmed non-booking
   expenses and generated stops — preserving confirmed/booking expenses and user stops.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select, update

from app.extensions import db
from app.models import Expense, Itinerary, Trip, TripDay, TripStop
from app.schemas.callback import (clean_activity, clean_day, clean_expense, clean_stop,
                                  parse_generation_id, validate_callback_envelope)
from app.schemas.trip_day import default_day_title
from app.services import audit, packing_seed, trip_rules, weather
from app.utils.errors import NotFound, ValidationError

log = logging.getLogger("travelmate.callback")

NO_VALID_PLACES = "No valid places found"
INVALID_PAYLOAD = "Itinerary service returned an invalid result. Please retry."


@dataclass
class CallbackResult:
    body: dict
    status_code: int = 200


def _ignored(trip: Trip, reason: str, gid) -> CallbackResult:
    db.session.rollback()  # release the row lock
    audit.record("callback_ignored", "ignored", actor="n8n", user_id=trip.user_id,
                 trip_id=trip.id, meta={"reason": reason, "generation_id": str(gid)})
    return CallbackResult({"ignored": True, "reason": reason})


def _fail_generation(trip_id: int, gid, message: str) -> bool:
    """Separate transaction: fail the trip only if this generation is still Processing."""
    try:
        res = db.session.execute(
            update(Trip)
            .where(Trip.id == trip_id, Trip.generation_id == gid, Trip.status == "Processing")
            .values(status="Failed", error_message=message[:500])
            .returning(Trip.id)
            .execution_options(synchronize_session=False)
        ).first()
        db.session.commit()
        return res is not None
    except Exception:
        db.session.rollback()
        raise


def process_callback(trip_id: int, data: dict) -> CallbackResult:
    gid = parse_generation_id(data)
    try:
        trip = db.session.execute(
            select(Trip).where(Trip.id == trip_id).with_for_update()
        ).scalar_one_or_none()
        if trip is None:
            db.session.rollback()
            raise NotFound("Trip not found")
        if trip.status == "Cancelled":
            return _ignored(trip, "cancelled", gid)
        if trip.generation_id != gid:
            return _ignored(trip, "stale_generation", gid)
        if trip.status != "Processing":
            return _ignored(trip, "not_processing", gid)

        try:
            envelope = validate_callback_envelope(data)
        except ValidationError as err:
            db.session.rollback()
            _fail_generation(trip_id, gid, INVALID_PAYLOAD)
            audit.record("callback_invalid", "failure", actor="n8n", user_id=trip.user_id,
                         trip_id=trip_id, meta={"fields": list((err.details.get("fields") or {}).keys())})
            raise

        if envelope["status"] == "Failed":
            message = envelope.get("error_message") or "Itinerary generation failed"
            trip.status = "Failed"
            trip.error_message = message[:500]
            db.session.commit()
            audit.record("generation_failed", "failure", actor="n8n", user_id=trip.user_id,
                         trip_id=trip_id, meta={"source": "n8n"})
            return CallbackResult({"status": "Failed", "trip_id": trip_id})

        return _apply_completed(trip, envelope)
    except Exception:
        db.session.rollback()
        raise


def _apply_completed(trip: Trip, envelope: dict) -> CallbackResult:
    max_day = trip_rules.duration_days(trip.start_date, trip.end_date)
    activities = [a for a in (clean_activity(r, max_day) for r in envelope["itinerary"]) if a]
    dropped = len(envelope["itinerary"]) - len(activities)
    if not activities:
        trip.status = "Failed"
        trip.error_message = NO_VALID_PLACES
        db.session.commit()
        audit.record("generation_failed", "failure", actor="n8n", user_id=trip.user_id,
                     trip_id=trip.id, meta={"reason": "no_valid_places", "dropped": dropped})
        return CallbackResult({"status": "Failed", "trip_id": trip.id, "error_message": NO_VALID_PLACES})

    expenses = [e for e in (clean_expense(r) for r in envelope["expenses"]) if e]
    days = {}
    for d in (clean_day(r, max_day) for r in envelope["days"]):
        if d and d["day_number"] not in days:
            days[d["day_number"]] = d
    stops = []
    seen = set()
    for s in (clean_stop(r) for r in envelope["stops"]):
        if s and s["name"].lower() not in seen:
            seen.add(s["name"].lower())
            stops.append(s)

    tid = trip.id
    # --- replace generated stops (user stops preserved, generated appended after them)
    db.session.execute(delete(TripStop).where(TripStop.trip_id == tid, TripStop.source == "generated"))
    user_stops = list(db.session.execute(
        select(TripStop).where(TripStop.trip_id == tid).order_by(TripStop.position)).scalars())
    for i, s in enumerate(user_stops, start=1):
        s.position = i
    next_pos = len(user_stops) + 1
    new_stops = []
    for s in stops:
        stop = TripStop(trip_id=tid, position=next_pos, source="generated", **s)
        db.session.add(stop)
        new_stops.append(stop)
        next_pos += 1
    db.session.flush()
    stop_by_name = {s.name.lower(): s.id for s in user_stops + new_stops}

    # --- replace itineraries
    db.session.execute(delete(Itinerary).where(Itinerary.trip_id == tid))
    per_day_counter: dict[int, int] = {}
    for a in activities:
        order = a.pop("sort_order")
        if order is None:
            order = per_day_counter.get(a["day_number"], 0)
        per_day_counter[a["day_number"]] = max(per_day_counter.get(a["day_number"], 0), order) + 1
        db.session.add(Itinerary(trip_id=tid, sort_order=order, is_edited=False, **a))

    # --- replace trip days (every day 1..N gets a row; default title "Day N")
    db.session.execute(delete(TripDay).where(TripDay.trip_id == tid))
    for n in range(1, max_day + 1):
        d = days.get(n) or {}
        db.session.add(TripDay(
            trip_id=tid, day_number=n,
            title=d.get("title") or default_day_title(n),
            summary=d.get("summary"),
            stop_id=stop_by_name.get((d.get("stop_name") or "").lower()),
        ))

    # --- replace unconfirmed, non-booking expenses (confirmed + booking-linked preserved)
    db.session.execute(delete(Expense).where(
        Expense.trip_id == tid, Expense.is_confirmed.is_(False), Expense.booking_id.is_(None)))
    for e in expenses:
        db.session.add(Expense(trip_id=tid, is_confirmed=False, source="n8n",
                               expense_date=trip.start_date, **e))

    # --- trip-level fields
    if "weather" in envelope:
        weather.apply_weather(trip, envelope["weather"])
    for k in ("latitude", "longitude", "hero_quote", "hero_quote_author"):
        if envelope.get(k) is not None:
            setattr(trip, k, envelope[k])
    trip.status = "Completed"
    trip.error_message = None
    trip.itinerary_stale = False

    jacket_added = packing_seed.ensure_jacket(tid, weather.min_forecast_temp(trip.weather))
    db.session.commit()
    audit.record("generation_completed", "success", actor="n8n", user_id=trip.user_id, trip_id=tid,
                 meta={"activities": len(activities), "dropped": dropped,
                       "expenses": len(expenses), "stops": len(new_stops)})
    return CallbackResult({
        "status": "Completed",
        "trip_id": tid,
        "activities_saved": len(activities),
        "activities_dropped": dropped,
        "expenses_saved": len(expenses),
        "stops_saved": len(new_stops),
        "jacket_added": jacket_added,
    })

