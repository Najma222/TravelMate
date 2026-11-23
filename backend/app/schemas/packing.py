"""Packing item validation and serialization (D11)."""
from __future__ import annotations

from app.schemas.common import iso
from app.utils.validators import (Validator, aware_datetime, boolean, integer, optional_string,
                                  string)


def _fields(v: Validator, creating: bool) -> Validator:
    return (v.field("name", string(100, min_len=1), required=creating)
             .field("note", optional_string(300), nullable=True)
             .field("is_packed", boolean, default=False)
             .field("remind_at", aware_datetime, nullable=True)
             .field("sort_order", integer(0, 1000)))


def validate_packing_create(data: dict) -> dict:
    return _fields(Validator(data), creating=True).finish()


def validate_packing_update(data: dict) -> dict:
    return _fields(Validator(data, partial=True), creating=False).finish()


def serialize_packing_item(p) -> dict:
    return {
        "id": p.id,
        "trip_id": p.trip_id,
        "name": p.name,
        "note": p.note,
        "is_packed": p.is_packed,
        "remind_at": iso(p.remind_at),
        "sort_order": p.sort_order,
        "source": p.source,
        "created_at": iso(p.created_at),
    }
