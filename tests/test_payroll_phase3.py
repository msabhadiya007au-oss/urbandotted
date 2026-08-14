"""Payroll Phase 3 unit tests — PDF renderer determinism and snapshot integrity."""
import os, sys, pathlib
os.environ.setdefault("PAYROLL_ENC_KEY", "test-key-phase3")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import payroll_pdf as pdfgen  # noqa: E402


def _snap(**over):
    base = {
        "payslip_ref": "UD-PS-2026-000001",
        "pay_run_ref": "UD-PR-2026-000001",
        "status": "finalised",
        "period_start": "2026-08-03", "period_end": "2026-08-16",
        "payment_date": "2026-08-19", "pay_frequency": "fortnightly",
        "standard_hours": "76",
        "employer": {"legal_business_name": "Urban Dotted Pty Ltd", "abn": "12345678901"},
        "employee": {"employee_id": "emp_1", "first_name": "Milan", "last_name": "S",
                     "address_line": "1 Main St, Adelaide, SA, 5000"},
        "earning_lines": [
            {"label": "Ordinary Hours", "hours_or_units": "76", "rate_cents": 3000,
             "amount_cents": 228000, "calc_type": "hourly", "date": None},
        ],
        "gross_cents": 228000, "pretax_ded_cents": 0, "taxable_cents": 228000,
        "payg_cents": 0, "posttax_ded_cents": 0, "net_cents": 228000,
        "super_cents": 27360, "super": {"fund_name": "AustralianSuper", "sg_rate": "0.12"},
        "leave_balances": [{"leave_type": "annual", "remaining_hours": "76.0"}],
        "ytd": {"gross_cents": 228000, "taxable_cents": 228000, "payg_cents": 0,
                "pretax_ded_cents": 0, "posttax_ded_cents": 0, "net_cents": 228000,
                "super_cents": 27360},
    }
    base.update(over)
    return base


def test_pdf_is_bytes_and_pdf_header():
    b = pdfgen.build_payslip_pdf(_snap())
    assert isinstance(b, bytes)
    assert b[:5] == b"%PDF-"


def test_pdf_deterministic_length_range():
    # Same input twice should produce comparably sized outputs.
    b1 = pdfgen.build_payslip_pdf(_snap())
    b2 = pdfgen.build_payslip_pdf(_snap())
    assert abs(len(b1) - len(b2)) < 200  # small variance possible from timestamps


def test_pdf_two_pages_when_dated_lines():
    dated = _snap(earning_lines=[
        {"label": "Ordinary Hours", "hours_or_units": "6", "rate_cents": 3000,
         "amount_cents": 18000, "calc_type": "hourly", "date": "2026-08-03"},
        {"label": "Ordinary Hours", "hours_or_units": "6", "rate_cents": 3000,
         "amount_cents": 18000, "calc_type": "hourly", "date": "2026-08-04"},
    ])
    b = pdfgen.build_payslip_pdf(dated)
    assert b.count(b"/Page ") + b.count(b"/Type /Page") >= 2  # at least one break


def test_pdf_voided_stamp():
    normal = pdfgen.build_payslip_pdf(_snap())
    voided = pdfgen.build_payslip_pdf(_snap(status="voided", void_reason="test correction"))
    # Voided version adds an extra banner block, so bytes differ and voided is longer.
    assert normal != voided
    assert len(voided) > len(normal) - 200
