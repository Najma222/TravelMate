"""Itinerary items, trip days (D7) and trip stops (deferred unique reorder)."""
from datetime import timedelta

from tests.factories import create_trip, register, today


def test_itinerary_empty_days_default_titles(client):
    register(client)
    trip = create_trip(client)
    body = client.get(f"/api/v1/trips/{trip['id']}/itinerary").get_json()
    assert [d["title"] for d in body["days"]] == ["Day 1", "Day 2", "Day 3"]
    assert body["days"][1]["date"] == (today() + timedelta(days=11)).isoformat()


def test_itinerary_crud(client):
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/itinerary", json={
        "day_number": 2, "activity_name": "Fort Aguada", "start_time": "09:00", "end_time": "11:30",
        "estimated_cost": "250.50"})
    assert r.status_code == 201
    item = r.get_json()["item"]
    assert item["is_edited"] and item["estimated_cost"] == "250.50" and item["start_time"] == "09:00"
    upd = client.put(f"/api/v1/itinerary/{item['id']}", json={"activity_name": "Fort Aguada Lighthouse"})
    assert upd.status_code == 200 and upd.get_json()["item"]["activity_name"] == "Fort Aguada Lighthouse"
    assert client.put(f"/api/v1/itinerary/{item['id']}", json={"end_time": "08:00"}).status_code == 400
    assert client.post(f"/api/v1/trips/{tid}/itinerary",
                       json={"day_number": 9, "activity_name": "X"}).status_code == 400
    days = client.get(f"/api/v1/trips/{tid}/itinerary").get_json()["days"]
    assert len(days[1]["items"]) == 1
    assert client.delete(f"/api/v1/itinerary/{item['id']}").status_code == 200
    assert client.delete(f"/api/v1/itinerary/{item['id']}").status_code == 404


def test_itinerary_locked_while_processing(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    sql("UPDATE trips SET status='Processing' WHERE id=:id", id=tid)
    r = client.post(f"/api/v1/trips/{tid}/itinerary", json={"day_number": 1, "activity_name": "X"})
    assert r.status_code == 409


def test_update_day_title_and_stop(client):
    register(client)
    tid = create_trip(client)["id"]
    stop = client.post(f"/api/v1/trips/{tid}/stops", json={"name": "Panaji"}).get_json()["stop"]
    r = client.put(f"/api/v1/trips/{tid}/days/2", json={"title": "Old Goa walk", "stop_id": stop["id"]})
    assert r.status_code == 200
    day = r.get_json()["day"]
    assert day["title"] == "Old Goa walk" and day["stop"]["name"] == "Panaji"
    assert client.put(f"/api/v1/trips/{tid}/days/7", json={"title": "x"}).status_code == 400
    assert client.put(f"/api/v1/trips/{tid}/days/1", json={"stop_id": 999999}).status_code == 400


def test_stops_crud_and_reorder(client):
    register(client)
    tid = create_trip(client)["id"]
    ids = [client.post(f"/api/v1/trips/{tid}/stops", json={"name": n, "latitude": 15.1, "longitude": 73.9})
           .get_json()["stop"]["id"] for n in ("A", "B", "C")]
    r = client.put(f"/api/v1/trips/{tid}/stops/order", json={"stop_ids": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200
    assert [(s["id"], s["position"]) for s in r.get_json()["stops"]] == [(ids[2], 1), (ids[0], 2), (ids[1], 3)]
    assert client.put(f"/api/v1/trips/{tid}/stops/order", json={"stop_ids": [ids[0], ids[1]]}).status_code == 400
    assert client.put(f"/api/v1/trips/{tid}/stops/order",
                      json={"stop_ids": [ids[0], ids[0], ids[1]]}).status_code == 400
    assert client.put(f"/api/v1/stops/{ids[0]}", json={"name": "A2"}).get_json()["stop"]["name"] == "A2"
    assert client.delete(f"/api/v1/stops/{ids[2]}").status_code == 200
    stops = client.get(f"/api/v1/trips/{tid}/places").get_json()["stops"]
    assert [(s["id"], s["position"]) for s in stops] == [(ids[0], 1), (ids[1], 2)]
    assert client.post(f"/api/v1/trips/{tid}/stops", json={"name": "X", "latitude": 200}).status_code == 400


def test_stop_ownership(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    sid = client.post(f"/api/v1/trips/{tid}/stops", json={"name": "A"}).get_json()["stop"]["id"]
    other = make_client()
    register(other)
    assert other.put(f"/api/v1/stops/{sid}", json={"name": "hack"}).status_code == 404
    assert other.delete(f"/api/v1/stops/{sid}").status_code == 404
