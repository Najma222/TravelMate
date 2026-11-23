"""Session helpers and the ``@login_required`` decorator.

The signed Flask session cookie stores ``uid`` and ``nonce``. A request is
authenticated only if the nonce still matches ``users.session_nonce``; rotating the
nonce (logout, password change) therefore invalidates every other cookie.
"""
from __future__ import annotations

from functools import wraps

from flask import g, session

from app.utils.errors import Unauthorized


def start_session(user) -> None:
    session.clear()
    session.permanent = True  # PERMANENT_SESSION_LIFETIME = 7 days
    session["uid"] = user.id
    session["nonce"] = user.session_nonce


def end_session() -> None:
    session.clear()


def current_user():
    return getattr(g, "current_user", None)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from app.services import auth_service

        uid = session.get("uid")
        nonce = session.get("nonce")
        user = auth_service.get_session_user(uid, nonce)
        if user is None:
            session.clear()
            raise Unauthorized("Authentication required")
        g.current_user = user
        return fn(*args, **kwargs)

    wrapper._login_required = True  # type: ignore[attr-defined]
    return wrapper


def public(fn):
    """Marks a route as intentionally unauthenticated (checked by the route-audit test)."""
    fn._public = True  # type: ignore[attr-defined]
    return fn
