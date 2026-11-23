"""Trip CRUD, validation, ownership, pagination, scopes, phase and ring (D13)."""
from datetime import date, timedelta

from app.services import trip_rules
from tests.factories import create_trip, register, today, trip_payload


def test_create_trip_and_seed_packing(client):
    register(client)
    trip = create_trip(client, budget="12345.60")
    assert trip["status"] == "Draft"
    assert trip["budget"] == "12345.60"
    assert trip["currency"] == "INR"
    assert trip["phase"] == "upcoming"
    assert trip["duration_days"] == 3
    packing = client.get(f"/api/v1/trips/{trip['id']}/packing").get_json()
    assert packing["total"] > 5
    assert all(i["source"] == "default" for i in packing["items"])


def test_create_trip_validation(client):
    register(client)
    t0 = today()
    cases = [
        ({"end_date": (t0 + timedelta(days=5)).isoformat(), "start_date": (t0 + timedelta(days=9)).isoformat()}, "end_date"),
        ({"start_date": (t0 - timedelta(days=1)).isoformat()}, "start_date"),
        ({"budget": "0"}, "budget"),
        ({"budget": "-5"}, "budget"),
        ({"budget": "10.123"}, "budget"),
        ({"traveller_count": 0}, "traveller_count"),
        ({"traveller_count": 51}, "traveller_count"),
        ({"currency": "JPY"}, "currency"),
        ({"transport_preference": "rocket"}, "transport_preference"),
        ({"start_date": "2026-13-01"}, "start_date"),
        ({"end_date": (t0 + timedelta(days=200)).isoformat()}, "end_date"),
    ]
    for override, field in cases:
        r = client.post("/api/v1/trips", json=trip_payload(**override))
        assert r.status_code == 400, override
        assert field in r.get_json()["error"]["details"]["fields"], (override, r.get_json())


def test_budget_is_decimal_exact(client):
    register(client)
    r = client.raw().post("/api/v1/trips", data=(
        '{"origin":"A","destination":"B","start_date":"%s","end_date":"%s","budget":1000.10}'
        % ((today() + timedelta(days=3)).isoformat(), (today() + timedelta(days=4)).isoformat())),
        headers={"Origin": "http://localhost:5173"}, content_type="application/json")
    assert r.status_code == 201
    assert r.get_json()["trip"]["budget"] == "1000.10"


def test_duplicate_submission_rejected(client):
    register(client)
    payload = trip_payload()
    assert client.post("/api/v1/trips", json=payload).status_code == 201
    r = client.post("/api/v1/trips", json=payload)
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "duplicate_submission"


def test_get_update_delete(client):
    register(client)
    trip = create_trip(client)
    tid = trip["id"]
    assert client.get(f"/api/v1/trips/{tid}").get_json()["trip"]["id"] == tid
    r = client.put(f"/api/v1/trips/{tid}", json={"traveller_count": 4, "preferences": "Food"})
    assert r.status_code == 200 and r.get_json()["trip"]["traveller_count"] == 4
    bad = client.put(f"/api/v1/trips/{tid}", json={"end_date": (today() + timedelta(days=1)).isoformat()})
    assert bad.status_code == 400
    assert client.delete(f"/api/v1/trips/{tid}").status_code == 200
    assert client.get(f"/api/v1/trips/{tid}").status_code == 404


def test_update_completed_trip_marks_itinerary_stale(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    sql("UPDATE trips SET status='Completed' WHERE id=:id", id=tid)
    r = client.put(f"/api/v1/trips/{tid}", json={"budget": "50000"})
    assert r.get_json()["trip"]["itinerary_stale"] is True


def test_cannot_edit_processing_or_cancelled(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    sql("UPDATE trips SET status='Processing' WHERE id=:id", id=tid)
    assert client.put(f"/api/v1/trips/{tid}", json={"budget": "1"}).status_code == 409
    sql("UPDATE trips SET status='Draft' WHERE id=:id", id=tid)
    assert client.post(f"/api/v1/trips/{tid}/cancel").status_code == 200
    assert client.put(f"/api/v1/trips/{tid}", json={"budget": "1"}).status_code == 409
    assert client.post(f"/api/v1/trips/{tid}/cancel").status_code == 409


def test_ownership_isolation_returns_404(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    other = make_client()
    register(other)
    for method, path in [("get", f"/api/v1/trips/{tid}"), ("put", f"/api/v1/trips/{tid}"),
                         ("delete", f"/api/v1/trips/{tid}"), ("get", f"/api/v1/trips/{tid}/overview"),
                         ("get", f"/api/v1/trips/{tid}/budget"), ("post", f"/api/v1/trips/{tid}/generate"),
                         ("get", f"/api/v1/trips/{tid}/itinerary"), ("get", f"/api/v1/trips/{tid}/packing")]:
        r = getattr(other, method)(path) if method == "get" else getattr(other, method)(path, json={"budget": "5"})
        assert r.status_code == 404, (method, path, r.status_code)
        assert r.get_json()["error"]["code"] == "not_found"


def test_pagination_and_scopes(client, sql):
    register(client)
    ids = [create_trip(client)["id"] for _ in range(5)]
    # make one archived (past) and one cancelled
    sql("UPDATE trips SET start_date=:s, end_date=:e WHERE id=:id",
        s=today() - timedelta(days=10), e=today() - timedelta(days=8), id=ids[0])
    sql("UPDATE trips SET status='Cancelled' WHERE id=:id", id=ids[1])
    page1 = client.get("/api/v1/trips?per_page=2&page=1").get_json()
    assert page1["pagination"] == {"page": 1, "per_page": 2, "total": 5, "pages": 3}
    assert len(page1["items"]) == 2
    up = client.get("/api/v1/trips?scope=upcoming").get_json()
    assert {t["id"] for t in up["items"]} == set(ids[2:])
    arc = client.get("/api/v1/trips?scope=archive").get_json()
    assert {t["id"] for t in arc["items"]} == {ids[0], ids[1]}
    assert client.get("/api/v1/trips?scope=bogus").status_code == 400
    assert client.get("/api/v1/trips?per_page=500").status_code == 400


def test_phase_rules():
    s, e = date(2026, 5, 10), date(2026, 5, 12)
    assert trip_rules.phase(s, e, date(2026, 5, 9)) == "upcoming"
    assert trip_rules.phase(s, e, date(2026, 5, 10)) == "ongoing"
    assert trip_rules.phase(s, e, date(2026, 5, 12)) == "ongoing"
    assert trip_rules.phase(s, e, date(2026, 5, 13)) == "past"
    assert trip_rules.in_upcoming_scope("Draft", e, date(2026, 5, 12))
    assert not trip_rules.in_upcoming_scope("Cancelled", e, date(2026, 5, 1))
    assert trip_rules.in_archive_scope("Draft", e, date(2026, 5, 13))


def test_ring_percent():
    created, start, end = date(2026, 1, 1), date(2026, 1, 11), date(2026, 1, 12)
    assert trip_rules.ring_percent(created, start, end, date(2026, 1, 1)) == 0.0
    assert trip_rules.ring_percent(created, start, end, date(2026, 1, 6)) == 50.0
    assert trip_rules.ring_percent(created, start, end, date(2026, 1, 11)) == 100.0
    assert trip_rules.ring_percent(created, start, end, date(2026, 1, 20)) == 100.0
    assert trip_rules.ring_percent(start, start, end, start) == 100.0
    assert trip_rules.ring_percent(date(2026, 1, 1), date(2026, 1, 4), end, date(2026, 1, 2)) == 33.3


def test_phase_serialized_in_app_timezone(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    sql("UPDATE trips SET start_date=:t, end_date=:t WHERE id=:id", t=today(), id=tid)
    trip = client.get(f"/api/v1/trips/{tid}").get_json()["trip"]
    assert trip["phase"] == "ongoing" and trip["ring_percent"] == 100.0
