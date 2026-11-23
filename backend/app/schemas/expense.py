"""Expense validation and serialization, plus the budget (D3) response shape."""
from __future__ import annotations

from decimal import Decimal

from app.models import EXPENSE_CATEGORIES
from app.schemas.common import fmt_money, iso
from app.utils.validators import Validator, boolean, choice, date_, money, optional_string

CATEGORY_ALIASES = {"transportation": "transport", "miscellaneous": "misc"}


def normalize_category(raw) -> str:
    """D4 normalisation for n8n data: aliases, lowercase, unknown -> misc."""
    if not isinstance(raw, str):
        return "misc"
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    key = CATEGORY_ALIASES.get(key, key)
    return key if key in EXPENSE_CATEGORIES else "misc"


def _fields(v: Validator, creating: bool) -> Validator:
    return (v.field("category", choice(EXPENSE_CATEGORIES, case_insensitive=True), required=creating)
             .field("description", optional_string(200), nullable=True)
             .field("amount", money(Decimal("0"), allow_equal_min=False), required=creating)
             .field("is_confirmed", boolean, default=False)
             .field("expense_date", date_))


def validate_expense_create(data: dict) -> dict:
    return _fields(Validator(data), creating=True).finish()


def validate_expense_update(data: dict) -> dict:
    return _fields(Validator(data, partial=True), creating=False).finish()


def serialize_expense(e) -> dict:
    return {
        "id": e.id,
        "trip_id": e.trip_id,
        "booking_id": e.booking_id,
        "category": e.category,
        "description": e.description,
        "amount": fmt_money(e.amount),
        "is_confirmed": e.is_confirmed,
        "expense_date": e.expense_date.isoformat() if e.expense_date else None,
        "source": e.source,
        "locked": e.booking_id is not None,
        "created_at": iso(e.created_at),
        "updated_at": iso(e.updated_at),
    }


def serialize_budget(summary, currency: str) -> dict:
    """``summary`` is a :class:`app.services.budget.BudgetSummary`."""
    return {
        "currency": currency,
        "budget": fmt_money(summary.budget),
        "confirmed_total": fmt_money(summary.confirmed_total),
        "estimated_total": fmt_money(summary.estimated_total),
        "forecast_total": fmt_money(summary.forecast_total),
        "remaining": fmt_money(summary.remaining),
        "exceeded": summary.exceeded,
        "exceeded_by": fmt_money(summary.exceeded_by),
        "spent_percent": float(summary.spent_percent),
        "remaining_percent": float(summary.remaining_percent),
        "forecast_percent": float(summary.forecast_percent),
        "categories": [
            {
                "category": c.category,
                "confirmed": fmt_money(c.confirmed),
                "estimated": fmt_money(c.estimated),
                "effective": fmt_money(c.effective),
                "basis": c.basis,
            }
            for c in summary.categories
        ],
    }
