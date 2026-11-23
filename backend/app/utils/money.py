"""Decimal-only money helpers. Never use float arithmetic for money."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")


def to_money(value) -> Decimal:
    """Coerce DB/Decimal/int/str into a 2dp Decimal. Floats are rejected."""
    if value is None:
        return ZERO
    if isinstance(value, float):
        raise TypeError("float values are not allowed for money")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value) -> str | None:
    """Serialize money as a fixed 2dp string (JSON-safe, no float rounding)."""
    if value is None:
        return None
    return str(to_money(value))


def percent(part: Decimal, whole: Decimal) -> Decimal:
    """``round(part / whole * 100, 1)`` in Decimal (half-up). ``whole <= 0`` -> 0.0."""
    if whole is None or whole <= 0:
        return Decimal("0.0")
    return (Decimal(part) / Decimal(whole) * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)
