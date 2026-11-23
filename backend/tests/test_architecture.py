"""Static/structural checks for AGENTS.md hard rules and the route audit."""
import ast
import os
import re

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(BACKEND, "app")

PUBLIC = {
    ("GET", "/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/discover/destinations"),
    ("GET", "/media/<path:filename>"),
}


def _py_files(sub):
    d = os.path.join(APP, sub)
    return [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".py")]


def test_every_route_is_authenticated_or_explicitly_public(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        methods = rule.methods - {"HEAD", "OPTIONS"}
        for m in methods:
            key = (m, rule.rule)
            if key in PUBLIC:
                assert getattr(view, "_public", False), key
                continue
            if rule.rule.startswith("/api/v1/internal/"):
                assert getattr(view, "_internal_only", False), key
            else:
                assert getattr(view, "_login_required", False), key


def test_all_api_routes_are_versioned(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        assert rule.rule.startswith("/api/v1/") or rule.rule in ("/health", "/media/<path:filename>"), rule.rule


def test_required_routes_exist(app):
    routes = {(m, r.rule) for r in app.url_map.iter_rules() for m in r.methods - {"HEAD", "OPTIONS"}}
    expected = """
    POST /api/v1/auth/logout|GET /api/v1/auth/me|PUT /api/v1/auth/profile|POST /api/v1/auth/avatar
    POST /api/v1/auth/change-password|DELETE /api/v1/auth/me|POST /api/v1/trips|GET /api/v1/trips
    GET /api/v1/trips/<int:trip_id>|PUT /api/v1/trips/<int:trip_id>|DELETE /api/v1/trips/<int:trip_id>
    POST /api/v1/trips/<int:trip_id>/generate|POST /api/v1/trips/<int:trip_id>/cancel
    GET /api/v1/trips/<int:trip_id>/status|POST /api/v1/trips/<int:trip_id>/cover
    GET /api/v1/trips/<int:trip_id>/weather|GET /api/v1/trips/<int:trip_id>/places
    POST /api/v1/trips/<int:trip_id>/stops|PUT /api/v1/stops/<int:stop_id>|DELETE /api/v1/stops/<int:stop_id>
    PUT /api/v1/trips/<int:trip_id>/stops/order|GET /api/v1/trips/<int:trip_id>/overview|GET /api/v1/dashboard
    GET /api/v1/trips/<int:trip_id>/itinerary|POST /api/v1/trips/<int:trip_id>/itinerary
    PUT /api/v1/itinerary/<int:item_id>|DELETE /api/v1/itinerary/<int:item_id>
    PUT /api/v1/trips/<int:trip_id>/days/<int:day_number>|GET /api/v1/trips/<int:trip_id>/expenses
    POST /api/v1/trips/<int:trip_id>/expenses|PUT /api/v1/expenses/<int:expense_id>
    DELETE /api/v1/expenses/<int:expense_id>|GET /api/v1/trips/<int:trip_id>/budget
    GET /api/v1/trips/<int:trip_id>/bookings|POST /api/v1/trips/<int:trip_id>/bookings
    PUT /api/v1/bookings/<int:booking_id>|DELETE /api/v1/bookings/<int:booking_id>
    GET /api/v1/trips/<int:trip_id>/booking-links|GET /api/v1/trips/<int:trip_id>/packing
    POST /api/v1/trips/<int:trip_id>/packing|PUT /api/v1/packing/<int:item_id>|DELETE /api/v1/packing/<int:item_id>
    GET /api/v1/notifications|PUT /api/v1/notifications/<int:notification_id>/read
    POST /api/v1/notifications/read-all|GET /api/v1/notifications/preferences|PUT /api/v1/notifications/preferences
    POST /api/v1/internal/trips/<int:trip_id>/result|PUT /api/v1/internal/trips/<int:trip_id>/weather
    GET /api/v1/internal/upcoming-trips|GET /api/v1/internal/active-trips|GET /api/v1/internal/booking-gaps
    POST /api/v1/internal/notifications|POST /api/v1/internal/sweep-stuck
    """
    for item in re.split(r"[|\n]", expected):
        item = item.strip()
        if not item:
            continue
        method, path = item.split(" ")
        assert (method, path) in routes, item
    assert ("GET", "/health") in routes and ("GET", "/media/<path:filename>") in routes


def test_blueprints_never_touch_db_session():
    for path in _py_files("blueprints"):
        src = open(path, encoding="utf-8").read()
        assert "db.session" not in src, path
        assert "from app.extensions import db" not in src, path
        assert ".commit(" not in src and ".rollback(" not in src, path


def test_models_have_no_serialization_methods():
    for path in _py_files("models"):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name not in ("to_dict", "serialize", "as_dict", "to_json"), (path, node.name)


def test_no_float_money_arithmetic_in_budget_and_money():
    for rel in ("services/budget.py", "utils/money.py", "services/booking_sync.py"):
        src = open(os.path.join(APP, rel), encoding="utf-8").read()
        assert "float(" not in src, rel


def test_no_secrets_committed():
    root = os.path.abspath(os.path.join(BACKEND, ".."))
    assert not os.path.exists(os.path.join(root, ".env")) or ".env" in open(
        os.path.join(root, ".gitignore"), encoding="utf-8").read()
