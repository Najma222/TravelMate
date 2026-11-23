"""D10 bookings and transactional booking -> expense sync."""
from unittest import mock

from tests.factories import create_trip, register


def _linked(sql, booking_id):
    return sql("SELECT category, amount::text, is_confirmed, source FROM expenses WHERE booking_id=:b",
               b=booking_id)


def test_create_confirmed_hotel_creates_expense(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/bookings", json={
        "booking_type": "hotel", "provider": "Taj", "amount": "12000.50", "status": "Confirmed",
        "start_at": "2026-12-01T14:00:00", "start_tz": "Asia/Kolkata",
        "end_at": "2026-12-03T11:00:00+05:30", "end_tz": "Asia/Kolkata"})
    assert r.status_code == 201, r.get_json()
    b = r.get_json()["booking"]
    assert b["linked_expense_id"] is not None
    assert b["start_at"] == "2026-12-01T08:30:00+00:00"
    assert _linked(sql, b["id"]) == [("accommodation", "12000.50", True, "booking")]


def test_status_changes_upsert_and_delete(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    b = client.post(f"/api/v1/trips/{tid}/bookings",
                    json={"booking_type": "flight", "amount": "5000"}).get_json()["booking"]
    assert b["status"] == "Not Booked" and _linked(sql, b["id"]) == []
    client.put(f"/api/v1/bookings/{b['id']}", json={"status": "Confirmed"})
    assert _linked(sql, b["id"]) == [("transport", "5000.00", True, "booking")]
    client.put(f"/api/v1/bookings/{b['id']}", json={"amount": "5500"})
    assert _linked(sql, b["id"]) == [("transport", "5500.00", True, "booking")]
    client.put(f"/api/v1/bookings/{b['id']}", json={"booking_type": "hotel"})
    assert _linked(sql, b["id"])[0][0] == "accommodation"
    client.put(f"/api/v1/bookings/{b['id']}", json={"amount": "0"})
    assert _linked(sql, b["id"]) == []
    client.put(f"/api/v1/bookings/{b['id']}", json={"amount": "10"})
    assert len(_linked(sql, b["id"])) == 1
    client.put(f"/api/v1/bookings/{b['id']}", json={"status": "Cancelled"})
    assert _linked(sql, b["id"]) == []
    # repeated confirm never duplicates
    for _ in range(3):
        client.put(f"/api/v1/bookings/{b['id']}", json={"status": "Confirmed"})
    assert sql("SELECT count(*) FROM expenses WHERE booking_id=:b", b=b["id"])[0][0] == 1


def test_linked_expense_is_locked(client):
    register(client)
    tid = create_trip(client)["id"]
    b = client.post(f"/api/v1/trips/{tid}/bookings",
                    json={"booking_type": "bus", "amount": "800", "status": "Confirmed"}).get_json()["booking"]
    eid = b["linked_expense_id"]
    r = client.put(f"/api/v1/expenses/{eid}", json={"amount": "1"})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "conflict"
    assert client.delete(f"/api/v1/expenses/{eid}").status_code == 409


def test_delete_booking_removes_expense(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    b = client.post(f"/api/v1/trips/{tid}/bookings",
                    json={"booking_type": "train", "amount": "900", "status": "Confirmed"}).get_json()["booking"]
    assert client.delete(f"/api/v1/bookings/{b['id']}").status_code == 200
    assert sql("SELECT count(*) FROM expenses WHERE trip_id=:t", t=tid)[0][0] == 0


def test_sync_is_atomic(client, sql):
    register(client)
    tid = create_trip(client)["id"]
    b = client.post(f"/api/v1/trips/{tid}/bookings",
                    json={"booking_type": "train", "amount": "900"}).get_json()["booking"]
    from app.services import booking_sync

    with mock.patch.object(booking_sync, "_description", side_effect=RuntimeError("boom")):
        r = client.put(f"/api/v1/bookings/{b['id']}", json={"status": "Confirmed", "amount": "1000"})
    assert r.status_code == 500
    assert sql("SELECT status, amount::text FROM bookings WHERE id=:b", b=b["id"]) == [("Not Booked", "900.00")]
    assert _linked(sql, b["id"]) == []


def test_booking_validation(client):
    register(client)
    tid = create_trip(client)["id"]
    url = f"/api/v1/trips/{tid}/bookings"
    assert client.post(url, json={"booking_type": "car"}).status_code == 400
    assert client.post(url, json={"booking_type": "hotel", "status": "Maybe"}).status_code == 400
    assert client.post(url, json={"booking_type": "hotel", "amount": "-1"}).status_code == 400
    assert client.post(url, json={"booking_type": "hotel", "start_tz": "Mars/Base"}).status_code == 400
    r = client.post(url, json={"booking_type": "hotel", "start_at": "2026-12-01T10:00:00"})
    assert r.status_code == 400  # naive datetime without tz
    r = client.post(url, json={"booking_type": "hotel", "start_at": "2026-12-02T10:00:00+05:30",
                               "end_at": "2026-12-01T10:00:00+05:30"})
    assert r.status_code == 400


def test_booking_list_and_ownership(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    bid = client.post(f"/api/v1/trips/{tid}/bookings", json={"booking_type": "hotel"}).get_json()["booking"]["id"]
    assert len(client.get(f"/api/v1/trips/{tid}/bookings").get_json()["items"]) == 1
    other = make_client()
    register(other)
    assert other.put(f"/api/v1/bookings/{bid}", json={"status": "Confirmed"}).status_code == 404
    assert other.delete(f"/api/v1/bookings/{bid}").status_code == 404


def test_booking_links(client):
    register(client)
    tid = create_trip(client, destination="Goa & Co")["id"]
    body = client.get(f"/api/v1/trips/{tid}/booking-links").get_json()
    types = {l["booking_type"] for l in body["links"]}
    assert types == {"hotel", "flight", "train", "bus"}
    hotel = next(l for l in body["links"] if l["booking_type"] == "hotel")
    assert "ss=Goa+%26+Co" in hotel["url"] and hotel["url"].startswith("https://")
    assert "not" in body["disclaimer"].lower()
