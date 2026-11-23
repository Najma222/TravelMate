"""Registration, login, sessions, nonce rotation, rate limits, profile, account deletion."""
from unittest import mock

from app.services import auth_service
from tests.factories import PASSWORD, register


def test_register_success_sets_session_and_hides_secrets(client, sql):
    r = client.post("/api/v1/auth/register",
                    json={"name": "Asha", "email": "  Asha@Example.COM ", "password": PASSWORD})
    assert r.status_code == 201
    user = r.get_json()["user"]
    assert user["email"] == "asha@example.com"
    assert "password_hash" not in user and "session_nonce" not in user
    assert client.get("/api/v1/auth/me").status_code == 200
    (pw_hash,), = sql("SELECT password_hash FROM users")
    assert pw_hash.startswith("$2") and PASSWORD not in pw_hash


def test_session_cookie_flags(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "A", "email": "c@example.com", "password": PASSWORD})
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Expires=" in cookie  # permanent 7-day session


def test_register_duplicate_email(client, make_client):
    register(client, email="dup@example.com")
    r = make_client().post("/api/v1/auth/register",
                           json={"name": "B", "email": "DUP@example.com", "password": PASSWORD})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "conflict"


def test_register_invalid_email(client):
    r = client.post("/api/v1/auth/register", json={"name": "A", "email": "not-an-email", "password": PASSWORD})
    assert r.status_code == 400
    assert "email" in r.get_json()["error"]["details"]["fields"]


def test_register_weak_passwords(client):
    for pw in ("short1", "lettersonly", "12345678901", "x" * 80 + "1"):
        r = client.post("/api/v1/auth/register", json={"name": "A", "email": "w@example.com", "password": pw})
        assert r.status_code == 400, pw
        assert "password" in r.get_json()["error"]["details"]["fields"]


def test_register_missing_fields(client):
    r = client.post("/api/v1/auth/register", json={})
    fields = r.get_json()["error"]["details"]["fields"]
    assert set(fields) == {"name", "email", "password"}


def test_login_success(client, make_client):
    register(client, email="l@example.com")
    c2 = make_client()
    r = c2.post("/api/v1/auth/login", json={"email": "L@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert c2.get("/api/v1/auth/me").get_json()["user"]["email"] == "l@example.com"


def test_login_wrong_password_generic(client, make_client, sql):
    register(client, email="l2@example.com")
    r = make_client().post("/api/v1/auth/login", json={"email": "l2@example.com", "password": "Wrong123x"})
    assert r.status_code == 401
    assert r.get_json()["error"]["message"] == "Invalid email or password"
    assert sql("SELECT count(*) FROM audit_logs WHERE action='login_failed'")[0][0] == 1


def test_login_unknown_email_runs_dummy_bcrypt(client):
    with mock.patch.object(auth_service, "check_password", wraps=auth_service.check_password) as spy:
        r = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "Whatever1"})
    assert r.status_code == 401
    assert r.get_json()["error"]["message"] == "Invalid email or password"
    assert spy.call_count == 1
    assert spy.call_args[0][0] == auth_service._dummy_hash()


def test_unauthenticated_access(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "unauthorized"


def test_logout_invalidates_session_and_other_copies(client, app):
    register(client, email="out@example.com")
    raw = client.raw()
    # A copy of the signed cookie (e.g. stolen) must stop working after logout.
    stolen = raw.get_cookie("tm_session").value
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    other = app.test_client()
    other.set_cookie("tm_session", stolen)
    assert other.get("/api/v1/auth/me").status_code == 401


def test_change_password_rotates_nonce(client, make_client, app):
    register(client, email="cp@example.com")
    c2 = make_client()
    c2.post("/api/v1/auth/login", json={"email": "cp@example.com", "password": PASSWORD})
    assert c2.get("/api/v1/auth/me").status_code == 200
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": PASSWORD, "new_password": "N3wPassword!"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200   # this session survives
    assert c2.get("/api/v1/auth/me").status_code == 401       # other sessions die
    c3 = make_client()
    assert c3.post("/api/v1/auth/login", json={"email": "cp@example.com", "password": PASSWORD}).status_code == 401
    assert c3.post("/api/v1/auth/login", json={"email": "cp@example.com", "password": "N3wPassword!"}).status_code == 200


def test_change_password_wrong_current(client):
    register(client)
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "Nope12345", "new_password": "N3wPassword!"})
    assert r.status_code == 400


def test_tampered_cookie_rejected(client, app):
    other = app.test_client()
    other.set_cookie("tm_session", "eyJ1aWQiOjF9.forged.signature")
    assert other.get("/api/v1/auth/me").status_code == 401


def test_ip_rate_limit_10_per_minute(client):
    codes = [client.post("/api/v1/auth/login", json={"email": f"x{i}@example.com", "password": "Bad12345"}).status_code
             for i in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    r = client.post("/api/v1/auth/login", json={"email": "y@example.com", "password": "Bad12345"})
    assert r.get_json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in r.headers


def test_failed_login_lockout_per_email(client, make_client, app):
    register(client, email="lock@example.com")
    for i in range(5):
        c = make_client()
        r = c.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "Wrong1234"},
                   environ_base={"REMOTE_ADDR": f"10.0.0.{i}"})
        assert r.status_code == 401
    # Even the correct password is refused while locked, from a fresh IP.
    r = make_client().post("/api/v1/auth/login", json={"email": "LOCK@example.com", "password": PASSWORD},
                           environ_base={"REMOTE_ADDR": "10.0.1.1"})
    assert r.status_code == 429
    assert r.get_json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0
    # Other accounts are unaffected.
    register(make_client(), email="free@example.com")
    r2 = make_client().post("/api/v1/auth/login", json={"email": "free@example.com", "password": PASSWORD},
                            environ_base={"REMOTE_ADDR": "10.0.1.2"})
    assert r2.status_code == 200


def test_profile_update(client):
    register(client)
    r = client.put("/api/v1/auth/profile", json={"name": "New Name", "ui_prefs": {"theme": "dark", "n": 1.5}})
    assert r.status_code == 200
    u = r.get_json()["user"]
    assert u["name"] == "New Name" and u["ui_prefs"] == {"theme": "dark", "n": 1.5}
    bad = client.put("/api/v1/auth/profile", json={"ui_prefs": {"x": "y" * 5000}})
    assert bad.status_code == 400


def test_delete_account(client, make_client):
    register(client, email="del@example.com")
    assert client.delete("/api/v1/auth/me", json={"password": "wrong"}).status_code == 400
    assert client.delete("/api/v1/auth/me", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    r = make_client().post("/api/v1/auth/login", json={"email": "del@example.com", "password": PASSWORD})
    assert r.status_code == 401
