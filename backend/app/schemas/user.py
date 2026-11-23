"""User/profile validation and serialization."""
from __future__ import annotations

import json

from app.schemas.common import iso
from app.utils.validators import FieldError, Validator, json_safe, string

UI_PREFS_MAX_BYTES = 4096


def ui_prefs(v):
    if not isinstance(v, dict):
        raise FieldError("must be an object")
    out = json_safe(v, max_depth=3)
    if len(json.dumps(out)) > UI_PREFS_MAX_BYTES:
        raise FieldError(f"must be at most {UI_PREFS_MAX_BYTES} bytes when encoded")
    return out


def validate_profile_update(data: dict) -> dict:
    return (Validator(data, partial=True)
            .field("name", string(80, min_len=1))
            .field("ui_prefs", ui_prefs)
            .finish())


def serialize_user(user) -> dict:
    """Safe user representation: never includes password hash or session nonce."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "notify_email": user.notify_email,
        "notify_telegram": user.notify_telegram,
        "telegram_chat_id": user.telegram_chat_id,
        "ui_prefs": user.ui_prefs or {},
        "created_at": iso(user.created_at),
        "updated_at": iso(user.updated_at),
    }
