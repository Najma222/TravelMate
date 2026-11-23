"""POST /internal/trips/{id}/result — idempotency, stale protection, replacement rules."""
import uuid

import pytest
import responses

from tests.factories import completed_payload, create_trip, register

N8N_URL = "http://n8n.test/webhook/trip"


@pytest.fixture
def processing_trip(client):
    """A trip in Processing with a known generation_id."""
    register(client)
    trip = create_trip(client)
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, N8N_URL, json={}, status=200)
        r = client.post(f"/api/v1/trips/{trip['id']}/generate")
    assert r.status_code == 202
    return trip["id"], r.get_json()["trip"]["generation_id"]


def _result(internal, tid, payload, secret=None):
    headers = {"X-Webhook-Secret": secret} if secret is not None else None
    return internal.post(f"/api/v1/internal/trips/{tid}/result", json=payload, headers=headers)


def test_callback_completed(client, internal, processing_trip):
    tid, gid = processing_trip
    r = _result(internal, tid, completed_payload(gid))
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["status"] == "Completed" and body["activities_saved"] == 6
    trip = client.get(f"/api/v1/trips/{tid}").get_json()["trip"]
    assert trip["status"] == "Completed" and trip["error_message"] is None
    itin = client.get(f"/api/v1/trips/{tid}/itinerary").get_json()
    assert itin["days"][0]["title"] == "Explore day 1"
    assert len(itin["days"][2]["items"]) == 2
    expenses = client.get(f"/api/v1/trips/{tid}/expenses").get_json()["items"]
    cats = sorted(e["category"] for e in expenses)
    assert cats == ["food", "misc", "transport"]  # D4 normalisation
    assert all(e["source"] == "n8n" and not e["is_confirmed"] for e in expenses)


def test_missing_and_invalid_secret(internal, processing_trip, sql):
    tid, gid = processing_trip
    c = internal
    assert _result(c, tid, completed_payload(gid), secret="").status_code == 401
    r = _result(c, tid, completed_payload(gid), secret="wrong-secret")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "unauthorized"
    assert sql("SELECT count(*) FROM audit_logs WHERE action='internal_auth_failed'")[0][0] == 2
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Processing"


def test_stale_generation_ignored(internal, processing_trip, sql):
    tid, _gid = processing_trip
    r = _result(internal, tid, completed_payload(str(uuid.uuid4())))
    assert r.status_code == 200
    assert r.get_json() == {"ignored": True, "reason": "stale_generation"}
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Processing"


def test_duplicate_callback_is_idempotent(client, internal, processing_trip, sql):
    tid, gid = processing_trip
    assert _result(internal, tid, completed_payload(gid)).get_json()["status"] == "Completed"
    r = _result(internal, tid, completed_payload(gid))
    assert r.get_json() == {"ignored": True, "reason": "not_processing"}
    assert sql("SELECT count(*) FROM itineraries WHERE trip_id=:id", id=tid)[0][0] == 6


def test_cancelled_trip_ignored(client, internal, processing_trip, sql):
    tid, gid = processing_trip
    assert client.post(f"/api/v1/trips/{tid}/cancel").status_code == 200
    r = _result(internal, tid, completed_payload(gid))
    assert r.get_json() == {"ignored": True, "reason": "cancelled"}
    assert sql("SELECT count(*) FROM itineraries WHERE trip_id=:id", id=tid)[0][0] == 0


def test_wrong_trip_id(internal, processing_trip):
    _tid, gid = processing_trip
    assert _result(internal, 987654, completed_payload(gid)).status_code == 404


def test_missing_generation_id_is_400_without_state_change(internal, processing_trip, sql):
    tid, gid = processing_trip
    payload = completed_payload(gid)
    del payload["generation_id"]
    assert _result(internal, tid, payload).status_code == 400
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Processing"


def test_failed_callback(internal, processing_trip, sql):
    tid, gid = processing_trip
    r = _result(internal, tid, {"generation_id": gid, "status": "Failed", "error_message": "LLM quota"})
    assert r.get_json()["status"] == "Failed"
    assert sql("SELECT status, error_message FROM trips WHERE id=:id", id=tid)[0] == ("Failed", "LLM quota")


def test_invalid_payload_marks_failed(internal, processing_trip, sql):
    tid, gid = processing_trip
    payload = completed_payload(gid)
    payload["itinerary"] = [payload["itinerary"][0]] * 201  # > 200 rows
    r = _result(internal, tid, payload)
    assert r.status_code == 400
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Failed"


def test_too_many_expenses_is_invalid(internal, processing_trip, sql):
    tid, gid = processing_trip
    payload = completed_payload(gid, expenses=[{"category": "food", "amount": "1"}] * 51)
    assert _result(internal, tid, payload).status_code == 400
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Failed"


def test_invalid_activities_dropped(client, internal, processing_trip):
    tid, gid = processing_trip
    payload = completed_payload(gid, days=1)
    payload["itinerary"] += [
        {"day_number": 1},                                         # no name
        {"day_number": 99, "activity_name": "Out of range"},
        {"day_number": 1, "activity_name": "Bad time", "start_time": "25:00"},
        {"day_number": 1, "activity_name": "Backwards", "start_time": "12:00", "end_time": "10:00"},
        {"day_number": 1, "activity_name": "Negative", "estimated_cost": "-5"},
        "not-an-object",
    ]
    body = _result(internal, tid, payload).get_json()
    assert body["activities_saved"] == 2 and body["activities_dropped"] == 6


def test_zero_valid_activities_fails(internal, processing_trip, sql):
    tid, gid = processing_trip
    payload = completed_payload(gid, itinerary=[{"day_number": 1}, {"activity_name": "no day"}])
    r = _result(internal, tid, payload)
    assert r.status_code == 200 and r.get_json()["status"] == "Failed"
    assert sql("SELECT status, error_message FROM trips WHERE id=:id", id=tid)[0] == (
        "Failed", "No valid places found")


def test_preserves_confirmed_booking_expenses_and_user_stops(client, internal, processing_trip, sql):
    tid, gid = processing_trip
    sql("UPDATE trips SET status='Draft' WHERE id=:id", id=tid)
    client.post(f"/api/v1/trips/{tid}/stops", json={"name": "User stop"})
    client.post(f"/api/v1/trips/{tid}/expenses",
                json={"category": "food", "amount": "100.00", "is_confirmed": True})
    client.post(f"/api/v1/trips/{tid}/expenses", json={"category": "food", "amount": "999.00"})
    client.post(f"/api/v1/trips/{tid}/bookings",
                json={"booking_type": "hotel", "amount": "5000", "status": "Confirmed"})
    sql("UPDATE trips SET status='Processing' WHERE id=:id", id=tid)
    # first generation adds a generated stop
    _result(internal, tid, completed_payload(gid))
    # second generation must replace generated stops but keep user stop
    sql("UPDATE trips SET status='Processing' WHERE id=:id", id=tid)
    _result(internal, tid, completed_payload(gid, stops=[{"name": "South Goa"}]))
    stops = sql("SELECT name, source, position FROM trip_stops WHERE trip_id=:id ORDER BY position", id=tid)
    assert stops == [("User stop", "user", 1), ("South Goa", "generated", 2)]
    rows = sql("SELECT amount::text, is_confirmed, source FROM expenses WHERE trip_id=:id ORDER BY id", id=tid)
    kept = [r for r in rows if r[2] != "n8n"]
    assert ("100.00", True, "user") in kept
    assert ("5000.00", True, "booking") in kept
    assert all(r[0] != "999.00" for r in rows)  # unconfirmed user estimate replaced
    assert sum(1 for r in rows if r[2] == "n8n") == 3


def test_callback_transaction_rolls_back_on_error(client, internal, processing_trip, sql, monkeypatch):
    tid, gid = processing_trip
    from app.services import packing_seed

    def boom(*a, **k):
        raise RuntimeError("simulated failure mid-transaction")

    monkeypatch.setattr(packing_seed, "ensure_jacket", boom)
    r = _result(internal, tid, completed_payload(gid))
    assert r.status_code == 500
    assert r.get_json()["error"]["code"] == "internal_error"
    assert sql("SELECT count(*) FROM itineraries WHERE trip_id=:id", id=tid)[0][0] == 0
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Processing"


def test_callback_stores_weather_and_auto_jacket(client, internal, processing_trip, sql):
    tid, gid = processing_trip
    weather = {"location_name": "Goa", "daily": [
        {"date": "2026-12-01", "temp_max_c": 28, "temp_min_c": 14.5, "precip_prob_max": 10, "weather_code": 1}]}
    body = _result(internal, tid, completed_payload(gid, weather=weather)).get_json()
    assert body["jacket_added"] is True
    items = client.get(f"/api/v1/trips/{tid}/packing").get_json()["items"]
    jackets = [i for i in items if "jacket" in i["name"].lower()]
    assert len(jackets) == 1 and jackets[0]["source"] == "auto"
    w = client.get(f"/api/v1/trips/{tid}/weather").get_json()["weather"]
    assert w["available"] and w["daily"][0]["low_c"] == 14.5


def test_auto_jacket_not_duplicated(client, internal, processing_trip, sql):
    tid, gid = processing_trip
    sql("UPDATE trips SET status='Draft' WHERE id=:id", id=tid)
    client.post(f"/api/v1/trips/{tid}/packing", json={"name": "Rain Jacket"})
    sql("UPDATE trips SET status='Processing' WHERE id=:id", id=tid)
    weather = {"daily": [{"date": "2026-12-01", "temp_max_c": 10, "temp_min_c": 2}]}
    assert _result(internal, tid, completed_payload(gid, weather=weather)).get_json()["jacket_added"] is False


def test_no_jacket_when_warm(internal, processing_trip):
    tid, gid = processing_trip
    weather = {"daily": [{"date": "2026-12-01", "temp_max_c": 33, "temp_min_c": 22}]}
    assert _result(internal, tid, completed_payload(gid, weather=weather)).get_json()["jacket_added"] is False
