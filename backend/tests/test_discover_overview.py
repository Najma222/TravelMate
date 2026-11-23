"""Discover (public), places, overview (≤8 queries, ETag/304), dashboard."""
from contextlib import contextmanager

import responses
from sqlalchemy import event

from app.extensions import db
from app.services import discover_service
from tests.factories import completed_payload, create_trip, register


def _seed(app):
    with app.app_context():
        discover_service.seed_destinations()
        db.session.remove()


def test_discover_public_search_filter_paginate(client, app):
    _seed(app)
    r = client.get("/api/v1/discover/destinations?per_page=5")
    assert r.status_code == 200
    body = r.get_json()
    assert body["pagination"]["total"] >= 30 and len(body["items"]) == 5
    assert client.get("/api/v1/discover/destinations?q=taj").get_json()["items"][0]["name"] == "Agra"
    nepal = client.get("/api/v1/discover/destinations?country=nepal").get_json()["items"]
    assert {d["name"] for d in nepal} == {"Kathmandu", "Pokhara"}
    beach = client.get("/api/v1/discover/destinations?tag=beach").get_json()["items"]
    assert beach and all("beach" in d["tags"] for d in beach)
    assert client.get("/api/v1/discover/destinations?q=%25").get_json()["items"] == []


def test_seed_discover_idempotent(app):
    _seed(app)
    _seed(app)
    with app.app_context():
        from app.models import DiscoverDestination

        n = db.session.query(DiscoverDestination).count()
        db.session.remove()
    assert n == len(discover_service.load_seed())


def test_places_only_from_stored_data(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    assert client.get(f"/api/v1/trips/{tid}/places").get_json()["places"] == []
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "http://n8n.test/webhook/trip", json={})
        gid = client.post(f"/api/v1/trips/{tid}/generate").get_json()["trip"]["generation_id"]
    internal.post(f"/api/v1/internal/trips/{tid}/result", json=completed_payload(gid))
    places = client.get(f"/api/v1/trips/{tid}/places").get_json()
    assert len(places["places"]) == 6 and places["stops"][0]["name"] == "North Goa"


@contextmanager
def count_queries(app):
    counter = {"n": 0}
    with app.app_context():
        engine = db.engine

    def before(*_a, **_k):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_overview_query_budget_and_etag(client, app, internal):
    register(client)
    tid = create_trip(client)["id"]
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "http://n8n.test/webhook/trip", json={})
        gid = client.post(f"/api/v1/trips/{tid}/generate").get_json()["trip"]["generation_id"]
    internal.post(f"/api/v1/internal/trips/{tid}/result", json=completed_payload(gid))
    client.post(f"/api/v1/trips/{tid}/bookings", json={"booking_type": "hotel", "amount": "10", "status": "Confirmed"})

    with count_queries(app) as q:
        r = client.get(f"/api/v1/trips/{tid}/overview")
    assert r.status_code == 200
    assert q["n"] <= 8, q["n"]
    body = r.get_json()
    assert body["trip"]["status"] == "Completed"
    assert body["itinerary"]["total_activities"] == 6 and len(body["itinerary"]["days"]) == 3
    assert body["bookings"]["status_counts"] == {"Confirmed": 1}
    assert body["budget"]["categories"][1]["basis"] == "confirmed"  # accommodation
    etag = r.headers["ETag"]
    r2 = client.get(f"/api/v1/trips/{tid}/overview", headers={"If-None-Match": etag})
    assert r2.status_code == 304 and r2.data == b""
    client.put(f"/api/v1/trips/{tid}", json={"preferences": "changed"})
    r3 = client.get(f"/api/v1/trips/{tid}/overview", headers={"If-None-Match": etag})
    assert r3.status_code == 200 and r3.headers["ETag"] != etag


def test_dashboard(client, internal, sql):
    register(client)
    a = create_trip(client)["id"]
    b = create_trip(client)["id"]
    sql("UPDATE trips SET status='Cancelled' WHERE id=:id", id=b)
    client.post(f"/api/v1/trips/{a}/expenses", json={"category": "food", "amount": "100", "is_confirmed": True})
    client.post(f"/api/v1/trips/{a}/bookings", json={"booking_type": "flight"})
    internal.post("/api/v1/internal/notifications",
                  json={"trip_id": a, "notification_type": "trip_reminder", "message": "hi", "delivery_status": "sent"})
    d = client.get("/api/v1/dashboard").get_json()
    assert d["counts"] == {"upcoming": 1, "ongoing": 0, "past": 0, "cancelled": 1, "total": 2}
    assert d["next_trip"]["id"] == a
    assert d["next_trip"]["budget_summary"]["confirmed_total"] == "100.00"
    assert [t["id"] for t in d["recent_trips"]] == [b]
    assert d["notifications"]["unread_count"] == 1 and d["pending_bookings"] == 1
