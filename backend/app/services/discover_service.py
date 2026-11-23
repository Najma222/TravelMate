"""Public destination discovery + idempotent JSON seeding."""
from __future__ import annotations

import json
import os
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import DiscoverDestination

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "seed", "discover_destinations.json")


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(filters: dict, page: int, per_page: int):
    stmt = select(DiscoverDestination).where(DiscoverDestination.is_active.is_(True))
    if "q" in filters:
        like = f"%{_escape_like(filters['q'])}%"
        stmt = stmt.where(or_(DiscoverDestination.name.ilike(like, escape="\\"),
                              DiscoverDestination.description.ilike(like, escape="\\"),
                              DiscoverDestination.region.ilike(like, escape="\\")))
    if "country" in filters:
        stmt = stmt.where(func.lower(DiscoverDestination.country) == filters["country"].lower())
    if "region" in filters:
        stmt = stmt.where(func.lower(DiscoverDestination.region) == filters["region"].lower())
    if "tag" in filters:
        stmt = stmt.where(DiscoverDestination.tags.contains([filters["tag"].lower()]))
    total = db.session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = list(db.session.execute(
        stmt.order_by(DiscoverDestination.name, DiscoverDestination.id)
        .offset((page - 1) * per_page).limit(per_page)).scalars())
    return items, total


def load_seed(path: str | None = None) -> list[dict]:
    with open(os.path.abspath(path or SEED_PATH), encoding="utf-8") as fh:
        rows = json.load(fh)
    out = []
    for r in rows:
        out.append({
            "name": str(r["name"])[:100],
            "country": str(r["country"])[:60],
            "region": (r.get("region") or None) and str(r["region"])[:60],
            "description": (r.get("description") or None) and str(r["description"])[:500],
            "best_season": (r.get("best_season") or None) and str(r["best_season"])[:60],
            "latitude": Decimal(str(r["latitude"])) if r.get("latitude") is not None else None,
            "longitude": Decimal(str(r["longitude"])) if r.get("longitude") is not None else None,
            "image_url": r.get("image_url"),
            "tags": [str(t).lower() for t in r.get("tags", [])],
            "is_active": bool(r.get("is_active", True)),
        })
    return out


def seed_destinations(path: str | None = None) -> tuple[int, int]:
    """Upsert on (name, country). Safe to re-run. Returns (inserted_or_updated, total_rows)."""
    rows = load_seed(path)
    try:
        for r in rows:
            stmt = insert(DiscoverDestination).values(**r)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_discover_destinations_name_country",
                set_={k: stmt.excluded[k] for k in r if k not in ("name", "country")})
            db.session.execute(stmt)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    total = db.session.execute(select(func.count(DiscoverDestination.id))).scalar_one()
    return len(rows), total
