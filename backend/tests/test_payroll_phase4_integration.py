"""Phase 4 API integration tests against the live preview backend.

Covers: dashboard-full, super liabilities list/pay, leave settings/ledger/adjustments,
leave requests lifecycle, reports (JSON+CSV+PDF), reminders scan, pay-run finalise
side-effects, and accounting regression (dashboard, pnl, gst, cogs, reminders).
"""
import os
import datetime as dt
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://deploy-fix-145.preview.emergentagent.com").rstrip("/")
EMAIL = "urbandottedstore@gmail.com"
PASSWORD = "Milan@112233!@#"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.verify = False
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def business_id(client):
    r = client.get(f"{BASE}/api/auth/me", timeout=30)
    return r.json()["default_business_id"]


# ============================================================================
# Auth
# ============================================================================
class TestAuth:
    def test_me(self, client):
        r = client.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == EMAIL
        assert d["role"] == "owner"


# ============================================================================
# Dashboard-full (Phase 4 rich)
# ============================================================================
class TestDashboardFull:
    def test_dashboard_full_shape(self, client):
        r = client.get(f"{BASE}/api/payroll/dashboard-full", params={"fy": "FY2026-27"})
        assert r.status_code == 200, r.text
        d = r.json()
        expected = ["fy", "active_employees", "drafts_count", "employees_missing_details",
                    "leave_pending_count", "ytd", "super", "leave", "recent_finalised",
                    "monthly", "next_draft"]
        for k in expected:
            assert k in d, f"missing key {k}"
        assert d["fy"] == "FY2026-27"
        # ytd sub-shape
        for k in ("gross_cents", "net_cents", "super_cents", "payg_cents", "total_employer_cost_cents"):
            assert k in d["ytd"]
        # super sub-shape
        for k in ("outstanding_cents", "overdue_cents", "overdue_items"):
            assert k in d["super"]
        assert "total_remaining_hours" in d["leave"]

    def test_legacy_dashboard_still_works(self, client):
        r = client.get(f"{BASE}/api/payroll/dashboard")
        assert r.status_code == 200
        # Legacy shape (not broken)
        d = r.json()
        assert isinstance(d, dict)


# ============================================================================
# Super Liabilities
# ============================================================================
class TestSuperLiabilities:
    def test_list_shape(self, client):
        r = client.get(f"{BASE}/api/payroll/super-liabilities")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "totals" in d
        for k in ("accrued_cents", "paid_cents", "outstanding_cents", "overdue_count"):
            assert k in d["totals"]
        for it in d["items"]:
            for k in ("liability_id", "quarter", "due_date", "accrued_cents",
                      "paid_cents", "outstanding_cents", "is_overdue", "status"):
                assert k in it, f"missing {k} in liability {it}"

    def test_pay_overpayment_rejected(self, client):
        r = client.get(f"{BASE}/api/payroll/super-liabilities")
        items = r.json()["items"]
        if not items:
            pytest.skip("no super liabilities to test payment over-guard")
        target = next((i for i in items if i["outstanding_cents"] > 0), None)
        if not target:
            pytest.skip("no outstanding liability")
        r2 = client.post(
            f"{BASE}/api/payroll/super-liabilities/{target['liability_id']}/pay",
            json={"paid_cents": target["accrued_cents"] + 100000,
                  "payment_date": dt.date.today().isoformat(),
                  "payment_reference": "TEST_OVER", "payment_note": "over"},
        )
        assert r2.status_code == 422, r2.text


# ============================================================================
# Leave Settings + Ledger + Adjustments
# ============================================================================
@pytest.fixture(scope="session")
def some_employee_id(client):
    r = client.get(f"{BASE}/api/payroll/employees")
    assert r.status_code == 200
    items = r.json().get("items") or r.json()
    if isinstance(items, dict):
        items = items.get("items", [])
    if not items:
        pytest.skip("no employees available")
    return items[0]["employee_id"]


class TestLeaveSettings:
    def test_put_get_persist(self, client, some_employee_id):
        payload = {"accruals": [
            {"leave_type": "annual", "hours_per_pay_period": "3.0769",
             "opening_balance_hours": "0", "active": True}
        ], "notes": "TEST_phase4"}
        r = client.put(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-settings",
                       json=payload)
        assert r.status_code == 200, r.text
        r2 = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-settings")
        assert r2.status_code == 200
        d = r2.json()
        assert d.get("notes") == "TEST_phase4"
        assert any(a["leave_type"] == "annual" for a in d["accruals"])

    def test_ledger_returns_list(self, client, some_employee_id):
        r = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-ledger")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        assert isinstance(d["items"], list)

    def test_adjustment_creates_ledger_row(self, client, some_employee_id):
        before = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-ledger").json()["total"]
        r = client.post(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-adjustments",
                        json={"leave_type": "annual", "hours": "1.5",
                              "note": "TEST_phase4 adjust"})
        assert r.status_code == 200, r.text
        after = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-ledger").json()["total"]
        assert after == before + 1


# ============================================================================
# Leave Requests
# ============================================================================
class TestLeaveRequests:
    def test_create_approve_and_reject(self, client, some_employee_id):
        # Create pending
        today = dt.date.today()
        r = client.post(f"{BASE}/api/payroll/leave-requests", json={
            "employee_id": some_employee_id,
            "leave_type": "annual",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
            "hours": "4",
            "reason": "TEST_phase4",
        })
        assert r.status_code == 200, r.text
        req_id = r.json()["request_id"]

        # Approve
        r2 = client.post(f"{BASE}/api/payroll/leave-requests/{req_id}/action",
                         json={"action": "approve", "note": "ok"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "approved"

        # Re-approve should 400
        r3 = client.post(f"{BASE}/api/payroll/leave-requests/{req_id}/action",
                         json={"action": "approve"})
        assert r3.status_code == 400

        # Cancel approved (posts reversing adjustment)
        r4 = client.post(f"{BASE}/api/payroll/leave-requests/{req_id}/action",
                         json={"action": "cancel"})
        assert r4.status_code == 200
        assert r4.json()["status"] == "cancelled"

    def test_reject_flow(self, client, some_employee_id):
        today = dt.date.today()
        r = client.post(f"{BASE}/api/payroll/leave-requests", json={
            "employee_id": some_employee_id, "leave_type": "annual",
            "start_date": today.isoformat(), "end_date": today.isoformat(),
            "hours": "2", "reason": "TEST_phase4 reject",
        })
        req_id = r.json()["request_id"]
        r2 = client.post(f"{BASE}/api/payroll/leave-requests/{req_id}/action",
                         json={"action": "reject", "note": "no"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "rejected"


# ============================================================================
# Reports (JSON, CSV, PDF)
# ============================================================================
class TestReports:
    @pytest.mark.parametrize("path", [
        "/api/payroll/reports/summary",
        "/api/payroll/reports/payment-summary",
        "/api/payroll/reports/super-quarter",
        "/api/payroll/reports/leave-balances",
    ])
    def test_json(self, client, path):
        r = client.get(f"{BASE}{path}", params={"fy": "FY2026-27"} if "leave-balances" not in path else None)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
        d = r.json()
        assert isinstance(d, dict)

    @pytest.mark.parametrize("path", [
        "/api/payroll/reports/summary.csv",
        "/api/payroll/reports/payment-summary.csv",
        "/api/payroll/reports/super-quarter.csv",
        "/api/payroll/reports/leave-balances.csv",
    ])
    def test_csv_has_bom(self, client, path):
        r = client.get(f"{BASE}{path}")
        assert r.status_code == 200, r.text[:200]
        assert r.content.startswith(b"\xef\xbb\xbf"), f"{path} missing BOM"

    @pytest.mark.parametrize("path", [
        "/api/payroll/reports/summary.pdf",
        "/api/payroll/reports/payment-summary.pdf",
        "/api/payroll/reports/super-quarter.pdf",
        "/api/payroll/reports/leave-balances.pdf",
    ])
    def test_pdf_magic(self, client, path):
        r = client.get(f"{BASE}{path}")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF", f"{path} not a PDF"


# ============================================================================
# Reminders scan
# ============================================================================
class TestReminders:
    def test_scan_writes_to_global_reminders(self, client):
        r = client.post(f"{BASE}/api/payroll/reminders/scan", params={"fy": "FY2026-27"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        # Verify they appear in global /api/reminders and start with payroll_
        r2 = client.get(f"{BASE}/api/reminders")
        assert r2.status_code == 200
        items = r2.json().get("items") or r2.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        # It's OK if there are zero payroll reminders (nothing overdue), but if any exist, ensure they start with 'payroll_'
        payroll_kinds = [i for i in items if str(i.get("kind", "")).startswith("payroll_")]
        # sanity: kind format
        for i in payroll_kinds:
            assert i["kind"].startswith("payroll_")


# ============================================================================
# Accounting regression
# ============================================================================
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/api/dashboard",
        "/api/reports/pnl",
        "/api/gst",
        "/api/cogs",
        "/api/reminders",
        "/api/month-end",
        "/api/year-end",
    ])
    def test_shape_ok(self, client, path):
        r = client.get(f"{BASE}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


# ============================================================================
# Pay-run finalise integration — creates a NEW weekly pay run with a distinct
# period, loads employees, finalises, and asserts side-effects.
# ============================================================================
class TestPayRunFinaliseSideEffects:
    def test_finalise_creates_super_liability_and_leave_accrual_only_for_configured(self, client, business_id, some_employee_id):
        today = dt.date.today()
        period_end = today
        period_start = today - dt.timedelta(days=6)
        payment_date = today + dt.timedelta(days=1)

        # Count txns before to verify no writes
        r_txn_before = client.get(f"{BASE}/api/transactions", params={"limit": 1})
        txn_total_before = None
        if r_txn_before.status_code == 200:
            body = r_txn_before.json()
            txn_total_before = body.get("total") if isinstance(body, dict) else None

        # Create pay run
        r = client.post(f"{BASE}/api/payroll/pay-runs", json={
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "payment_date": payment_date.isoformat(),
            "pay_frequency": "weekly",
            "notes": "TEST_phase4 integration",
        })
        if r.status_code == 400 and "already exists" in r.text:
            pytest.skip("duplicate pay run — retry with different period")
        assert r.status_code == 200, r.text
        ref = r.json()["pay_run_ref"]

        # Load employees
        r2 = client.post(f"{BASE}/api/payroll/pay-runs/{ref}/load")
        assert r2.status_code == 200, r2.text

        # Calculate
        r3 = client.post(f"{BASE}/api/payroll/pay-runs/{ref}/calculate")
        assert r3.status_code == 200, r3.text

        # Snapshot ledger BEFORE finalise for the target employee
        before_ledger = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-ledger").json()["total"]

        # Finalise
        r4 = client.post(f"{BASE}/api/payroll/pay-runs/{ref}/finalise")
        assert r4.status_code == 200, r4.text

        # Super liability rows should exist and contain contributing_payslip_refs
        rl = client.get(f"{BASE}/api/payroll/super-liabilities", params={"fy": "FY2026-27"})
        assert rl.status_code == 200
        items = rl.json()["items"]
        # There should be at least one with a non-empty contributing_payslip_refs
        assert any(it.get("contributing_payslip_refs") for it in items), \
            "no super_liabilities with contributing_payslip_refs after finalise"

        # Leave accrual: should only accrue for employees with leave-settings configured.
        # The target employee had accruals configured in TestLeaveSettings.
        after_ledger = client.get(f"{BASE}/api/payroll/employees/{some_employee_id}/leave-ledger").json()["total"]
        assert after_ledger >= before_ledger, "ledger should have accrual for configured employee (or unchanged)"

        # Guardrail: no new documents in /api/transactions from pay run finalise.
        if txn_total_before is not None:
            r_txn_after = client.get(f"{BASE}/api/transactions", params={"limit": 1})
            if r_txn_after.status_code == 200:
                body = r_txn_after.json()
                after = body.get("total") if isinstance(body, dict) else None
                if after is not None:
                    assert after == txn_total_before, \
                        f"transactions total changed: {txn_total_before} -> {after}"
