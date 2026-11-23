"""Notification validation and serialization (D9)."""
from __future__ import annotations

import re

from app.models import DELIVERY_STATUSES, NOTIFICATION_CHANNELS
from app.schemas.common import iso
from app.utils.validators import (Validator, aware_datetime, boolean, choice, date_, integer,
                                  list_of, string)

TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")
TELEGRAM_CHAT_RE = re.compile(r"^-?\d{1,20}$|^@[A-Za-z0-9_]{5,32}$")


def validate_preferences(data: dict) -> dict:
    return (Validator(data, partial=True)
            .field("notify_email", boolean)
            .field("notify_telegram", boolean)
            .field("telegram_chat_id",
                   string(40, min_len=1, pattern=TELEGRAM_CHAT_RE,
                          pattern_msg="must be a numeric chat id or @username"),
                   nullable=True)
            .finish())


def validate_internal_notification(data: dict) -> dict:
    v = (Validator(data)
         .field("trip_id", integer(1), required=True)
         .field("notification_type",
                string(30, min_len=2, pattern=TYPE_RE,
                       pattern_msg="must be lowercase snake_case (max 30 chars)"),
                required=True)
         .field("message", string(1000, min_len=1), required=True)
         .field("channels", list_of(choice(NOTIFICATION_CHANNELS), max_items=3), default=list)
         .field("scheduled_for", date_)
         .field("delivery_status", choice(DELIVERY_STATUSES), default="pending")
         .field("sent_at", aware_datetime, nullable=True))
    if "channels" in v.out:
        v.out["channels"] = sorted(set(v.out["channels"]))
    return v.finish()


def serialize_notification(n) -> dict:
    return {
        "id": n.id,
        "trip_id": n.trip_id,
        "notification_type": n.notification_type,
        "message": n.message,
        "channels": n.channels or [],
        "scheduled_for": n.scheduled_for.isoformat() if n.scheduled_for else None,
        "sent_at": iso(n.sent_at),
        "delivery_status": n.delivery_status,
        "read_at": iso(n.read_at),
        "is_read": n.read_at is not None,
        "created_at": iso(n.created_at),
    }


def serialize_preferences(user) -> dict:
    return {
        "notify_email": user.notify_email,
        "notify_telegram": user.notify_telegram,
        "telegram_chat_id": user.telegram_chat_id,
    }


def validate_unread_filter(raw: str | None) -> bool | None:
    if raw is None:
        return None
    if raw.lower() in ("1", "true", "yes"):
        return True
    if raw.lower() in ("0", "false", "no"):
        return False
    from app.utils.errors import ValidationError

    raise ValidationError("Invalid unread filter", details={"fields": {"unread": "must be true or false"}})

