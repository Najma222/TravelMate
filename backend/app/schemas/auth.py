"""Auth request validation."""
from __future__ import annotations

import re

from app.utils.validators import FieldError, Validator, email, string

PASSWORD_MIN = 8
PASSWORD_MAX_BYTES = 72  # bcrypt truncates beyond 72 bytes


def password(v):
    if not isinstance(v, str):
        raise FieldError("must be a string")
    if len(v) < PASSWORD_MIN:
        raise FieldError(f"must be at least {PASSWORD_MIN} characters")
    if len(v.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise FieldError(f"must be at most {PASSWORD_MAX_BYTES} bytes")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise FieldError("must contain at least one letter and one digit")
    if v.strip() != v:
        raise FieldError("must not start or end with whitespace")
    return v


def _any_password(v):
    if not isinstance(v, str) or not v:
        raise FieldError("is required")
    if len(v.encode("utf-8")) > 256:
        raise FieldError("is too long")
    return v


def validate_register(data: dict) -> dict:
    return (Validator(data)
            .field("name", string(80, min_len=1), required=True)
            .field("email", email, required=True)
            .field("password", password, required=True)
            .finish())


def validate_login(data: dict) -> dict:
    return (Validator(data)
            .field("email", email, required=True)
            .field("password", _any_password, required=True)
            .finish())


def validate_change_password(data: dict) -> dict:
    v = (Validator(data)
         .field("current_password", _any_password, required=True)
         .field("new_password", password, required=True))
    if (v.out.get("current_password") and v.out.get("new_password")
            and v.out["current_password"] == v.out["new_password"]):
        v.error("new_password", "must differ from the current password")
    return v.finish()


def validate_delete_account(data: dict) -> dict:
    return Validator(data).field("password", _any_password, required=True).finish()
