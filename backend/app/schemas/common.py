"""Shared serialization helpers and the error-envelope schema."""
from __future__ import annotations

from decimal import Decimal

from app.utils.dates import iso
from app.utils.money import fmt_money

__all__ = ["coord", "iso", "fmt_money", "error_envelope", "paginated"]


def coord(value) -> float | None:
    """Coordinates are display data, serialized as JSON numbers."""
    if value is None:
        return None
    return float(Decimal(value))


def error_envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def paginated(items: list, meta: dict) -> dict:
    return {"items": items, "pagination": meta}
