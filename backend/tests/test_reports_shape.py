"""Regression tests for the P&L route shadowing bug (iteration_3).

Ensures that GET /api/reports/<key> for every known report key returns a
payload that contains BOTH `columns` and `rows` arrays. This prevents a
regression where routes_analytics accidentally shadows the report builder
and returns a structured `{fy, months, totals}` payload that the frontend
cannot render (causing `Cannot read properties of undefined (reading length)`).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://expense-hub-au.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@urbandotted.com.au")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "UrbanDotted!2026")

REPORT_KEYS = [
    "revenue", "expenses", "expense_by_category", "advertising", "refunds",
    "gst", "inventory", "cogs", "assets", "suppliers", "cashflow",
    "missing_receipts", "uncategorised", "accountant_questions", "ledger", "pnl",
]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.mark.parametrize("key", REPORT_KEYS)
def test_report_returns_columns_and_rows(client, key):
    r = client.get(f"{BASE_URL}/api/reports/{key}", params={"fy": "FY2025-26"})
    assert r.status_code == 200, f"{key}: HTTP {r.status_code} {r.text[:200]}"
    data = r.json()
    assert isinstance(data.get("columns"), list), f"{key}: missing columns[]"
    assert isinstance(data.get("rows"), list), f"{key}: missing rows[]"
    assert len(data["columns"]) > 0, f"{key}: empty columns"


def test_pnl_report_shape_and_totals(client):
    r = client.get(f"{BASE_URL}/api/reports/pnl", params={"fy": "FY2025-26"})
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("columns"), list) and len(d["columns"]) == 9
    assert isinstance(d.get("rows"), list) and len(d["rows"]) >= 13  # 12 months + FY TOTAL
    # find FY TOTAL row
    total = None
    for row in d["rows"]:
        cells = row if isinstance(row, list) else list(row.values())
        if any(isinstance(c, str) and "TOTAL" in c.upper() for c in cells):
            total = cells
            break
    assert total is not None, "FY TOTAL row not found"


def test_pnl_empty_fy_returns_clean_shape(client):
    r = client.get(f"{BASE_URL}/api/reports/pnl", params={"fy": "FY2026-27"})
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("columns"), list)
    assert isinstance(d.get("rows"), list)


def test_analytics_pnl_still_returns_structured(client):
    """The analytics endpoint (moved to /api/pnl) still returns the structured shape."""
    r = client.get(f"{BASE_URL}/api/pnl", params={"fy": "FY2025-26"})
    assert r.status_code == 200
    d = r.json()
    assert "fy" in d and "months" in d and "totals" in d and "formula" in d
    assert len(d["months"]) == 12
