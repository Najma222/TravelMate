"""Dashboard and overview response composition (pure serialization)."""
from __future__ import annotations

from app.schemas.common import fmt_money
from app.schemas.trip import serialize_trip


def serialize_trip_card(trip, budget_summary, today_date) -> dict:
    """Compact trip summary with budget headline numbers."""
    data = serialize_trip(trip, today_date=today_date)
    data["budget_summary"] = {
        "forecast_total": fmt_money(budget_summary.forecast_total),
        "confirmed_total": fmt_money(budget_summary.confirmed_total),
        "remaining": fmt_money(budget_summary.remaining),
        "exceeded": budget_summary.exceeded,
        "spent_percent": float(budget_summary.spent_percent),
    }
    return data
