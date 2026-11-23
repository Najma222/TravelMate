"""CLI: seed-discover, seed-demo, simulate-callback (uses the real callback service)."""
import responses

from tests.factories import create_trip, register


def test_seed_discover_cli(app):
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=["seed-discover"])
    r2 = runner.invoke(args=["seed-discover"])
    assert r1.exit_code == 0 and r2.exit_code == 0, r1.output
    assert "in table" in r2.output


def test_seed_demo_and_refuses_in_production(app, make_client):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["seed-demo"])
    assert r.exit_code == 0, r.output
    assert "already exists" in runner.invoke(args=["seed-demo"]).output
    c = make_client()
    assert c.post("/api/v1/auth/login", json={"email": "demo@travelmate.local", "password": "DemoPass123"}).status_code == 200
    assert len(c.get("/api/v1/trips").get_json()["items"]) == 2
    app.config["ALLOW_DEMO_SEED"] = False
    try:
        r = runner.invoke(args=["seed-demo", "--email", "x@y.zz"])
        assert r.exit_code != 0 and "disabled" in r.output
    finally:
        app.config["ALLOW_DEMO_SEED"] = True


def test_simulate_callback(app, client, sql):
    register(client)
    tid = create_trip(client)["id"]
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "http://n8n.test/webhook/trip", json={})
        client.post(f"/api/v1/trips/{tid}/generate")
    r = app.test_cli_runner().invoke(args=["simulate-callback", "--trip-id", str(tid)])
    assert r.exit_code == 0, r.output
    assert '"status": "Completed"' in r.output
    assert sql("SELECT status FROM trips WHERE id=:id", id=tid)[0][0] == "Completed"
    again = app.test_cli_runner().invoke(args=["simulate-callback", "--trip-id", str(tid)])
    assert "not_processing" in again.output
