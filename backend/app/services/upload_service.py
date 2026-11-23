"""D14 media uploads: validate with Pillow, strip EXIF by re-encoding to WebP.

* ≤ 2 MB, actual content must decode as JPEG, PNG or WebP (extension alone is not trusted).
* Re-encoded to ``.webp`` without metadata => EXIF/GPS stripped.
* Stored at ``UPLOAD_DIR/{avatars|covers}/{uuid}.webp``; served by ``GET /media/<path>``.
"""
from __future__ import annotations

import io
import logging
import os
import re
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from app.utils.errors import PayloadTooLarge, UnsupportedMediaType, ValidationError

log = logging.getLogger("travelmate.upload")

KINDS = {"avatars": 512, "covers": 2000}  # max edge in pixels after resize
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PIXELS = 40_000_000  # decompression-bomb guard
MEDIA_PATH_RE = re.compile(r"^(avatars|covers)/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.webp$")
MEDIA_URL_PREFIX = "/media/"


def upload_root() -> str:
    return os.path.abspath(current_app.config["UPLOAD_DIR"])


def _read_limited(file_storage) -> bytes:
    limit = current_app.config["MAX_UPLOAD_BYTES"]
    data = file_storage.stream.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge("Image exceeds the 2 MB limit")
    if not data:
        raise ValidationError("Uploaded file is empty", details={"fields": {"file": "is empty"}})
    return data


def process_image(file_storage, kind: str) -> str:
    """Validate + re-encode. Returns the public URL (``/media/{kind}/{uuid}.webp``)."""
    if kind not in KINDS:
        raise ValueError("unknown upload kind")
    if file_storage is None or not file_storage.filename:
        raise ValidationError("A file field named 'file' is required",
                              details={"fields": {"file": "is required"}})
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaType("Only JPEG, PNG or WebP images are allowed",
                                   details={"fields": {"file": "unsupported file extension"}})
    data = _read_limited(file_storage)

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED_FORMATS:
                raise UnsupportedMediaType("Only JPEG, PNG or WebP images are allowed",
                                           details={"fields": {"file": "unsupported image format"}})
            w, h = probe.size
            if w * h > MAX_PIXELS:
                raise ValidationError("Image dimensions are too large",
                                      details={"fields": {"file": "image is too large"}})
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:  # verify() invalidates; reopen to decode
            img.load()
            img = ImageOps.exif_transpose(img)  # honour orientation before EXIF is dropped
            img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
            img.thumbnail((KINDS[kind], KINDS[kind]))
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=85, method=4)  # no exif= => metadata stripped
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise UnsupportedMediaType("File is not a valid image",
                                   details={"fields": {"file": "could not be decoded as an image"}})

    name = f"{uuid.uuid4()}.webp"
    directory = os.path.join(upload_root(), kind)
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, f".{name}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(out.getvalue())
    os.replace(tmp, os.path.join(directory, name))
    return f"{MEDIA_URL_PREFIX}{kind}/{name}"


def resolve_media_path(relative: str) -> str | None:
    """Map a ``/media/<relative>`` request to an absolute file path, or ``None``.

    Only ``{avatars|covers}/{uuid}.webp`` is accepted, so traversal is impossible.
    """
    if not MEDIA_PATH_RE.match(relative or ""):
        return None
    root = upload_root()
    path = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        return None
    return path


def delete_media(url: str | None) -> None:
    """Best-effort removal of a previously stored file (called after the DB commit)."""
    if not url or not url.startswith(MEDIA_URL_PREFIX):
        return
    path = resolve_media_path(url[len(MEDIA_URL_PREFIX):])
    if path:
        try:
            os.remove(path)
        except OSError:
            log.warning("media_delete_failed")
