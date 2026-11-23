"""Discover destination query parsing and serialization."""
from __future__ import annotations

from flask import request

from app.schemas.common import coord
from app.utils.errors import ValidationError


def parse_discover_query() -> dict:
    out = {}
    for key, max_len in (("q", 100), ("country", 60), ("region", 60), ("tag", 40)):
        val = request.args.get(key)
        if val is None or not val.strip():
            continue
        val = val.strip()
        if len(val) > max_len:
            raise ValidationError("Invalid query", details={"fields": {key: f"must be at most {max_len} characters"}})
        out[key] = val
    return out


def serialize_destination(d) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "country": d.country,
        "region": d.region,
        "description": d.description,
        "best_season": d.best_season,
        "latitude": coord(d.latitude),
        "longitude": coord(d.longitude),
        "image_url": d.image_url,
        "tags": d.tags or [],
    }
