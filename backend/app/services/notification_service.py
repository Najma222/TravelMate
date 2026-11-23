"""Notifications (D9): user inbox, preferences and the internal delivery record.

Delivery semantics: the backend records what n8n reports. Deduplication is per
``(trip_id, notification_type, scheduled_for)``; a ``sent`` row cannot be re-recorded
(409), a ``failed``/``pending`` row is updated (200) so n8n can retry. This gives
at-most-once *recording*, not exactly-once delivery: if n8n sends an email and crashes
before reporting, the external send may still be repeated.
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import Notification, Trip, User
from app.services import audit
from app.utils.dates import now_utc, today
from app.utils.errors import Conflict, NotFound, ValidationError


def list_for_user(user_id: int, unread: bool | None, page: int, per_page: int):
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread is True:
        stmt = stmt.where(Notification.read_at.is_(None))
    elif unread is False:
        stmt = stmt.where(Notification.read_at.is_not(None))
    total = db.session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = list(db.session.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * per_page).limit(per_page)).scalars())
    return items, total, unread_count(user_id)


def unread_count(user_id: int) -> int:
    return db.session.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))).scalar_one()


def mark_read(user_id: int, notification_id: int) -> Notification:
    try:
        n = db.session.execute(
            select(Notification).where(Notification.id == notification_id,
                                       Notification.user_id == user_id)).scalar_one_or_none()
        if n is None:
            raise NotFound("Notification not found")
        if n.read_at is None:
            n.read_at = now_utc()
        db.session.commit()
        return n
    except Exception:
        db.session.rollback()
        raise


def mark_all_read(user_id: int) -> int:
    try:
        res = db.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=func.now())
            .execution_options(synchronize_session=False))
        db.session.commit()
        return res.rowcount or 0
    except Exception:
        db.session.rollback()
        raise


def update_preferences(user: User, data: dict) -> User:
    try:
        for k, v in data.items():
            setattr(user, k, v)
        if user.notify_telegram and not user.telegram_chat_id:
            raise ValidationError("telegram_chat_id is required to enable Telegram notifications",
                                  details={"fields": {"telegram_chat_id": "is required when notify_telegram is true"}})
        db.session.commit()
        return user
    except Exception:
        db.session.rollback()
        raise


def record_delivery(data: dict) -> tuple[Notification, int]:
    """Internal: insert, or update a failed/pending row. Returns (row, http_status)."""
    try:
        trip = db.session.execute(select(Trip).where(Trip.id == data["trip_id"])).scalar_one_or_none()
        if trip is None:
            raise NotFound("Trip not found")
        scheduled_for = data.get("scheduled_for") or today()
        status = data["delivery_status"]
        sent_at = data.get("sent_at")
        if status == "sent" and sent_at is None:
            sent_at = now_utc()
        values = {
            "trip_id": trip.id,
            "user_id": trip.user_id,
            "notification_type": data["notification_type"],
            "message": data["message"],
            "channels": data.get("channels") or [],
            "scheduled_for": scheduled_for,
            "delivery_status": status,
            "sent_at": sent_at,
        }
        inserted = db.session.execute(
            insert(Notification).values(**values)
            .on_conflict_do_nothing(constraint="uq_notifications_trip_id_notification_type_scheduled_for")
            .returning(Notification.id)).first()
        if inserted is not None:
            db.session.commit()
            return db.session.get(Notification, inserted[0]), 201

        existing = db.session.execute(
            select(Notification).where(
                Notification.trip_id == trip.id,
                Notification.notification_type == values["notification_type"],
                Notification.scheduled_for == scheduled_for).with_for_update()).scalar_one()
        if existing.delivery_status == "sent":
            db.session.rollback()
            raise Conflict("Notification already sent", details={"notification_id": existing.id})
        existing.message = values["message"]
        existing.channels = values["channels"]
        existing.delivery_status = status
        existing.sent_at = sent_at
        db.session.commit()
        audit.record("notification_retry", "success", actor="n8n", trip_id=trip.id,
                     meta={"notification_id": existing.id, "delivery_status": status})
        return existing, 200
    except Exception:
        db.session.rollback()
        raise
