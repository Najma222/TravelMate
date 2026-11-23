"""Query-string pagination helpers."""
from __future__ import annotations

import math

from flask import request

from app.utils.errors import ValidationError

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def get_page_args(default_per_page: int = DEFAULT_PER_PAGE) -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", default_per_page))
    except (TypeError, ValueError):
        raise ValidationError("page and per_page must be integers",
                              details={"fields": {"page": "must be an integer"}})
    if page < 1 or per_page < 1 or per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"page must be >= 1 and per_page between 1 and {MAX_PER_PAGE}",
            details={"fields": {"per_page": f"must be between 1 and {MAX_PER_PAGE}"}},
        )
    return page, per_page


def page_meta(page: int, per_page: int, total: int) -> dict:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
    }
