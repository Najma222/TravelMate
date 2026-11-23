"""/api/v1/auth — registration, login, session, profile, avatar, password, account."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.extensions import limiter
from app.schemas.auth import (validate_change_password, validate_delete_account, validate_login,
                              validate_register)
from app.schemas.media import serialize_upload
from app.schemas.user import serialize_user, validate_profile_update
from app.services import auth_service, upload_service
from app.utils.auth import current_user, end_session, login_required, public, start_session
from app.utils.validators import json_body

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _auth_limit():
    return current_app.config["AUTH_RATE_LIMIT"]


@bp.post("/register")
@public
@limiter.limit(_auth_limit)
def register():
    data = validate_register(json_body(required=True))
    user = auth_service.register(data)
    start_session(user)
    return jsonify({"user": serialize_user(user)}), 201


@bp.post("/login")
@public
@limiter.limit(_auth_limit)
def login():
    data = validate_login(json_body(required=True))
    user = auth_service.login(data["email"], data["password"])
    start_session(user)
    return jsonify({"user": serialize_user(user)}), 200


@bp.post("/logout")
@login_required
def logout():
    auth_service.logout(current_user())
    end_session()
    return jsonify({"logged_out": True}), 200


@bp.get("/me")
@login_required
def me():
    return jsonify({"user": serialize_user(current_user())}), 200


@bp.put("/profile")
@login_required
def update_profile():
    data = validate_profile_update(json_body())
    user = auth_service.update_profile(current_user(), data)
    return jsonify({"user": serialize_user(user)}), 200


@bp.post("/avatar")
@login_required
def upload_avatar():
    url = upload_service.process_image(request.files.get("file"), "avatars")
    try:
        old = auth_service.set_avatar(current_user(), url)
    except Exception:
        upload_service.delete_media(url)
        raise
    upload_service.delete_media(old)
    return jsonify({"user": serialize_user(current_user()),
                    "upload": serialize_upload("avatar", url)}), 200


@bp.post("/change-password")
@login_required
def change_password():
    data = validate_change_password(json_body(required=True))
    user = auth_service.change_password(current_user(), data["current_password"],
                                        data["new_password"])
    start_session(user)  # keep this session alive with the rotated nonce
    return jsonify({"password_changed": True}), 200


@bp.delete("/me")
@login_required
def delete_me():
    data = validate_delete_account(json_body(required=True))
    media = auth_service.delete_account(current_user(), data["password"])
    end_session()
    for url in media:
        upload_service.delete_media(url)
    return jsonify({"deleted": True}), 200
