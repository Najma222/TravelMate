"""Test data builders that go through the public API (so they exercise real code paths)."""
from __future__ import annotations

import itertools
from datetime import date, timedelta

from app.utils.dates import today as app_today

_seq = itertools.count(1)
PASSWORD = "Passw0rd!x"


def today() -> date:
    return app_today()


def register(client, email: str | None = None, name: str = "Test User", password: str = PASSWORD):
    email = email or f"user{next(_seq)}@example.com"
    resp = client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["user"]


def trip_payload(**overrides) -> dict:
    t0 = today()
    data = {
        "origin": "Mumbai",
        "destination": f"Goa {next(_seq)}",
        "start_date": (t0 + timedelta(days=10)).isoformat(),
        "end_date": (t0 + timedelta(days=12)).isoformat(),
        "traveller_count": 2,
        "budget": "30000.00",
        "currency": "INR",
        "preferences": "Beaches",
    }
    data.update(overrides)
    return data


def create_trip(client, **overrides) -> dict:
    resp = client.post("/api/v1/trips", json=trip_payload(**overrides))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["trip"]


def completed_payload(generation_id: str, days: int = 3, **extra) -> dict:
    payload = {
        "generation_id": generation_id,
        "status": "Completed",
        "itinerary": [
            {"day_number": d, "activity_name": f"Place {d}-{i}", "location": f"Area {d}",
             "start_time": f"{9 + 2 * i:02d}:00", "end_time": f"{10 + 2 * i:02d}:00",
             "estimated_cost": "500.00", "latitude": 15.5, "longitude": 73.8}
            for d in range(1, days + 1) for i in range(2)
        ],
        "days": [{"day_number": d, "title": f"Explore day {d}", "summary": "Sightseeing"}
                 for d in range(1, days + 1)],
        "expenses": [
            {"category": "Transportation", "description": "Flights", "amount": "8000.00"},
            {"category": "food", "description": "Meals", "amount": "6000.00"},
            {"category": "Miscellaneous", "description": "Extras", "amount": "1000.00"},
        ],
        "stops": [{"name": "North Goa", "latitude": 15.6, "longitude": 73.75}],
    }
    payload.update(extra)
    return payload
