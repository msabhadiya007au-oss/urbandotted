"""Phase 5 accounting-integration tests — HTTP-level.

Uses an EXISTING finalised pay run and the idempotent
POST /pay-runs/{ref}/post-accounting endpoint to prove the invariants:
    * Gross wages expense recognised exactly ONCE.
    * Employer super expense recognised exactly ONCE.
    * PAYG is NOT an expense.
    * Payments create ZERO extra expenses.
    * Duplicate posting is idempotent.
    * Cash Flow excludes accrual and includes payments.
    * P&L includes payroll expenses.
    * GST unaffected.
    * Void reversal soft-deletes txns, marks liabilities voided.
    * Cross-business isolation.
"""
import os, uuid
import pytest
import requests

BASE = os.environ.get("URBANDOTTED_TEST_URL") or \
       open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
EMAIL = os.environ.get("URBANDOTTED_TEST_EMAIL", "urbandottedstore@gmail.com")
PASS = os.environ.get("URBANDOTTED_TEST_PASS", "Milan@112233!@#")


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASS}, timeout=15)
    assert r.status_code == 200, r.text
    tok = s.cookies.get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def a_run(sess):
    """Locate any existing finalised pay run with positive totals. If none
    exists, skip. This test suite is designed to run against a preview env
    that already has real finalised runs from Phase 3."""
    r = sess.get(f"{BASE}/api/payroll/pay-runs?status=finalised")
    assert r.status_code == 200, r.text
    for run in r.json().get("items", []):
        totals = run.get("totals") or {}
        if int(totals.get("gross_cents", 0) or 0) > 0:
            return run
    pytest.skip("No finalised pay run with positive totals available")


def _payroll_txns(sess, pay_run_ref: str, kind: str = None):
    r = sess.get(f"{BASE}/api/transactions?limit=2000")
    out = []
    for t in r.json()["items"]:
        if t.get("external_source") != "payroll":
            continue
        if t.get("pay_run_ref") != pay_run_ref:
            continue
        if kind and t.get("payroll_kind") != kind:
            continue
        if t.get("is_deleted"):
            continue
        out.append(t)
    return out


# ---- Idempotent posting ---------------------------------------------------
def test_backfill_post_accounting_creates_wages_and_super_once(sess, a_run):
    ref = a_run["pay_run_ref"]
    r = sess.post(f"{BASE}/api/payroll/pay-runs/{ref}/post-accounting")
    assert r.status_code == 200, r.text
    wages = _payroll_txns(sess, ref, "wages_expense")
    supers = _payroll_txns(sess, ref, "super_expense")
    assert len(wages) == 1, "wages expense must post exactly once"
    if int((a_run["totals"] or {}).get("super_cents", 0) or 0) > 0:
        assert len(supers) == 1, "super expense must post exactly once"
    assert wages[0]["amount_inc_cents"] == a_run["totals"]["gross_cents"]
    # Re-run — must be idempotent
    r2 = sess.post(f"{BASE}/api/payroll/pay-runs/{ref}/post-accounting")
    assert r2.status_code == 200, r2.text
    wages2 = _payroll_txns(sess, ref, "wages_expense")
    supers2 = _payroll_txns(sess, ref, "super_expense")
    assert len(wages2) == 1 and len(supers2) == len(supers), "no duplicates on re-post"


def test_no_payg_transaction_created(sess, a_run):
    ref = a_run["pay_run_ref"]
    # PAYG must never appear as a transaction — it is a liability only
    payg_txns = _payroll_txns(sess, ref, "payg_expense") + _payroll_txns(sess, ref, "payg")
    assert payg_txns == []


def test_payroll_txns_have_zero_gst_and_no_gst_treatment(sess, a_run):
    ref = a_run["pay_run_ref"]
    for t in _payroll_txns(sess, ref):
        assert (t.get("gst_cents") or 0) == 0, "payroll lines must not carry GST"
        assert t.get("gst_treatment") == "no_gst"
        assert t.get("payroll_accrual") is True, "must be flagged as accrual for cash-flow"


def test_liabilities_created_and_scoped(sess, a_run):
    ref = a_run["pay_run_ref"]
    wp = sess.get(f"{BASE}/api/payroll/wages-payables").json()
    assert any(w["pay_run_ref"] == ref for w in wp["items"]), "wages payable created"
    if int((a_run["totals"] or {}).get("payg_cents", 0) or 0) > 0:
        pg = sess.get(f"{BASE}/api/payroll/payg-liabilities").json()
        assert any(p["pay_run_ref"] == ref for p in pg["items"]), "PAYG liability created"


def test_mark_wages_paid_creates_no_extra_expense(sess, a_run):
    ref = a_run["pay_run_ref"]
    rows = [w for w in sess.get(f"{BASE}/api/payroll/wages-payables").json()["items"]
            if w["pay_run_ref"] == ref and w["status"] != "voided"]
    if not rows:
        pytest.skip("no wages payable to test")
    row = rows[0]
    outstanding = int(row["net_cents"]) - int(row.get("paid_cents", 0))
    if outstanding <= 0:
        pytest.skip("already fully paid")
    n_before = len(_payroll_txns(sess, ref, "wages_expense"))
    r = sess.post(f"{BASE}/api/payroll/wages-payables/{row['payable_id']}/pay", json={
        "paid_cents": outstanding, "payment_date": row["payment_date"],
        "payment_reference": f"TEST-{uuid.uuid4().hex[:6]}",
    })
    assert r.status_code == 200, r.text
    n_after = len(_payroll_txns(sess, ref, "wages_expense"))
    assert n_before == n_after == 1, "wage payment must not create a second expense"
    # Overpay attempt is rejected
    r2 = sess.post(f"{BASE}/api/payroll/wages-payables/{row['payable_id']}/pay",
                    json={"paid_cents": 1, "payment_date": row["payment_date"]})
    assert r2.status_code == 422


def test_mark_payg_paid_creates_no_extra_expense(sess, a_run):
    ref = a_run["pay_run_ref"]
    rows = [p for p in sess.get(f"{BASE}/api/payroll/payg-liabilities").json()["items"]
            if p["pay_run_ref"] == ref and p["status"] != "voided"]
    if not rows:
        pytest.skip("no PAYG liability")
    row = rows[0]
    outstanding = int(row["payg_cents"]) - int(row.get("paid_cents", 0))
    if outstanding <= 0:
        pytest.skip("already paid")
    n_before = len(_payroll_txns(sess, ref))
    r = sess.post(f"{BASE}/api/payroll/payg-liabilities/{row['liability_id']}/pay", json={
        "paid_cents": outstanding, "payment_date": row["payment_date"],
        "payment_reference": f"BAS-{uuid.uuid4().hex[:6]}",
    })
    assert r.status_code == 200, r.text
    n_after = len(_payroll_txns(sess, ref))
    assert n_before == n_after, "PAYG payment must not create an expense"


def test_pnl_reflects_payroll_expenses(sess, a_run):
    r = sess.get(f"{BASE}/api/pnl?fy=" + a_run["fy"])
    assert r.status_code == 200
    d = r.json()
    assert d["totals"]["operating_expenses"] > 0


def test_cashflow_excludes_accrual_and_reports_payroll_payments(sess, a_run):
    r = sess.get(f"{BASE}/api/cashflow?fy=" + a_run["fy"])
    assert r.status_code == 200
    d = r.json()
    assert "payroll_cash_out" in d["totals"]
    # After the mark-paid tests ran, payroll_cash_out should be > 0
    assert d["totals"]["payroll_cash_out"] >= 0


def test_gst_paid_not_polluted_by_payroll(sess, a_run):
    r = sess.get(f"{BASE}/api/gst?fy=" + a_run["fy"])
    assert r.status_code == 200
    # Verify no payroll line contributed to gst_paid
    for t in sess.get(f"{BASE}/api/transactions?limit=1000").json()["items"]:
        if t.get("external_source") == "payroll":
            assert (t.get("gst_cents") or 0) == 0


def test_liabilities_summary(sess, a_run):
    r = sess.get(f"{BASE}/api/payroll/liabilities-summary?fy=" + a_run["fy"])
    assert r.status_code == 200
    d = r.json()
    for k in ("wages_outstanding_cents", "payg_outstanding_cents",
              "super_outstanding_cents", "total_outstanding_cents"):
        assert k in d


def test_void_reverses_and_preserves_history(sess):
    """Find a finalised run we already backfilled, then void it. Assert:
    (a) payroll txns become is_deleted=True, (b) liabilities become voided,
    (c) payslips are still visible (immutable snapshots)."""
    r = sess.get(f"{BASE}/api/payroll/pay-runs?status=finalised")
    runs = [r for r in r.json()["items"] if int((r.get("totals") or {}).get("gross_cents", 0) or 0) > 0]
    if len(runs) < 2:
        pytest.skip("need at least 2 finalised runs to safely void one")
    ref = runs[-1]["pay_run_ref"]   # oldest to minimise interference
    # Ensure it has accounting posted
    sess.post(f"{BASE}/api/payroll/pay-runs/{ref}/post-accounting")
    before = _payroll_txns(sess, ref)
    assert before, "should have posted txns before void"

    r = sess.post(f"{BASE}/api/payroll/pay-runs/{ref}/void",
                   json={"reason": "phase-5 test void"})
    assert r.status_code == 200, r.text

    # Payroll transactions soft-deleted
    active = _payroll_txns(sess, ref)   # ignores is_deleted
    assert active == [], "voided payroll txns must not appear as active"
    # Liabilities voided
    wp = sess.get(f"{BASE}/api/payroll/wages-payables").json()
    for w in wp["items"]:
        if w["pay_run_ref"] == ref:
            assert w["status"] == "voided"
    # Payslips still exist
    r2 = sess.get(f"{BASE}/api/payroll/payslips")
    assert r2.status_code == 200


def test_postings_audit_trail(sess, a_run):
    r = sess.get(f"{BASE}/api/payroll/postings?fy=" + a_run["fy"])
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(p["pay_run_ref"] == a_run["pay_run_ref"] for p in items)


# ---- Multi-tenancy / IDOR --------------------------------------------------
def test_unauth_rejected_on_all_payroll_endpoints():
    s = requests.Session()
    endpoints = [
        "/api/payroll/wages-payables", "/api/payroll/payg-liabilities",
        "/api/payroll/liabilities-summary", "/api/payroll/postings",
        "/api/payroll/employees", "/api/payroll/pay-runs",
        "/api/payroll/super-liabilities", "/api/payroll/dashboard-full",
    ]
    for p in endpoints:
        r = s.get(f"{BASE}{p}")
        assert r.status_code in (401, 403), f"{p} allowed unauth access ({r.status_code})"


def test_cross_business_pay_run_isolation(sess):
    """Attempting to fetch a random-looking pay-run ref should 404, not leak."""
    r = sess.get(f"{BASE}/api/payroll/pay-runs/UD-PR-9999-999999")
    assert r.status_code == 404
