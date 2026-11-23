"""Packing CRUD + reminders (D11) and weather (D6)."""
from datetime import datetime, timedelta, timezone

from app.services.weather import condition_label
from tests.factories import create_trip, register, today


def test_packing_crud(client):
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/packing", json={"name": "Snorkel", "note": "Rental?"})
    assert r.status_code == 201
    item = r.get_json()["item"]
    assert item["source"] == "user" and not item["is_packed"]
    u = client.put(f"/api/v1/packing/{item['id']}", json={"is_packed": True})
    assert u.get_json()["item"]["is_packed"] is True
    lst = client.get(f"/api/v1/trips/{tid}/packing").get_json()
    assert lst["packed"] == 1
    assert client.delete(f"/api/v1/packing/{item['id']}").status_code == 200
    assert client.post(f"/api/v1/trips/{tid}/packing", json={"name": ""}).status_code == 400


def test_remind_at_rules(client):
    register(client)
    tid = create_trip(client)["id"]  # ends today+12
    url = f"/api/v1/trips/{tid}/packing"
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert client.post(url, json={"name": "A", "remind_at": past}).status_code == 400
    too_late = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert client.post(url, json={"name": "A", "remind_at": too_late}).status_code == 400
    assert client.post(url, json={"name": "A", "remind_at": "2026-12-01T10:00:00"}).status_code == 400  # naive
    ok = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert client.post(url, json={"name": "A", "remind_at": ok}).status_code == 201
    end_day = (today() + timedelta(days=12)).isoformat() + "T23:30:00+05:30"
    assert client.post(url, json={"name": "B", "remind_at": end_day}).status_code == 201


def test_packing_ownership(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    pid = client.get(f"/api/v1/trips/{tid}/packing").get_json()["items"][0]["id"]
    other = make_client()
    register(other)
    assert other.put(f"/api/v1/packing/{pid}", json={"is_packed": True}).status_code == 404
    assert other.delete(f"/api/v1/packing/{pid}").status_code == 404


def test_weather_unavailable_is_explicit(client):
    register(client)
    tid = create_trip(client)["id"]
    w = client.get(f"/api/v1/trips/{tid}/weather").get_json()["weather"]
    assert w == {"available": False, "daily": [], "message": "Forecast not available yet"}


def test_wmo_mapping():
    assert condition_label(0) == "Clear sky"
    assert condition_label(63) == "Moderate rain"
    assert condition_label(95) == "Thunderstorm"
    assert condition_label(4) == "Unknown" and condition_label(None) == "Unknown"


def test_internal_weather_put(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    payload = {
        "location_name": "Panaji",
        "current": {"temperature_c": 29.5, "weather_code": 2, "observed_at": "2026-11-23T10:00:00+05:30"},
        "daily": [{"date": "2026-11-24", "temp_max_c": 20, "temp_min_c": 31, "precip_prob_max": 40, "weather_code": 61}],
    }
    r = internal.put(f"/api/v1/internal/trips/{tid}/weather", json=payload)
    assert r.status_code == 200, r.get_json()
    w = client.get(f"/api/v1/trips/{tid}/weather").get_json()["weather"]
    assert w["available"] and w["location_name"] == "Panaji"
    day = w["daily"][0]
    assert day["high_c"] >= day["low_c"] and (day["high_c"], day["low_c"]) == (31, 20)
    assert day["condition"] == "Slight rain" and w["current"]["condition"] == "Partly cloudy"


def test_internal_weather_validation_and_auth(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    url = f"/api/v1/internal/trips/{tid}/weather"
    assert internal.put(url, json={"daily": [{"date": "x", "temp_max_c": 1, "temp_min_c": 0}]}).status_code == 400
    assert internal.put(url, json={"daily": [{"date": "2026-11-24", "temp_max_c": 500, "temp_min_c": 0}]}).status_code == 400
    assert internal.put(url, json={}, headers={"X-Webhook-Secret": "nope"}).status_code == 401
    assert internal.put("/api/v1/internal/trips/99999/weather", json={}).status_code == 404
    r = internal.put(url, json={"weather_message": "Provider down"})
    assert r.status_code == 200
    w = client.get(f"/api/v1/trips/{tid}/weather").get_json()["weather"]
    assert w == {"available": False, "daily": [], "message": "Provider down"}
