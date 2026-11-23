"""D3 budget math — Decimal only.

Estimated expenses are category placeholders until a confirmed expense exists in that
category::

    effective(cat) = confirmed(cat) if confirmed(cat) > 0 else estimated(cat)
    forecast_total = sum(effective over the 6 categories)
    remaining      = budget - forecast_total
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select

from app.extensions import db
from app.models import EXPENSE_CATEGORIES, Expense
from app.utils.money import ZERO, percent, to_money


@dataclass(frozen=True)
class CategoryBudget:
    category: str
    confirmed: Decimal
    estimated: Decimal
    effective: Decimal
    basis: str


@dataclass(frozen=True)
class BudgetSummary:
    budget: Decimal
    confirmed_total: Decimal
    estimated_total: Decimal
    forecast_total: Decimal
    remaining: Decimal
    exceeded: bool
    exceeded_by: Decimal
    spent_percent: Decimal
    remaining_percent: Decimal
    forecast_percent: Decimal
    categories: list[CategoryBudget] = field(default_factory=list)


def compute_budget(budget, rows: Iterable[tuple[str, bool, Decimal]]) -> BudgetSummary:
    """Pure D3 computation.

    ``rows`` are ``(category, is_confirmed, amount)``; amounts may be pre-aggregated.
    Unknown categories are counted as ``misc``.
    """
    budget = to_money(budget)
    confirmed = {c: ZERO for c in EXPENSE_CATEGORIES}
    estimated = {c: ZERO for c in EXPENSE_CATEGORIES}
    for category, is_confirmed, amount in rows:
        cat = category if category in confirmed else "misc"
        bucket = confirmed if is_confirmed else estimated
        bucket[cat] = bucket[cat] + to_money(amount)

    categories = []
    for c in EXPENSE_CATEGORIES:
        if confirmed[c] > 0:
            categories.append(CategoryBudget(c, confirmed[c], estimated[c], confirmed[c], "confirmed"))
        else:
            categories.append(CategoryBudget(c, confirmed[c], estimated[c], estimated[c], "estimated"))

    confirmed_total = sum(confirmed.values(), ZERO)
    estimated_total = sum(estimated.values(), ZERO)
    forecast_total = sum((c.effective for c in categories), ZERO)
    remaining = budget - forecast_total
    exceeded = remaining < 0
    exceeded_by = max(ZERO, -remaining)
    spent_percent = percent(confirmed_total, budget)
    remaining_percent = max(Decimal("0.0"), (Decimal(100) - spent_percent).quantize(Decimal("0.1")))
    forecast_percent = percent(forecast_total, budget)
    return BudgetSummary(
        budget=budget,
        confirmed_total=to_money(confirmed_total),
        estimated_total=to_money(estimated_total),
        forecast_total=to_money(forecast_total),
        remaining=to_money(remaining),
        exceeded=exceeded,
        exceeded_by=to_money(exceeded_by),
        spent_percent=spent_percent,
        remaining_percent=remaining_percent,
        forecast_percent=forecast_percent,
        categories=categories,
    )


def aggregate_rows(trip_ids: list[int]) -> dict[int, list[tuple[str, bool, Decimal]]]:
    """One grouped query for many trips (avoids N+1 on dashboard lists)."""
    out: dict[int, list] = {tid: [] for tid in trip_ids}
    if not trip_ids:
        return out
    rows = db.session.execute(
        select(Expense.trip_id, Expense.category, Expense.is_confirmed, func.sum(Expense.amount))
        .where(Expense.trip_id.in_(trip_ids))
        .group_by(Expense.trip_id, Expense.category, Expense.is_confirmed)
    ).all()
    for trip_id, category, is_confirmed, total in rows:
        out[trip_id].append((category, is_confirmed, total))
    return out


def trip_budget(trip) -> BudgetSummary:
    return compute_budget(trip.budget, aggregate_rows([trip.id])[trip.id])
