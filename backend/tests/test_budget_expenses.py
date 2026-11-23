"""D3 budget math (pure + API) and expense CRUD."""
from decimal import Decimal

from app.services.budget import compute_budget
from tests.factories import create_trip, register

D = Decimal


def _cat(summary, name):
    return next(c for c in summary.categories if c.category == name)


def test_empty_expenses():
    s = compute_budget(D("1000.00"), [])
    assert s.forecast_total == D("0.00") and s.remaining == D("1000.00")
    assert not s.exceeded and s.exceeded_by == D("0.00")
    assert s.spent_percent == D("0.0") and s.remaining_percent == D("100.0")
    assert all(c.basis == "estimated" for c in s.categories)
    assert len(s.categories) == 6


def test_confirmed_replaces_estimate_per_category():
    rows = [("food", False, D("500.00")), ("food", True, D("120.50")),
            ("transport", False, D("300.00")), ("accommodation", True, D("200.00"))]
    s = compute_budget(D("1000.00"), rows)
    food = _cat(s, "food")
    assert (food.effective, food.basis) == (D("120.50"), "confirmed")
    assert (_cat(s, "transport").effective, _cat(s, "transport").basis) == (D("300.00"), "estimated")
    assert s.confirmed_total == D("320.50")
    assert s.estimated_total == D("800.00")
    assert s.forecast_total == D("620.50")
    assert s.remaining == D("379.50")
    assert s.spent_percent == D("32.1")          # 32.05 -> half-up
    assert s.remaining_percent == D("67.9")
    assert s.forecast_percent == D("62.1")       # 62.05 -> half-up


def test_exceeded_budget():
    s = compute_budget(D("100.00"), [("misc", True, D("150.25"))])
    assert s.exceeded and s.remaining == D("-50.25") and s.exceeded_by == D("50.25")
    assert s.spent_percent == D("150.3") and s.remaining_percent == D("0.0")


def test_unknown_category_counts_as_misc():
    s = compute_budget(D("100.00"), [("weird", False, D("10.00"))])
    assert _cat(s, "misc").estimated == D("10.00")


def test_decimal_precision_no_float_drift():
    rows = [("food", True, D("0.10"))] * 3
    s = compute_budget(D("0.30"), rows)
    assert s.confirmed_total == D("0.30") and s.remaining == D("0.00") and not s.exceeded


def test_zero_budget_protection():
    s = compute_budget(D("0"), [("food", True, D("5.00"))])
    assert s.spent_percent == D("0.0") and s.forecast_percent == D("0.0")


def test_budget_endpoint(client):
    register(client)
    tid = create_trip(client, budget="1000.00")["id"]
    client.post(f"/api/v1/trips/{tid}/expenses", json={"category": "food", "amount": "500"})
    client.post(f"/api/v1/trips/{tid}/expenses", json={"category": "food", "amount": "120.50", "is_confirmed": True})
    b = client.get(f"/api/v1/trips/{tid}/budget").get_json()["budget"]
    assert b["forecast_total"] == "120.50" and b["remaining"] == "879.50"
    assert b["confirmed_total"] == "120.50" and b["estimated_total"] == "500.00"
    assert b["spent_percent"] == 12.1 and b["currency"] == "INR"


def test_expense_crud_and_validation(client):
    register(client)
    tid = create_trip(client)["id"]
    r = client.post(f"/api/v1/trips/{tid}/expenses", json={"category": "Food", "amount": 99.99, "description": "Lunch"})
    assert r.status_code == 201
    e = r.get_json()["expense"]
    assert e["category"] == "food" and e["amount"] == "99.99" and e["source"] == "user"
    for bad in ({"category": "food", "amount": 0}, {"category": "food", "amount": "-1"},
                {"category": "nope", "amount": 1}, {"amount": 1}, {"category": "food", "amount": "1.001"}):
        assert client.post(f"/api/v1/trips/{tid}/expenses", json=bad).status_code == 400, bad
    u = client.put(f"/api/v1/expenses/{e['id']}", json={"amount": "150", "is_confirmed": True})
    assert u.get_json()["expense"]["amount"] == "150.00"
    assert client.get(f"/api/v1/trips/{tid}/expenses?category=food").get_json()["items"][0]["id"] == e["id"]
    assert client.get(f"/api/v1/trips/{tid}/expenses?category=bad").status_code == 400
    assert client.delete(f"/api/v1/expenses/{e['id']}").status_code == 200
    assert client.get(f"/api/v1/trips/{tid}/expenses").get_json()["items"] == []


def test_expense_ownership(client, make_client):
    register(client)
    tid = create_trip(client)["id"]
    eid = client.post(f"/api/v1/trips/{tid}/expenses", json={"category": "food", "amount": "5"}).get_json()["expense"]["id"]
    other = make_client()
    register(other)
    assert other.put(f"/api/v1/expenses/{eid}", json={"amount": "1"}).status_code == 404
    assert other.delete(f"/api/v1/expenses/{eid}").status_code == 404
    assert other.post(f"/api/v1/trips/{tid}/expenses", json={"category": "food", "amount": "5"}).status_code == 404
