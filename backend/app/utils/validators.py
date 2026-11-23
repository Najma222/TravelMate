"""Small declarative validation toolkit used by ``app.schemas``.

Parsers are callables ``value -> parsed`` that raise :class:`FieldError` with a
human message. :class:`Validator` collects per-field errors and raises a single
``ValidationError`` (400) whose ``details.fields`` maps field -> message.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import request

from app.utils.errors import ValidationError

MISSING = object()

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
MONEY_MAX = Decimal("9999999999.99")


class FieldError(Exception):
    pass


# --------------------------------------------------------------------------- JSON body

def _reject_constant(name: str):
    raise ValueError(f"Invalid JSON constant {name}")


def parse_json_bytes(raw: bytes) -> Any:
    """Parse JSON with Decimal floats (no float precision loss) and no NaN/Infinity."""
    return json.loads(raw, parse_float=Decimal, parse_constant=_reject_constant)


def json_body(required: bool = False) -> dict:
    """Return the request JSON object. Empty body -> ``{}``. Non-object -> 400."""
    raw = request.get_data(cache=True)
    if not raw or not raw.strip():
        if required:
            raise ValidationError("Request body is required")
        return {}
    try:
        data = parse_json_bytes(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Malformed JSON body")
    if not isinstance(data, dict):
        raise ValidationError("JSON body must be an object")
    return data


# --------------------------------------------------------------------------- parsers

def string(max_len: int, min_len: int = 0, strip: bool = True, pattern: re.Pattern | None = None,
           pattern_msg: str = "has an invalid format") -> Callable[[Any], str]:
    def parse(v):
        if not isinstance(v, str):
            raise FieldError("must be a string")
        if strip:
            v = v.strip()
        if len(v) < min_len:
            raise FieldError("is required" if min_len == 1 else f"must be at least {min_len} characters")
        if len(v) > max_len:
            raise FieldError(f"must be at most {max_len} characters")
        if "\x00" in v:
            raise FieldError("contains invalid characters")
        if pattern is not None and not pattern.match(v):
            raise FieldError(pattern_msg)
        return v
    return parse


def optional_string(max_len: int) -> Callable[[Any], str | None]:
    """String where blank collapses to ``None``."""
    inner = string(max_len)

    def parse(v):
        out = inner(v)
        return out or None
    return parse


def email(v):
    if not isinstance(v, str):
        raise FieldError("must be a string")
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise FieldError("must be a valid email address")
    return v


def integer(min_value: int | None = None, max_value: int | None = None):
    def parse(v):
        if isinstance(v, bool):
            raise FieldError("must be an integer")
        if isinstance(v, Decimal):
            if v != v.to_integral_value():
                raise FieldError("must be an integer")
            v = int(v)
        if isinstance(v, str) and re.fullmatch(r"-?\d{1,9}", v.strip()):
            v = int(v.strip())
        if not isinstance(v, int):
            raise FieldError("must be an integer")
        if min_value is not None and v < min_value:
            raise FieldError(f"must be >= {min_value}")
        if max_value is not None and v > max_value:
            raise FieldError(f"must be <= {max_value}")
        return v
    return parse


def money(min_value: Decimal = Decimal("0"), allow_equal_min: bool = True):
    """Parse a monetary amount into ``Decimal`` with exactly 2 decimal places.

    Accepts JSON numbers (parsed as Decimal), integers or numeric strings.
    Floats are never used.
    """
    def parse(v):
        if isinstance(v, bool) or v is None:
            raise FieldError("must be a number")
        if isinstance(v, float):  # defensive: should not occur with parse_json_bytes
            v = repr(v)
        try:
            d = Decimal(str(v).strip()) if not isinstance(v, Decimal) else v
        except (InvalidOperation, ValueError):
            raise FieldError("must be a number")
        if not d.is_finite():
            raise FieldError("must be a finite number")
        if d != d.quantize(Decimal("0.01")):
            raise FieldError("must have at most 2 decimal places")
        d = d.quantize(Decimal("0.01"))
        if allow_equal_min and d < min_value:
            raise FieldError(f"must be >= {min_value}")
        if not allow_equal_min and d <= min_value:
            raise FieldError(f"must be greater than {min_value}")
        if d > MONEY_MAX:
            raise FieldError(f"must be <= {MONEY_MAX}")
        return d
    return parse


def number(min_value: float | None = None, max_value: float | None = None):
    """Non-monetary numeric value (temperatures, percentages) returned as float."""
    def parse(v):
        if isinstance(v, bool):
            raise FieldError("must be a number")
        try:
            d = Decimal(str(v).strip()) if not isinstance(v, Decimal) else v
        except (InvalidOperation, ValueError):
            raise FieldError("must be a number")
        if not d.is_finite():
            raise FieldError("must be a finite number")
        f = float(d)
        if min_value is not None and f < min_value:
            raise FieldError(f"must be >= {min_value}")
        if max_value is not None and f > max_value:
            raise FieldError(f"must be <= {max_value}")
        return f
    return parse


def coordinate(kind: str):
    limit = Decimal("90") if kind == "lat" else Decimal("180")

    def parse(v):
        if isinstance(v, bool):
            raise FieldError("must be a number")
        try:
            d = Decimal(str(v).strip()) if not isinstance(v, Decimal) else v
        except (InvalidOperation, ValueError):
            raise FieldError("must be a number")
        if not d.is_finite() or d < -limit or d > limit:
            raise FieldError(f"must be between -{limit} and {limit}")
        return d.quantize(Decimal("0.000001"))
    return parse


def boolean(v):
    if not isinstance(v, bool):
        raise FieldError("must be true or false")
    return v


def choice(options, case_insensitive: bool = False):
    opts = tuple(options)

    def parse(v):
        if not isinstance(v, str):
            raise FieldError(f"must be one of: {', '.join(opts)}")
        if case_insensitive:
            for o in opts:
                if o.lower() == v.strip().lower():
                    return o
        elif v in opts:
            return v
        raise FieldError(f"must be one of: {', '.join(opts)}")
    return parse


def date_(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        raise FieldError("must be a date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(v.strip())
    except ValueError:
        raise FieldError("must be a date (YYYY-MM-DD)")


def time_(v):
    if not isinstance(v, str):
        raise FieldError("must be a time (HH:MM)")
    s = v.strip()
    if not re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", s):
        raise FieldError("must be a time (HH:MM)")
    try:
        return time.fromisoformat(s)
    except ValueError:
        raise FieldError("must be a time (HH:MM)")


def datetime_(v):
    """ISO-8601 datetime. Naive values are returned naive (caller localises)."""
    if not isinstance(v, str):
        raise FieldError("must be an ISO-8601 datetime")
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise FieldError("must be an ISO-8601 datetime")


def aware_datetime(v):
    dt = datetime_(v)
    if dt.tzinfo is None:
        raise FieldError("must include a timezone offset")
    return dt


def iana_timezone(v):
    if not isinstance(v, str) or not v.strip() or len(v) > 40:
        raise FieldError("must be an IANA timezone name")
    try:
        ZoneInfo(v.strip())
    except (ZoneInfoNotFoundError, ValueError):
        raise FieldError("must be an IANA timezone name")
    return v.strip()


def uuid_(v):
    if not isinstance(v, str):
        raise FieldError("must be a UUID")
    try:
        return uuid.UUID(v.strip())
    except ValueError:
        raise FieldError("must be a UUID")


def list_of(parser, max_items: int, min_items: int = 0):
    def parse(v):
        if not isinstance(v, list):
            raise FieldError("must be a list")
        if len(v) > max_items:
            raise FieldError(f"must contain at most {max_items} items")
        if len(v) < min_items:
            raise FieldError(f"must contain at least {min_items} items")
        out = []
        for i, item in enumerate(v):
            try:
                out.append(parser(item))
            except FieldError as e:
                raise FieldError(f"item {i} {e}")
        return out
    return parse


def json_safe(value, max_depth: int = 5):
    """Convert parsed JSON (with Decimals) into JSONB-storable primitives."""
    if max_depth < 0:
        raise FieldError("is nested too deeply")
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() and abs(value) < 2**53 else float(value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise FieldError("keys must be strings")
            out[k] = json_safe(v, max_depth - 1)
        return out
    if isinstance(value, list):
        return [json_safe(v, max_depth - 1) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise FieldError("contains an unsupported value")


# --------------------------------------------------------------------------- collector

class Validator:
    """Collects field errors for a single payload.

    ``partial=True`` (PUT semantics) skips ``required`` and only validates keys present.
    """

    def __init__(self, data: dict | None, partial: bool = False):
        if data is not None and not isinstance(data, dict):
            raise ValidationError("JSON body must be an object")
        self.data = data or {}
        self.partial = partial
        self.errors: dict[str, str] = {}
        self.out: dict[str, Any] = {}

    def field(self, name: str, parser: Callable[[Any], Any], *, required: bool = False,
              default: Any = MISSING, nullable: bool = False) -> "Validator":
        if name not in self.data:
            if required and not self.partial:
                self.errors[name] = "is required"
            elif default is not MISSING and not self.partial:
                self.out[name] = default() if callable(default) else default
            return self
        value = self.data[name]
        if value is None:
            if nullable:
                self.out[name] = None
            else:
                self.errors[name] = "may not be null"
            return self
        try:
            self.out[name] = parser(value)
        except FieldError as e:
            self.errors[name] = str(e)
        return self

    def error(self, name: str, message: str) -> None:
        self.errors.setdefault(name, message)

    def reject_unknown(self, allowed: set[str]) -> "Validator":
        for k in self.data:
            if k not in allowed:
                self.errors.setdefault(k, "is not a recognised field")
        return self

    def finish(self) -> dict:
        if self.errors:
            raise ValidationError("Request validation failed", details={"fields": self.errors})
        return self.out
