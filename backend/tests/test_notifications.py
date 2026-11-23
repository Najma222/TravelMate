"""D9 notifications: inbox, read state, preferences, internal recording + dedupe."""
from datetime import timedelta

from tests.factories import create_trip, register, today


def _post(internal, **kw):
    body = {"notification_type": "trip_reminder", "message": "Your trip starts soon",
            "channels": ["email", "in_app"], "delivery_status": "sent"}
    body.update(kw)
    return internal.post("/api/v1/internal/notifications", json=body)


def test_create_and_list(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    r = _post(internal, trip_id=tid)
    assert r.status_code == 201
    n = r.get_json()["notification"]
    assert n["delivery_status"] == "sent" and n["sent_at"] and n["scheduled_for"] == today().isoformat()
    body = client.get("/api/v1/notifications").get_json()
    assert body["unread_count"] == 1 and body["items"][0]["id"] == n["id"]


def test_dedupe_sent_is_conflict(client, internal, sql):
    register(client)
    tid = create_trip(client)["id"]
    assert _post(internal, trip_id=tid).status_code == 201
    r = _post(internal, trip_id=tid)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "conflict"
    # a different day is a different notification
    other_day = (today() + timedelta(days=1)).isoformat()
    assert _post(internal, trip_id=tid, scheduled_for=other_day).status_code == 201
    assert sql("SELECT count(*) FROM notifications")[0][0] == 2


def test_failed_then_retry_updates_row(client, internal, sql):
    register(client)
    tid = create_trip(client)["id"]
    first = _post(internal, trip_id=tid, delivery_status="failed")
    assert first.status_code == 201 and first.get_json()["notification"]["sent_at"] is None
    retry = _post(internal, trip_id=tid, delivery_status="sent")
    assert retry.status_code == 200
    assert retry.get_json()["notification"]["id"] == first.get_json()["notification"]["id"]
    assert sql("SELECT delivery_status FROM notifications") == [("sent",)]


def test_pending_then_sent(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    assert _post(internal, trip_id=tid, delivery_status="pending").status_code == 201
    assert _post(internal, trip_id=tid, delivery_status="sent").status_code == 200
    assert _post(internal, trip_id=tid, delivery_status="sent").status_code == 409


def test_internal_validation(client, internal):
    register(client)
    tid = create_trip(client)["id"]
    assert _post(internal, trip_id=tid, notification_type="Bad Type").status_code == 400
    assert _post(internal, trip_id=tid, channels=["sms"]).status_code == 400
    assert _post(internal, trip_id=tid, delivery_status="delivered").status_code == 400
    assert _post(internal, trip_id=999999).status_code == 404
    assert _post(internal, trip_id=tid, headers=None).status_code == 201


def test_read_and_read_all(client, internal, make_client):
    register(client)
    tid = create_trip(client)["id"]
    ids = [_post(internal, trip_id=tid, notification_type=f"t{i}x").get_json()["notification"]["id"] for i in range(3)]
    r = client.put(f"/api/v1/notifications/{ids[0]}/read")
    assert r.get_json()["notification"]["is_read"] is True
    assert client.get("/api/v1/notifications?unread=true").get_json()["pagination"]["total"] == 2
    assert client.post("/api/v1/notifications/read-all").get_json()["marked_read"] == 2
    assert client.get("/api/v1/notifications").get_json()["unread_count"] == 0
    other = make_client()
    register(other)
    assert other.put(f"/api/v1/notifications/{ids[1]}/read").status_code == 404
    assert other.get("/api/v1/notifications").get_json()["items"] == []


def test_preferences(client):
    register(client)
    prefs = client.get("/api/v1/notifications/preferences").get_json()["preferences"]
    assert prefs == {"notify_email": True, "notify_telegram": False, "telegram_chat_id": None}
    assert client.put("/api/v1/notifications/preferences", json={"notify_telegram": True}).status_code == 400
    r = client.put("/api/v1/notifications/preferences",
                   json={"notify_telegram": True, "telegram_chat_id": "123456789", "notify_email": False})
    assert r.status_code == 200
    assert r.get_json()["preferences"]["notify_telegram"] is True
    assert client.put("/api/v1/notifications/preferences", json={"telegram_chat_id": "bad id!"}).status_code == 400


def test_reminder_queries(client, internal, sql):
    register(client)
    soon = create_trip(client, start_date=(today() + timedelta(days=2)).isoformat(),
                       end_date=(today() + timedelta(days=4)).isoformat())["id"]
    later = create_trip(client)["id"]  # starts in 10 days
    active = create_trip(client)["id"]
    sql("UPDATE trips SET start_date=:s, end_date=:e WHERE id=:id",
        s=today() - timedelta(days=1), e=today() + timedelta(days=1), id=active)
    up = internal.get("/api/v1/internal/upcoming-trips?days=3").get_json()["items"]
    assert [t["id"] for t in up] == [soon]
    assert up[0]["user"]["email"].endswith("@example.com") and up[0]["unpacked_items"] > 0
    act = internal.get("/api/v1/internal/active-trips").get_json()["items"]
    assert [t["id"] for t in act] == [active] and act[0]["day_number"] == 2
    client.post(f"/api/v1/trips/{later}/bookings", json={"booking_type": "hotel", "status": "Confirmed", "amount": "10"})
    gaps = {g["id"]: g["missing"] for g in internal.get("/api/v1/internal/booking-gaps?days=14").get_json()["items"]}
    assert gaps[later] == ["transport"] and gaps[soon] == ["hotel", "transport"]
    assert internal.get("/api/v1/internal/upcoming-trips?days=abc").status_code == 400
    assert internal.get("/api/v1/internal/upcoming-trips", headers={"X-Webhook-Secret": "x"}).status_code == 401
