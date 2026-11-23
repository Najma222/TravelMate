"""Health, request id, D12 origin/content-type checks, security headers, error envelope."""
from tests.conftest import ORIGIN
from tests.factories import PASSWORD, register


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "database": "ok"}


def test_request_id_generated_and_echoed(client):
    r = client.get("/health")
    assert len(r.headers["X-Request-ID"]) == 36
    r2 = client.get("/health", headers={"X-Request-ID": "abc12345-client-id"})
    assert r2.headers["X-Request-ID"] == "abc12345-client-id"
    r3 = client.get("/health", headers={"X-Request-ID": "bad id with spaces <script>"})
    assert r3.headers["X-Request-ID"] != "bad id with spaces <script>"


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    body = r.get_json()
    assert body["error"]["code"] == "not_found"
    assert set(body["error"]) == {"code", "message", "details"}


def test_method_not_allowed_envelope(client):
    r = client.raw().patch("/health")
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == "method_not_allowed"


def test_missing_origin_and_referer_rejected(client):
    r = client.raw().post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 403
    assert r.get_json()["error"]["details"]["reason"] == "origin_missing"


def test_bad_origin_rejected(client):
    r = client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == "forbidden"


def test_valid_referer_accepted_when_no_origin(client):
    raw = client.raw()
    r = raw.post("/api/v1/auth/register",
                 json={"name": "R", "email": "ref@example.com", "password": PASSWORD},
                 headers={"Referer": ORIGIN + "/signup?x=1"})
    assert r.status_code == 201


def test_invalid_referer_rejected(client):
    r = client.raw().post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"},
                          headers={"Referer": "https://evil.example/page"})
    assert r.status_code == 403
    assert r.get_json()["error"]["details"]["reason"] == "referer_not_allowed"


def test_wrong_content_type_rejected(client):
    r = client.raw().post("/api/v1/auth/login", data="email=a@b.co&password=x",
                          headers={"Origin": ORIGIN},
                          content_type="application/x-www-form-urlencoded")
    assert r.status_code == 403
    assert r.get_json()["error"]["details"]["reason"] == "content_type_not_allowed"


def test_multipart_rejected_on_non_upload_route(client):
    register(client)
    r = client.upload("/api/v1/trips", data={"origin": "x"})
    assert r.status_code == 403


def test_multipart_allowed_on_upload_route(client):
    register(client)
    r = client.upload("/api/v1/auth/avatar", data={})
    # passes the CSRF layer; fails validation because no file was sent
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "validation_error"


def test_internal_routes_skip_origin_check_but_need_secret(client, internal):
    r = client.raw().post("/api/v1/internal/sweep-stuck", json={})
    assert r.status_code == 401
    r2 = internal.post("/api/v1/internal/sweep-stuck", json={})
    assert r2.status_code == 200


def test_get_requests_not_subject_to_csrf(client):
    r = client.raw().get("/api/v1/discover/destinations")
    assert r.status_code == 200


def test_csrf_rejection_is_audited(client, sql):
    client.raw().post("/api/v1/auth/login", json={}, headers={"Origin": "https://evil.example"})
    rows = sql("SELECT action, outcome FROM audit_logs WHERE action='csrf_rejected'")
    assert rows == [("csrf_rejected", "denied")]


def test_malformed_json_is_validation_error(client):
    r = client.raw().post("/api/v1/auth/login", data="{not json",
                          headers={"Origin": ORIGIN}, content_type="application/json")
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "validation_error"


def test_json_array_body_rejected(client):
    r = client.post("/api/v1/auth/login", json=[1, 2])
    assert r.status_code == 400
