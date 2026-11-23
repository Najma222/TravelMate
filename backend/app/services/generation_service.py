"""POST /trips/{id}/generate — atomic claim, commit, then call n8n (AGENTS.md §3)."""
from __future__ import annotations

import uuid

from flask import current_app
from sqlalchemy import func, select, update

from app.extensions import db
from app.models import Trip, TripStop
from app.services import audit, n8n_client, trip_rules
from app.utils.errors import Conflict, NotFound, UpstreamError
from app.utils.money import fmt_money

CLAIMABLE = ("Draft", "Completed", "Failed")
START_FAILED_MESSAGE = "Could not start itinerary generation. Please retry."


def _claim(trip_id: int, user_id: int, gid: uuid.UUID) -> bool:
    stmt = (update(Trip)
            .where(Trip.id == trip_id, Trip.user_id == user_id, Trip.status.in_(CLAIMABLE))
            .values(status="Processing", generation_id=gid,
                    processing_started_at=func.now(), error_message=None,
                    itinerary_stale=False)
            .returning(Trip.id)
            .execution_options(synchronize_session=False))
    return db.session.execute(stmt).first() is not None


def build_payload(trip: Trip, stops: list[TripStop]) -> dict:
    base = current_app.config["BACKEND_INTERNAL_URL"].rstrip("/")
    return {
        "trip_id": trip.id,
        "generation_id": str(trip.generation_id),
        "callback_url": f"{base}/api/v1/internal/trips/{trip.id}/result",
        "weather_url": f"{base}/api/v1/internal/trips/{trip.id}/weather",
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
        "latitude": float(trip.latitude) if trip.latitude is not None else None,
        "longitude": float(trip.longitude) if trip.longitude is not None else None,
        "user_stops": [
            {"name": s.name, "position": s.position,
             "latitude": float(s.latitude) if s.latitude is not None else None,
             "longitude": float(s.longitude) if s.longitude is not None else None}
            for s in stops if s.source == "user"
        ],
    }


def start_generation(user_id: int, trip_id: int) -> Trip:
    gid = uuid.uuid4()
    try:
        claimed = _claim(trip_id, user_id, gid)
        if not claimed:
            current = db.session.execute(
                select(Trip.status).where(Trip.id == trip_id, Trip.user_id == user_id)
            ).scalar_one_or_none()
            db.session.rollback()
            if current is None:
                raise NotFound("Trip not found")
            raise Conflict(f"Trip cannot be generated while {current}",
                           details={"status": current})
        # Commit BEFORE calling n8n: the callback may arrive before this request returns.
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    trip = db.session.execute(select(Trip).where(Trip.id == trip_id)).scalar_one()
    stops = list(db.session.execute(
        select(TripStop).where(TripStop.trip_id == trip_id).order_by(TripStop.position)
    ).scalars())
    payload = build_payload(trip, stops)
    db.session.rollback()  # end the read transaction; do not hold it during the HTTP call

    try:
        n8n_client.trigger_generation(payload)
    except n8n_client.N8NError as err:
        _mark_start_failed(trip_id, gid)
        audit.record("generation_failed", "failure", actor="user", user_id=user_id,
                     trip_id=trip_id, meta={"reason": err.reason, "upstream_status": err.status})
        raise UpstreamError("Itinerary service is unavailable. Please retry.",
                            details={"reason": err.reason})

    audit.record("generation_started", "success", actor="user", user_id=user_id, trip_id=trip_id,
                 meta={"generation_id": str(gid)})
    return db.session.execute(select(Trip).where(Trip.id == trip_id)).scalar_one()


def _mark_start_failed(trip_id: int, gid: uuid.UUID) -> None:
    """New transaction: fail only *this* generation if it is still Processing."""
    try:
        db.session.execute(
            update(Trip)
            .where(Trip.id == trip_id, Trip.generation_id == gid, Trip.status == "Processing")
            .values(status="Failed", error_message=START_FAILED_MESSAGE)
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
