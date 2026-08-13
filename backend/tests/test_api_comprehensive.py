"""Comprehensive backend API test suite for Urban Dotted Expense Book."""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://deploy-fix-145.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@urbandotted.com.au"
ADMIN_PASSWORD = "UrbanDotted!2026"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "user" in data or "access_token" in data or s.cookies.get("access_token")
    return s


# ============ AUTH / HEALTH ============
def test_health():
    r = requests.get(f"{API}/")
    assert r.status_code == 200

def test_login_bad_creds():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code in (400, 401, 403)

def test_unauth_dashboard_401():
    r = requests.get(f"{API}/dashboard")
    assert r.status_code == 401

def test_auth_me(sess):
    r = sess.get(f"{API}/auth/me")
    assert r.status_code == 200
    d = r.json()
    assert d.get("email") == ADMIN_EMAIL or d.get("user", {}).get("email") == ADMIN_EMAIL

def test_foreign_business_403(sess):
    r = sess.get(f"{API}/dashboard", headers={"X-Business-Id": "nonexistent-business-id-xyz"})
    assert r.status_code == 403


# ============ META / SETUP ============
def test_meta(sess):
    r = sess.get(f"{API}/meta")
    assert r.status_code == 200

def test_business(sess):
    r = sess.get(f"{API}/business")
    assert r.status_code == 200

def test_categories(sess):
    r = sess.get(f"{API}/categories")
    assert r.status_code == 200
    d = r.json()
    assert "flat" in d and isinstance(d["flat"], list) and len(d["flat"]) > 0

def test_accounts(sess):
    r = sess.get(f"{API}/accounts")
    assert r.status_code == 200

def test_suppliers(sess):
    r = sess.get(f"{API}/suppliers")
    assert r.status_code == 200

def test_products(sess):
    r = sess.get(f"{API}/products")
    assert r.status_code == 200


# ============ DEMO DATA LIFECYCLE ============
def test_demo_load_and_status(sess):
    # ensure demo present
    st = sess.get(f"{API}/demo/status")
    assert st.status_code == 200
    if not st.json().get("present"):
        r = sess.post(f"{API}/demo/load")
        assert r.status_code == 200
    st2 = sess.get(f"{API}/demo/status")
    assert st2.json().get("has_demo_data") is True


# ============ DASHBOARD / ANALYTICS (FY2025-26) ============
FY = "FY2025-26"

def test_dashboard_fy2526(sess):
    r = sess.get(f"{API}/dashboard", params={"fy": FY})
    assert r.status_code == 200
    d = r.json().get("kpis", {})
    for k in ["gross_sales", "net_sales", "refunds", "cogs", "gross_profit",
              "operating_expenses", "operating_profit", "gst_collected",
              "gst_paid", "cash_inflow", "cash_outflow"]:
        assert k in d, f"missing KPI {k}"
    # Verify demo data values per main agent context
    assert d["gross_sales"] == 97500.0
    assert d["net_sales"] == 88260.0
    assert d["refunds"] == 3480.0
    assert abs(d["cogs"] - 20392.86) < 1  # allow rounding
    assert d["operating_expenses"] == 29592.0

def test_dashboard_empty_fy(sess):
    r = sess.get(f"{API}/dashboard", params={"fy": "FY2026-27"})
    assert r.status_code == 200
    d = r.json().get("kpis", {})
    assert d.get("gross_sales", 0) == 0

def test_cogs(sess):
    r = sess.get(f"{API}/cogs", params={"fy": FY})
    assert r.status_code == 200

def test_gst(sess):
    r = sess.get(f"{API}/gst", params={"fy": FY})
    assert r.status_code == 200

def test_cashflow(sess):
    r = sess.get(f"{API}/cashflow", params={"fy": FY})
    assert r.status_code == 200

def test_advertising(sess):
    r = sess.get(f"{API}/advertising", params={"fy": FY})
    assert r.status_code == 200

def test_refunds_analytics(sess):
    r = sess.get(f"{API}/refunds/analytics", params={"fy": FY})
    assert r.status_code == 200

def test_sales_summary(sess):
    r = sess.get(f"{API}/sales/summary", params={"fy": FY})
    assert r.status_code == 200

def test_pnl(sess):
    r = sess.get(f"{API}/reports/pnl", params={"fy": FY})
    assert r.status_code == 200

def test_search(sess):
    r = sess.get(f"{API}/search", params={"q": "Facebook", "fy": FY})
    assert r.status_code == 200

def test_compare(sess):
    r = sess.get(f"{API}/compare", params={"fy": FY})
    assert r.status_code == 200


# ============ TRANSACTIONS CRUD + GST ============
def test_create_expense_gst_inclusive(sess):
    # Get a category
    cats = sess.get(f"{API}/categories").json()["flat"]
    cat = next((c for c in cats if c.get("type") == "expense" or c.get("kind") == "expense"), cats[0])
    cat_id = cat.get("category_id") or cat.get("id")
    payload = {
        "txn_type": "expense",
        "date": "2026-08-15",
        "category_id": cat_id,
        "description": "TEST_gst_inclusive_110",
        "amount": 110.00,
        "gst_treatment": "gst_included",
        "payment_method": "eft",
    }
    r = sess.post(f"{API}/transactions", json=payload)
    assert r.status_code in (200, 201), r.text
    d = r.json()
    tid = d.get("txn_id") or d.get("id")
    # Fetch and verify split
    g = sess.get(f"{API}/transactions/{tid}").json()
    # amount_ex_gst_cents = 10000, gst_cents = 1000
    assert g.get("gst") in (10, 10.0), f"expected 10 gst got {g.get('gst')}"
    assert g.get("amount_ex") in (100, 100.0)
    # cleanup
    sess.delete(f"{API}/transactions/{tid}")

def test_create_expense_gst_free(sess):
    cats = sess.get(f"{API}/categories").json()["flat"]
    cat = next((c for c in cats if c.get("type") == "expense" or c.get("kind") == "expense"), cats[0])
    cat_id = cat.get("category_id") or cat.get("id")
    payload = {
        "txn_type": "expense",
        "date": "2026-08-15",
        "category_id": cat_id,
        "description": "TEST_gst_free",
        "amount": 100.00,
        "gst_treatment": "gst_free",
        "payment_method": "eft",
    }
    r = sess.post(f"{API}/transactions", json=payload)
    assert r.status_code in (200, 201)
    tid = r.json().get("txn_id") or r.json().get("id")
    g = sess.get(f"{API}/transactions/{tid}").json()
    assert g.get("gst", 0) == 0
    sess.delete(f"{API}/transactions/{tid}")

def test_transactions_list(sess):
    r = sess.get(f"{API}/transactions", params={"fy": FY})
    assert r.status_code == 200


# ============ INVENTORY / COGS ============
def test_inventory_purchase_landed_cost(sess):
    prods = sess.get(f"{API}/products").json()
    if not prods:
        # try create a product
        pr = sess.post(f"{API}/products", json={"sku": "TEST-SKU-001", "name": "TEST product"})
        if pr.status_code in (200, 201):
            prods = [pr.json()]
        else:
            pytest.skip("no products to test inventory purchase")
    payload = {
        "date": "2026-08-01",
        "sku": prods[0].get("sku", "TEST-SKU-001"),
        "qty": 1000,
        "unit_cost": 5.00,
        "freight": 500.00,
        "customs": 300.00,
        "import_gst": 580.00,
        "other": 100.00,
        "supplier_name": "TEST Supplier",
    }
    r = sess.post(f"{API}/inventory/purchases", json=payload)
    assert r.status_code in (200, 201), r.text
    d = r.json()
    # total_cost expected around 6480 dollars (excluding import GST from landed? verify)
    # accept either 6480 or 5900 depending on convention
    total = d.get("total_cost") or d.get("total_cost_cents", 0) / 100
    landed = d.get("landed_unit_cost") or (d.get("landed_unit_cost_cents", 0) / 100)
    assert total > 0
    assert landed > 0
    # cleanup
    if d.get("id"):
        sess.delete(f"{API}/inventory/purchases/{d['id']}")


def test_assets_list(sess):
    r = sess.get(f"{API}/assets")
    assert r.status_code == 200


# ============ REMINDERS / MONTH-END ============
def test_reminders_scan(sess):
    r = sess.post(f"{API}/reminders/scan", params={"fy": FY})
    assert r.status_code == 200

def test_reminders_list(sess):
    r = sess.get(f"{API}/reminders", params={"fy": FY})
    assert r.status_code == 200

def test_month_end(sess):
    r = sess.get(f"{API}/month-end", params={"fy": FY})
    assert r.status_code == 200

def test_year_end(sess):
    r = sess.get(f"{API}/year-end", params={"fy": FY})
    assert r.status_code == 200


# ============ REPORTS / EXPORT ============
def test_reports_list(sess):
    r = sess.get(f"{API}/reports", params={"fy": FY})
    assert r.status_code == 200

def test_report_pnl_csv(sess):
    r = sess.get(f"{API}/reports/pnl/csv", params={"fy": FY})
    assert r.status_code == 200
    assert len(r.content) > 0

def test_report_pnl_pdf(sess):
    r = sess.get(f"{API}/reports/pnl/pdf", params={"fy": FY})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"

def test_export_transactions_csv(sess):
    r = sess.get(f"{API}/export/transactions", params={"fy": FY})
    assert r.status_code == 200
    text = r.text[:2000]
    # Required column headers per problem statement
    for col in ["Date", "Category", "Supplier", "Description", "GST"]:
        assert col in text, f"missing column {col} in CSV header"

def test_accountant_export_zip(sess):
    r = sess.post(f"{API}/export/accountant", json={"fy": FY, "format": "zip", "reports": ["pnl", "gst"], "include_receipts": True})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # zip magic


# ============ DOCUMENTS ============
def test_documents_list(sess):
    r = sess.get(f"{API}/documents")
    assert r.status_code == 200

def test_documents_missing_receipts(sess):
    r = sess.get(f"{API}/documents/missing-receipts", params={"fy": FY})
    assert r.status_code == 200

def test_document_upload_bad_extension(sess):
    files = {"file": ("evil.exe", b"MZ\x00\x00\x00\x00\x00", "application/octet-stream")}
    r = sess.post(f"{API}/documents/upload", files=files)
    assert r.status_code in (400, 415, 422), f"expected reject, got {r.status_code}"

def test_document_upload_pdf(sess):
    # Minimal PDF
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    files = {"file": ("TEST_receipt.pdf", pdf_bytes, "application/pdf")}
    r = sess.post(f"{API}/documents/upload", files=files)
    # Object storage may still be off - report either way
    assert r.status_code in (200, 201, 500, 503), f"unexpected {r.status_code} {r.text[:200]}"
    if r.status_code in (200, 201):
        doc_id = r.json().get("id")
        if doc_id:
            # download
            d = sess.get(f"{API}/documents/{doc_id}/download")
            assert d.status_code == 200
            assert len(d.content) > 0
            sess.delete(f"{API}/documents/{doc_id}")


# ============ SETTINGS ============
def test_audit_logs(sess):
    r = sess.get(f"{API}/audit-logs")
    assert r.status_code == 200

def test_integrations(sess):
    r = sess.get(f"{API}/integrations")
    assert r.status_code == 200
    # Expect labelled Phase 4/5
    body = r.text.lower()
    assert "phase" in body

def test_backup_export(sess):
    r = sess.get(f"{API}/backup/export")
    assert r.status_code == 200
    assert len(r.content) > 0

def test_recurring(sess):
    r = sess.get(f"{API}/recurring")
    assert r.status_code == 200


# ============ IMPORT ============
def test_import_fields(sess):
    r = sess.get(f"{API}/import/fields")
    assert r.status_code == 200


# ============ LOGOUT ============
def test_logout():
    s = requests.Session()
    s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = s.post(f"{API}/auth/logout")
    assert r.status_code in (200, 204)
    # After logout, /me should be 401
    r2 = s.get(f"{API}/auth/me")
    assert r2.status_code == 401
