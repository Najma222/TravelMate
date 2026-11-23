"""Trip lifecycle, stops, places and the stuck-generation sweeper."""
from __future__ import annotations

from datetime import timedelta

from flask import current_app
from sqlalchemy import and_, delete, func, or_, select, text, update

from app.extensions import db
from app.models import Itinerary, Trip, TripStop
from app.schemas.trip import TRIP_FIELDS_AFFECTING_GENERATION, check_dates
from app.services import audit, packing_seed, trip_rules
from app.services.ownership import get_owned_child, get_owned_trip
from app.utils.dates import now_utc, today
from app.utils.errors import Conflict, ValidationError

DUPLICATE_WINDOW_SECONDS = 10
SWEEP_MESSAGE = "Generation timed out. Please retry."


def _rollback_on_error(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            db.session.rollback()
            raise
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# --------------------------------------------------------------------------- CRUD

@_rollback_on_error
def create_trip(user_id: int, data: dict) -> Trip:
    # Serialise concurrent creates for the same user so duplicate detection is race-free.
    db.session.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
                       {"k1": 7301, "k2": int(user_id) % 2_147_483_647})
    since = now_utc() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    dup = db.session.execute(
        select(Trip.id).where(
            Trip.user_id == user_id,
            Trip.origin == data["origin"],
            Trip.destination == data["destination"],
            Trip.start_date == data["start_date"],
            Trip.end_date == data["end_date"],
            Trip.created_at >= since,
        ).limit(1)
    ).scalar_one_or_none()
    if dup is not None:
        raise Conflict("An identical trip was just created", code="duplicate_submission",
                       details={"existing_trip_id": dup})
    trip = Trip(user_id=user_id, status="Draft", **data)
    db.session.add(trip)
    db.session.flush()
    packing_seed.seed_default_items(trip.id)
    db.session.commit()
    return trip


def list_trips(user_id: int, scope: str, page: int, per_page: int) -> tuple[list[Trip], int]:
    t = today()
    stmt = select(Trip).where(Trip.user_id == user_id)
    if scope == "upcoming":
        stmt = stmt.where(Trip.status != "Cancelled", Trip.end_date >= t)
        order = (Trip.start_date.asc(), Trip.id.asc())
    elif scope == "archive":
        stmt = stmt.where(or_(Trip.status == "Cancelled", Trip.end_date < t))
        order = (Trip.end_date.desc(), Trip.id.desc())
    else:
        order = (Trip.created_at.desc(), Trip.id.desc())
    total = db.session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = db.session.execute(
        stmt.order_by(*order).offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()
    return list(items), total


def get_trip(user_id: int, trip_id: int) -> Trip:
    return get_owned_trip(user_id, trip_id)


@_rollback_on_error
def update_trip(user_id: int, trip_id: int, validator) -> Trip:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    data = validator.out
    start = data.get("start_date", trip.start_date)
    end = data.get("end_date", trip.end_date)
    check_dates(validator, start, end,
                start_changed="start_date" in data and data["start_date"] != trip.start_date)
    validator.finish()
    if trip.status == "Processing":
        raise Conflict("Trip is being generated; try again when generation finishes",
                       details={"status": trip.status})
    if trip.status == "Cancelled":
        raise Conflict("Cancelled trips cannot be edited", details={"status": trip.status})
    changed = {k for k, v in data.items() if getattr(trip, k) != v}
    for k, v in data.items():
        setattr(trip, k, v)
    if changed & TRIP_FIELDS_AFFECTING_GENERATION and trip.status == "Completed":
        trip.itinerary_stale = True
    db.session.commit()
    return trip


@_rollback_on_error
def delete_trip(user_id: int, trip_id: int) -> str | None:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    cover = trip.cover_image_url
    db.session.execute(delete(Trip).where(Trip.id == trip.id))
    db.session.commit()
    return cover


@_rollback_on_error
def cancel_trip(user_id: int, trip_id: int) -> Trip:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    if trip.status == "Cancelled":
        raise Conflict("Trip is already cancelled", details={"status": trip.status})
    previous = trip.status
    trip.status = "Cancelled"
    db.session.commit()
    audit.record("trip_cancelled", "success", actor="user", user_id=user_id, trip_id=trip.id,
                 meta={"previous_status": previous})
    return trip


@_rollback_on_error
def set_cover(user_id: int, trip_id: int, url: str) -> tuple[Trip, str | None]:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    old = trip.cover_image_url
    trip.cover_image_url = url
    db.session.commit()
    return trip, old


# --------------------------------------------------------------------------- sweeper

def _sweep_stmt(trip_id: int | None = None):
    minutes = current_app.config["GENERATION_TIMEOUT_MINUTES"]
    cutoff = now_utc() - timedelta(minutes=minutes)
    cond = and_(Trip.status == "Processing",
                or_(Trip.processing_started_at < cutoff, Trip.processing_started_at.is_(None)))
    if trip_id is not None:
        cond = and_(cond, Trip.id == trip_id)
    return (update(Trip).where(cond)
            .values(status="Failed", error_message=SWEEP_MESSAGE)
            .returning(Trip.id, Trip.user_id)
            .execution_options(synchronize_session=False))


@_rollback_on_error
def sweep_stuck(trip_id: int | None = None) -> list[int]:
    """Atomically fail Processing trips older than GENERATION_TIMEOUT_MINUTES.

    A single conditional UPDATE: concurrent sweeps/callbacks cannot double-transition.
    """
    rows = db.session.execute(_sweep_stmt(trip_id)).all()
    db.session.commit()
    for tid, uid in rows:
        audit.record("generation_timed_out", "failure", actor="system", user_id=uid, trip_id=tid)
    return [r[0] for r in rows]


def get_status(user_id: int, trip_id: int) -> Trip:
    trip = get_owned_trip(user_id, trip_id)
    if trip.status == "Processing":
        if sweep_stuck(trip.id):
            db.session.expire_all()
            trip = get_owned_trip(user_id, trip_id)
    return trip


# --------------------------------------------------------------------------- stops

def list_stops(trip_id: int) -> list[TripStop]:
    return list(db.session.execute(
        select(TripStop).where(TripStop.trip_id == trip_id).order_by(TripStop.position)
    ).scalars())


@_rollback_on_error
def add_stop(user_id: int, trip_id: int, data: dict) -> TripStop:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    count = db.session.execute(
        select(func.count(TripStop.id)).where(TripStop.trip_id == trip.id)).scalar_one()
    if count >= 50:
        raise Conflict("A trip may have at most 50 stops")
    max_pos = db.session.execute(
        select(func.coalesce(func.max(TripStop.position), 0)).where(TripStop.trip_id == trip.id)
    ).scalar_one()
    stop = TripStop(trip_id=trip.id, position=max_pos + 1, source="user", **data)
    db.session.add(stop)
    db.session.commit()
    return stop


@_rollback_on_error
def update_stop(user_id: int, stop_id: int, data: dict) -> TripStop:
    stop, _trip = get_owned_child(TripStop, user_id, stop_id, label="Stop", for_update=True)
    for k, v in data.items():
        setattr(stop, k, v)
    if data:
        stop.source = "user"  # an edited stop is user-owned and survives regeneration
    db.session.commit()
    return stop


def _renumber(trip_id: int) -> None:
    stops = list_stops(trip_id)
    for i, s in enumerate(stops, start=1):
        s.position = i


@_rollback_on_error
def delete_stop(user_id: int, stop_id: int) -> None:
    stop, trip = get_owned_child(TripStop, user_id, stop_id, label="Stop")
    get_owned_trip(user_id, trip.id, for_update=True)
    db.session.delete(stop)
    db.session.flush()
    _renumber(trip.id)
    db.session.commit()


@_rollback_on_error
def reorder_stops(user_id: int, trip_id: int, stop_ids: list[int]) -> list[TripStop]:
    trip = get_owned_trip(user_id, trip_id, for_update=True)
    stops = list_stops(trip.id)
    current = {s.id: s for s in stops}
    if len(stop_ids) != len(set(stop_ids)) or set(stop_ids) != set(current):
        raise ValidationError("stop_ids must list every stop of the trip exactly once",
                              details={"fields": {"stop_ids": "must be a permutation of the trip's stop ids"}})
    for pos, sid in enumerate(stop_ids, start=1):
        current[sid].position = pos  # unique(trip_id, position) is DEFERRED: checked at commit
    db.session.commit()
    return list_stops(trip.id)


# --------------------------------------------------------------------------- places

def get_places(user_id: int, trip_id: int) -> tuple[Trip, list[TripStop], list[Itinerary]]:
    """Places come only from stored stops/itinerary rows — never invented."""
    trip = get_owned_trip(user_id, trip_id)
    max_day = trip_rules.duration_days(trip.start_date, trip.end_date)
    stops = list_stops(trip.id)
    items = list(db.session.execute(
        select(Itinerary)
        .where(Itinerary.trip_id == trip.id, Itinerary.day_number <= max_day,
               or_(Itinerary.location.is_not(None), Itinerary.latitude.is_not(None)))
        .order_by(Itinerary.day_number, Itinerary.sort_order, Itinerary.start_time, Itinerary.id)
    ).scalars())
    return trip, stops, items
