"""Trip stop validation and serialization."""
from __future__ import annotations

from app.schemas.common import coord
from app.utils.validators import Validator, coordinate, integer, list_of, string


def validate_stop_create(data: dict) -> dict:
    return (Validator(data)
            .field("name", string(100, min_len=1), required=True)
            .field("latitude", coordinate("lat"), nullable=True)
            .field("longitude", coordinate("lon"), nullable=True)
            .finish())


def validate_stop_update(data: dict) -> dict:
    return (Validator(data, partial=True)
            .field("name", string(100, min_len=1))
            .field("latitude", coordinate("lat"), nullable=True)
            .field("longitude", coordinate("lon"), nullable=True)
            .finish())


def validate_stop_order(data: dict) -> list[int]:
    out = (Validator(data)
           .field("stop_ids", list_of(integer(1), max_items=200), required=True)
           .finish())
    return out["stop_ids"]


def serialize_stop(stop) -> dict:
    return {
        "id": stop.id,
        "trip_id": stop.trip_id,
        "position": stop.position,
        "name": stop.name,
        "latitude": coord(stop.latitude),
        "longitude": coord(stop.longitude),
        "source": stop.source,
    }
