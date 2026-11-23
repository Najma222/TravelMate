"""Authentication, sessions and account management."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import bcrypt, db
from app.models import AuditLog, Trip, User
from app.services import audit
from app.utils.dates import now_utc
from app.utils.errors import Conflict, RateLimited, Unauthorized, ValidationError

log = logging.getLogger("travelmate.auth")

_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """A real bcrypt hash used to equalise timing for unknown emails."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.generate_password_hash(secrets.token_urlsafe(24)).decode("utf-8")
    return _DUMMY_HASH


def new_nonce() -> str:
    return secrets.token_hex(16)  # 32 chars


def hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")


def check_password(pw_hash: str, password: str) -> bool:
    try:
        return bcrypt.check_password_hash(pw_hash, password)
    except ValueError:
        return False


# --------------------------------------------------------------------------- session lookup

def get_session_user(uid, nonce) -> User | None:
    if not isinstance(uid, int) or not isinstance(nonce, str) or not nonce:
        return None
    user = db.session.get(User, uid)
    if user is None:
        return None
    if not secrets.compare_digest(user.session_nonce, nonce):
        return None
    return user


# --------------------------------------------------------------------------- register / login

def register(data: dict) -> User:
    user = User(
        name=data["name"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
        session_nonce=new_nonce(),
        ui_prefs={},
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("An account with this email already exists",
                       details={"fields": {"email": "is already registered"}})
    audit.record("register", "success", actor="user", user_id=user.id)
    return user


def _recent_failures(email_fp: str):
    window = current_app.config["LOGIN_FAILURE_WINDOW_MINUTES"]
    since = now_utc() - timedelta(minutes=window)
    row = db.session.execute(
        select(func.count(AuditLog.id), func.min(AuditLog.created_at))
        .where(AuditLog.action == "login_failed",
               AuditLog.created_at >= since,
               AuditLog.meta["email_fp"].astext == email_fp)
    ).one()
    return row[0], row[1]


def _check_lockout(email_fp: str) -> None:
    count, oldest = _recent_failures(email_fp)
    limit = current_app.config["LOGIN_FAILURE_LIMIT"]
    if count >= limit:
        window = timedelta(minutes=current_app.config["LOGIN_FAILURE_WINDOW_MINUTES"])
        retry_after = max(1, int((oldest + window - now_utc()).total_seconds()) + 1)
        audit.record("login_locked", "denied", actor="anon", meta={"email_fp": email_fp})
        raise RateLimited("Too many failed login attempts. Try again later.",
                          details={"retry_after": retry_after},
                          headers={"Retry-After": str(retry_after)})


def login(email: str, password: str) -> User:
    email_fp = audit.email_fingerprint(email)
    _check_lockout(email_fp)
    user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        check_password(_dummy_hash(), password)  # constant-ish time: no enumeration
        ok = False
    else:
        ok = check_password(user.password_hash, password)
    db.session.rollback()  # release the read transaction before audit writes
    if not ok:
        audit.record("login_failed", "denied", actor="anon",
                     user_id=user.id if user else None, meta={"email_fp": email_fp})
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    audit.record("login", "success", actor="user", user_id=user.id)
    return user


def logout(user: User) -> None:
    """Rotate the nonce so every outstanding cookie for this user stops working."""
    try:
        user.session_nonce = new_nonce()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    audit.record("logout", "success", actor="user", user_id=user.id)


def change_password(user: User, current_password: str, new_password: str) -> User:
    if not check_password(user.password_hash, current_password):
        audit.record("password_change", "denied", actor="user", user_id=user.id)
        raise ValidationError("Current password is incorrect",
                              details={"fields": {"current_password": "is incorrect"}})
    try:
        user.password_hash = hash_password(new_password)
        user.session_nonce = new_nonce()  # invalidates all other sessions
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    audit.record("password_change", "success", actor="user", user_id=user.id)
    return user


def update_profile(user: User, data: dict) -> User:
    try:
        for k in ("name", "ui_prefs"):
            if k in data:
                setattr(user, k, data[k])
        db.session.commit()
        return user
    except Exception:
        db.session.rollback()
        raise


def set_avatar(user: User, url: str) -> str | None:
    """Store a new avatar URL; return the previous one so the caller can delete the file."""
    try:
        old = user.avatar_url
        user.avatar_url = url
        db.session.commit()
        return old
    except Exception:
        db.session.rollback()
        raise


def delete_account(user: User, password: str) -> list[str]:
    """Delete the user and (via cascade) all their data. Returns media URLs to remove."""
    if not check_password(user.password_hash, password):
        audit.record("account_delete", "denied", actor="user", user_id=user.id)
        raise ValidationError("Password is incorrect", details={"fields": {"password": "is incorrect"}})
    user_id = user.id
    try:
        media = [u for (u,) in db.session.execute(
            select(Trip.cover_image_url).where(Trip.user_id == user_id,
                                               Trip.cover_image_url.is_not(None)))]
        if user.avatar_url:
            media.append(user.avatar_url)
        db.session.execute(delete(User).where(User.id == user_id))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    db.session.expunge_all()
    audit.record("account_delete", "success", actor="user", meta={"deleted_user_id": user_id})
    return media
