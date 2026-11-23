"""Media upload response shapes."""
from __future__ import annotations


def serialize_upload(kind: str, url: str) -> dict:
    return {"kind": kind, "url": url, "content_type": "image/webp"}
