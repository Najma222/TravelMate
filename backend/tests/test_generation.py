"""POST /trips/{id}/generate — atomic claim, commit-before-call, n8n retry rules, sweeper."""
import threading
import uuid

import requests
import responses

from tests.factories import create_trip, register

N8N_URL = "http://n8n.test/webhook/trip"


@responses.activate
def test_generate_success(client, sql):
    responses.add(responses.POST, N8N_URL, json={"ok": True}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/generate")
    assert r.status_code == 202
    trip = r.get_json()["trip"]
    assert trip["status"] == "Processing"
    gid = trip["generation_id"]
    uuid.UUID(gid)
    sent = responses.calls[0].request
    assert sent.headers["X-Webhook-Secret"] == "test-internal-secret"
    import json
    body = json.loads(sent.body)
    assert body["generation_id"] == gid and body["trip_id"] == tid
    assert body["budget"] == "30000.00"
    assert body["callback_url"].endswith(f"/api/v1/internal/trips/{tid}/result")
    assert sql("SELECT count(*) FROM audit_logs WHERE action='generation_started'")[0][0] == 1


@responses.activate
def test_generation_committed_before_n8n_call(client, app, sql):
    """When n8n is called the Processing state must already be visible to other connections."""
    seen = {}

    def callback(request):
        seen["status"] = sql("SELECT status FROM trips")[0][0]
        return (200, {}, "{}")

    responses.add_callback(responses.POST, N8N_URL, callback=callback)
    register(client)
    tid = create_trip(client)["id"]
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 202
    assert seen["status"] == "Processing"


@responses.activate
def test_generate_conflict_when_processing_or_cancelled(client, sql):
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 202
    r = client.post(f"/api/v1/trips/{tid}/generate")
    assert r.status_code == 409 and r.get_json()["error"]["details"]["status"] == "Processing"
    sql("UPDATE trips SET status='Cancelled' WHERE id=:id", id=tid)
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 409
    assert len(responses.calls) == 1


def test_generate_not_owned_is_404(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    other = make_client()
    register(other)
    assert other.post(f"/api/v1/trips/{tid}/generate").status_code == 404
    assert other.post("/api/v1/trips/999999/generate").status_code == 404


@responses.activate
def test_concurrent_generate_only_one_wins(app, client):
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client, email="race@example.com")
    tid = create_trip(client)["id"]
    cookie = client.raw().get_cookie("tm_session").value
    results = []
    barrier = threading.Barrier(5)

    def worker():
        c = app.test_client()
        c.set_cookie("tm_session", cookie)
        barrier.wait()
        r = c.post(f"/api/v1/trips/{tid}/generate", json={},
                   headers={"Origin": "http://localhost:5173"})
        results.append(r.status_code)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [202, 409, 409, 409, 409]


@responses.activate
def test_upstream_failure_marks_failed_and_502(client, sql):
    responses.add(responses.POST, N8N_URL, json={"err": 1}, status=500)
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/generate")
    assert r.status_code == 502
    assert r.get_json()["error"]["code"] == "upstream_error"
    status, msg = sql("SELECT status, error_message FROM trips WHERE id=:id", id=tid)[0]
    assert status == "Failed" and msg
    # Failed trips can be retried
    responses.replace(responses.POST, N8N_URL, json={}, status=200)
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 202


@responses.activate
def test_connection_error_retried_once(client):
    responses.add(responses.POST, N8N_URL, body=requests.exceptions.ConnectionError("refused"))
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/generate")
    assert r.status_code == 202
    assert len(responses.calls) == 2


@responses.activate
def test_connection_error_twice_fails(client):
    responses.add(responses.POST, N8N_URL, body=requests.exceptions.ConnectionError("refused"))
    responses.add(responses.POST, N8N_URL, body=requests.exceptions.ConnectionError("refused"))
    register(client)
    tid = create_trip(client)["id"]
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 502
    assert len(responses.calls) == 2


@responses.activate
def test_timeout_never_retried(client, sql):
    responses.add(responses.POST, N8N_URL, body=requests.exceptions.ReadTimeout("slow"))
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/generate")
    assert r.status_code == 502
    assert len(responses.calls) == 1
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Failed"


@responses.activate
def test_connect_timeout_never_retried(client):
    responses.add(responses.POST, N8N_URL, body=requests.exceptions.ConnectTimeout("slow connect"))
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    assert client.post(f"/api/v1/trips/{tid}/generate").status_code == 502
    assert len(responses.calls) == 1


@responses.activate
def test_status_endpoint_sweeps_stuck_trip(client, sql):
    responses.add(responses.POST, N8N_URL, json={}, status=200)
    register(client)
    tid = create_trip(client)["id"]
    client.post(f"/api/v1/trips/{tid}/generate")
    assert client.get(f"/api/v1/trips/{tid}/status").get_json()["trip"]["status"] == "Processing"
    sql("UPDATE trips SET processing_started_at = now() - interval '11 minutes' WHERE id=:id", id=tid)
    trip = client.get(f"/api/v1/trips/{tid}/status").get_json()["trip"]
    assert trip["status"] == "Failed"
    assert trip["error_message"] == "Generation timed out. Please retry."


def test_internal_sweep_stuck(client, internal, sql):
    register(client)
    t1 = create_trip(client)["id"]
    t2 = create_trip(client)["id"]
    sql("UPDATE trips SET status='Processing', processing_started_at = now() - interval '15 minutes' WHERE id=:id", id=t1)
    sql("UPDATE trips SET status='Processing', processing_started_at = now() - interval '2 minutes' WHERE id=:id", id=t2)
    r = internal.post("/api/v1/internal/sweep-stuck", json={})
    assert r.get_json() == {"swept": 1, "trip_ids": [t1]}
    # concurrent/repeated sweeps are no-ops
    assert internal.post("/api/v1/internal/sweep-stuck", json={}).get_json()["swept"] == 0
    assert sql("SELECT status FROM trips WHERE id=:id", id=t2)[0][0] == "Processing"
