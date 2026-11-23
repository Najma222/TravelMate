"""Default packing list seeding (D11) and the auto-jacket rule."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from sqlalchemy import func, select

from app.extensions import db
from app.models import PackingItem

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "seed", "default_packing.json")
JACKET_TEMP_THRESHOLD_C = 15.0


@lru_cache(maxsize=1)
def load_default_items() -> tuple[dict, ...]:
    with open(os.path.abspath(SEED_PATH), encoding="utf-8") as fh:
        data = json.load(fh)
    items = []
    for i, row in enumerate(data):
        name = str(row["name"]).strip()[:100]
        note = row.get("note")
        items.append({"name": name, "note": str(note)[:300] if note else None, "sort_order": i})
    return tuple(items)


def seed_default_items(trip_id: int) -> int:
    """Add default items to a new trip. Caller owns the transaction."""
    for item in load_default_items():
        db.session.add(PackingItem(trip_id=trip_id, name=item["name"], note=item["note"],
                                   sort_order=item["sort_order"], source="default"))
    return len(load_default_items())


def ensure_jacket(trip_id: int, min_temp_c: float | None) -> bool:
    """Insert a jacket item when it will be cold and none exists. Caller owns the transaction."""
    if min_temp_c is None or min_temp_c > JACKET_TEMP_THRESHOLD_C:
        return False
    exists = db.session.execute(
        select(func.count(PackingItem.id))
        .where(PackingItem.trip_id == trip_id, PackingItem.name.ilike("%jacket%"))
    ).scalar_one()
    if exists:
        return False
    max_order = db.session.execute(
        select(func.coalesce(func.max(PackingItem.sort_order), -1))
        .where(PackingItem.trip_id == trip_id)
    ).scalar_one()
    db.session.add(PackingItem(
        trip_id=trip_id, name="Warm jacket",
        note=f"Forecast low of {min_temp_c:g}°C at your destination",
        sort_order=min(int(max_order) + 1, 1000), source="auto",
    ))
    return True
