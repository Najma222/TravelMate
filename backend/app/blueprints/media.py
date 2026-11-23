"""GET /media/<path:filename> (public, unversioned)."""
from __future__ import annotations

import os

from flask import Blueprint, send_file

from app.services import upload_service
from app.utils.auth import public
from app.utils.errors import NotFound

bp = Blueprint("media", __name__)


@bp.get("/media/<path:filename>")
@public
def serve(filename: str):
    path = upload_service.resolve_media_path(filename)
    if path is None:
        raise NotFound("File not found")
    resp = send_file(path, mimetype="image/webp", max_age=86400, conditional=True,
                     download_name=os.path.basename(path))
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Disposition"] = "inline"
    return resp
