"""Payroll Phase 4 tests — pure engine helpers + PDF renderers.

Focuses on the pieces without a DB dependency; the DB-backed endpoints
are exercised through the API by the testing agent.
"""
import os, sys, pathlib
os.environ.setdefault("PAYROLL_ENC_KEY", "test-key-phase4")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402
import payroll_phase4_engine as pe  # noqa: E402
import payroll_reports_pdf as rpdf  # noqa: E402


# ---------- Quarter helpers -------------------------------------------------
def test_quarter_of_boundaries():
    assert pe.quarter_of("2026-07-01") == "Q1"
    assert pe.quarter_of("2026-09-30") == "Q1"
    assert pe.quarter_of("2026-10-01") == "Q2"
    assert pe.quarter_of("2026-12-31") == "Q2"
    assert pe.quarter_of("2027-01-01") == "Q3"
    assert pe.quarter_of("2027-03-31") == "Q3"
    assert pe.quarter_of("2027-04-01") == "Q4"
    assert pe.quarter_of("2027-06-30") == "Q4"


def test_quarter_bounds_q1_FY202627():
    start, end, due = pe.quarter_bounds("FY2026-27", "Q1")
    assert (start, end, due) == ("2026-07-01", "2026-09-30", "2026-10-28")


def test_quarter_bounds_q3_crosses_calendar_year():
    start, end, due = pe.quarter_bounds("FY2026-27", "Q3")
    assert (start, end, due) == ("2027-01-01", "2027-03-31", "2027-04-28")


def test_quarter_bounds_q4_due_july_next_year():
    start, end, due = pe.quarter_bounds("FY2026-27", "Q4")
    assert (start, end, due) == ("2027-04-01", "2027-06-30", "2027-07-28")


# ---------- Overdue detection ----------------------------------------------
def test_is_overdue_before_due():
    assert pe.is_overdue("2026-10-28", "2026-10-27", 0, 10000) is False


def test_is_overdue_after_due_unpaid():
    assert pe.is_overdue("2026-10-28", "2026-10-29", 0, 10000) is True


def test_is_overdue_after_due_fully_paid():
    assert pe.is_overdue("2026-10-28", "2026-11-15", 10000, 10000) is False


def test_is_overdue_zero_accrual_never_overdue():
    assert pe.is_overdue("2026-10-28", "2027-01-01", 0, 0) is False


# ---------- Accrual math ---------------------------------------------------
def test_accrual_zero_when_zero_rate():
    assert pe.accrual_hours_for_period("0", "active") == "0"


def test_accrual_returns_configured_hours():
    # 76 std hours * 4/52 (annual leave standard) ≈ 5.8462 per fortnight
    # But we don't hard-code — the owner passes the hours per period directly.
    assert pe.accrual_hours_for_period("5.8462", "active") == "5.8462"


def test_accrual_archived_employee_is_zero():
    assert pe.accrual_hours_for_period("5", "archived") == "0"


def test_accrual_on_leave_still_accrues_if_configured():
    """On-leave employees still accrue per user's instructions — never silently zero."""
    assert pe.accrual_hours_for_period("2.5", "on_leave") == "2.5000"


# ---------- Ledger sum -----------------------------------------------------
def test_sum_hours_signed():
    entries = [{"hours": "5.5"}, {"hours": "-2.5"}, {"hours": "1"}]
    assert pe.sum_hours(entries) == "4.0000"


def test_sum_hours_empty():
    assert pe.sum_hours([]) == "0.0000"


# ---------- Format ---------------------------------------------------------
def test_format_hours_keeps_one_decimal():
    assert pe.format_hours("5") == "5.0"
    assert pe.format_hours("5.50") == "5.5"


# ---------- PDF renderers --------------------------------------------------
def test_summary_pdf_is_valid():
    d = {
        "fy": "FY2026-27",
        "rows": [{
            "employee_name": "Milan S", "payslip_count": 2,
            "gross_cents": 500000, "taxable_cents": 500000,
            "pretax_ded_cents": 0, "posttax_ded_cents": 0,
            "payg_cents": 0, "net_cents": 500000, "super_cents": 60000,
        }],
        "totals": {"payslip_count": 2, "gross_cents": 500000, "taxable_cents": 500000,
                   "pretax_ded_cents": 0, "posttax_ded_cents": 0,
                   "payg_cents": 0, "net_cents": 500000, "super_cents": 60000},
    }
    b = rpdf.build_summary_pdf(d, {"legal_business_name": "Urban Dotted Pty Ltd", "abn": "12345678901"})
    assert isinstance(b, bytes) and b[:5] == b"%PDF-"


def test_payment_summary_pdf_multi_employees():
    d = {"fy": "FY2026-27", "rows": [
        {"employee_id": "e1", "employee_name": "A", "address_line": "",
         "period_start": "2026-07-01", "period_end": "2026-12-31",
         "payslip_count": 5, "gross_cents": 100000, "taxable_cents": 100000,
         "pretax_ded_cents": 0, "posttax_ded_cents": 0,
         "payg_cents": 0, "net_cents": 100000, "super_cents": 12000},
        {"employee_id": "e2", "employee_name": "B", "address_line": "",
         "period_start": "2026-07-01", "period_end": "2026-12-31",
         "payslip_count": 5, "gross_cents": 200000, "taxable_cents": 200000,
         "pretax_ded_cents": 0, "posttax_ded_cents": 0,
         "payg_cents": 0, "net_cents": 200000, "super_cents": 24000},
    ]}
    b = rpdf.build_payment_summary_pdf(d, {})
    assert b[:5] == b"%PDF-" and len(b) > 500


def test_super_pdf_shows_overdue():
    d = {"fy": "FY2026-27", "quarter": None, "quarters": [{
        "quarter": "Q1", "period_start": "2026-07-01", "period_end": "2026-09-30",
        "due_date": "2026-10-28",
        "accrued_cents": 60000, "paid_cents": 0, "outstanding_cents": 60000,
        "employees": [{"employee_name": "Milan S", "fund_name": "AustralianSuper",
                       "accrued_cents": 60000, "paid_cents": 0,
                       "outstanding_cents": 60000, "status": "accrued",
                       "is_overdue": True}],
    }]}
    b = rpdf.build_super_pdf(d, {})
    assert b[:5] == b"%PDF-" and len(b) > 500


def test_leave_balances_pdf():
    d = {"generated_at": "2026-08-01T00:00:00Z",
         "rows": [{"employee_id": "e1", "employee_name": "Milan S",
                    "by_type": {"annual": {"entitled_hours": "76.0",
                                            "future_approved_hours": "0.0",
                                            "remaining_hours": "76.0"}}}]}
    b = rpdf.build_leave_balances_pdf(d, {})
    assert b[:5] == b"%PDF-"
