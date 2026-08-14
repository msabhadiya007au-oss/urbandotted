"""Payroll Phase 2 unit tests — calculation engine.

Comprehensive coverage of the pure calc functions in payroll_calc.py.
No DB dependency.
"""
import os, sys, pathlib
os.environ.setdefault("PAYROLL_ENC_KEY", "test-key-phase2")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402
import payroll_calc as pc  # noqa: E402


# ------------------------------------------------------------------ money
def test_to_cents_rounding():
    assert pc.to_cents("10") == 1000
    assert pc.to_cents("10.005") == 1001  # half-up
    assert pc.to_cents("0.004") == 0
    assert pc.to_cents(None) == 0
    assert pc.to_cents("") == 0


def test_to_dollars_str():
    assert pc.to_dollars_str(1234) == "12.34"
    assert pc.to_dollars_str(0) == "0.00"


# ------------------------------------------------------------------ ordinary
def test_ordinary_hourly_weekly():
    ps = {"pay_basis": "hourly", "pay_frequency": "weekly",
          "base_hourly_rate": "30", "std_hours_per_week": "38"}
    assert pc.ordinary_gross_cents(ps) == pc.to_cents(30 * 38)


def test_ordinary_hourly_fortnightly():
    ps = {"pay_basis": "hourly", "pay_frequency": "fortnightly",
          "base_hourly_rate": "30", "std_hours_per_week": "38"}
    # falls back to hours_per_week * 2 when fortnight field missing
    assert pc.ordinary_gross_cents(ps) == pc.to_cents(30 * 76)


def test_ordinary_salary_weekly():
    ps = {"pay_basis": "annual_salary", "pay_frequency": "weekly", "annual_salary": "52000"}
    assert pc.ordinary_gross_cents(ps) == 100000  # $1000/week


def test_ordinary_salary_fortnightly():
    ps = {"pay_basis": "annual_salary", "pay_frequency": "fortnightly", "annual_salary": "70000"}
    # 70000/26 = 2692.307...  -> $2692.31
    assert pc.ordinary_gross_cents(ps) == 269231


def test_ordinary_salary_monthly():
    ps = {"pay_basis": "monthly_salary", "pay_frequency": "monthly", "monthly_salary": "5000"}
    assert pc.ordinary_gross_cents(ps) == 500000


def test_ordinary_fixed():
    ps = {"pay_basis": "fixed_pay", "pay_frequency": "weekly", "fixed_pay_amount": "1234.56"}
    assert pc.ordinary_gross_cents(ps) == 123456


# ------------------------------------------------------------------ line amount
def test_line_hourly():
    assert pc.line_amount_cents("hourly", "20", 3000) == 60000  # 20h * $30 = $600


def test_line_fixed_uses_rate():
    assert pc.line_amount_cents("fixed", "0", 25000) == 25000  # rate IS the amount


def test_line_units_rate():
    assert pc.line_amount_cents("units_rate", "3", 5000) == 15000  # 3 units × $50


def test_line_percent_loading():
    # 8h at 25% loading over $30 base: 8 * 3000 * 0.25 = 6000 cents
    assert pc.line_amount_cents("percent_loading", "8", 2500, base_rate_cents=3000) == 6000


def test_line_percent_of_base_150pct():
    # 4h Sunday @ 150% of $30 base: 4 * 3000 * 1.50 = 18000 cents
    assert pc.line_amount_cents("percent_of_base", "4", 15000, base_rate_cents=3000) == 18000


def test_line_zero_hours():
    assert pc.line_amount_cents("hourly", "0", 5000) == 0


def test_line_unknown_calc_type():
    with pytest.raises(ValueError):
        pc.line_amount_cents("bogus", "1", 1000)


# ------------------------------------------------------------------ super
def test_super_positive():
    assert pc.super_amount_cents(100000, "0.12") == 12000


def test_super_zero_earnings():
    assert pc.super_amount_cents(0, "0.12") == 0


def test_super_zero_rate():
    assert pc.super_amount_cents(100000, "0") == 0


def test_super_rounds_half_up():
    # 12345 * 0.115 = 1419.675 -> 1420 cents
    assert pc.super_amount_cents(12345, "0.115") == 1420


# ------------------------------------------------------------------ PAYG
def test_payg_manual_defaults_to_zero():
    assert pc.payg_manual(None) == 0
    assert pc.payg_manual("0") == 0


def test_payg_manual_dollars_to_cents():
    assert pc.payg_manual("120.50") == 12050


def test_payg_override_wins():
    assert pc.payg_manual("120", override_cents=8000) == 8000


def test_payg_never_negative():
    assert pc.payg_manual("-500") == 0
    assert pc.payg_manual("100", override_cents=-1) == 0


# ------------------------------------------------------------------ aggregate
def _line(**kw):
    d = dict(pay_item_id=None, code="X", label="X", kind="earning",
             calc_type="hourly", hours_or_units="0", rate_cents=0,
             base_rate_cents=None, taxable=True, super_liable=True,
             deduction_category=None, date=None, amount_cents_override=None)
    d.update(kw)
    return pc.LineIn(**d)


def test_calc_hourly_20h_30_rate():
    tot = pc.calculate_employee_pay(
        lines=[_line(code="ORD", hours_or_units="20", rate_cents=3000)],
        sg_rate_decimal="0.12", manual_payg_dollars="0",
    )
    assert tot.gross_cents == 60000
    assert tot.taxable_cents == 60000
    assert tot.payg_cents == 0
    assert tot.net_cents == 60000
    assert tot.super_cents == 7200
    assert tot.total_employer_cost_cents == 67200


def test_calc_hourly_mixed_ordinary_shift_overtime():
    tot = pc.calculate_employee_pay(
        lines=[
            _line(code="ORD", hours_or_units="20", rate_cents=3000),
            _line(code="SHIFT175", calc_type="percent_of_base",
                  hours_or_units="12", rate_cents=17500, base_rate_cents=3000),
            _line(code="OT150", calc_type="percent_of_base",
                  hours_or_units="8", rate_cents=15000, base_rate_cents=3000),
        ],
        sg_rate_decimal="0.12", manual_payg_dollars="0",
    )
    # 60000 + 12*3000*1.75(=63000) + 8*3000*1.5(=36000) = 159000
    assert tot.gross_cents == 159000
    assert tot.super_cents == pc.super_amount_cents(159000, "0.12")


def test_calc_salary_fortnightly_with_manual_payg():
    tot = pc.calculate_employee_pay(
        lines=[_line(code="ORD", calc_type="fixed", rate_cents=269231, super_liable=True)],
        sg_rate_decimal="0.12", manual_payg_dollars="450",
    )
    assert tot.gross_cents == 269231
    assert tot.payg_cents == 45000
    assert tot.net_cents == 269231 - 45000
    assert tot.super_cents == pc.super_amount_cents(269231, "0.12")


def test_calc_pretax_deduction_reduces_taxable_and_super_untouched():
    tot = pc.calculate_employee_pay(
        lines=[
            _line(code="ORD", calc_type="fixed", rate_cents=100000, super_liable=True),
            _line(code="SS", kind="deduction", calc_type="fixed", rate_cents=10000,
                  deduction_category="pretax"),
        ],
        sg_rate_decimal="0.12", manual_payg_dollars="0",
    )
    assert tot.gross_cents == 100000
    assert tot.pretax_ded_cents == 10000
    assert tot.taxable_cents == 90000
    assert tot.super_cents == 12000  # super still on the full gross earning (super-liable)


def test_calc_posttax_deduction_reduces_net_only():
    tot = pc.calculate_employee_pay(
        lines=[
            _line(code="ORD", calc_type="fixed", rate_cents=100000),
            _line(code="LOAN", kind="deduction", calc_type="fixed", rate_cents=15000,
                  deduction_category="posttax"),
        ],
        sg_rate_decimal="0.12", manual_payg_dollars="0",
    )
    assert tot.gross_cents == 100000
    assert tot.taxable_cents == 100000
    assert tot.posttax_ded_cents == 15000
    assert tot.net_cents == 100000 - 15000


def test_calc_non_super_earning_excluded_from_super():
    tot = pc.calculate_employee_pay(
        lines=[
            _line(code="ORD", calc_type="fixed", rate_cents=100000, super_liable=True),
            _line(code="REIMB", calc_type="fixed", rate_cents=5000, super_liable=False),
        ],
        sg_rate_decimal="0.12", manual_payg_dollars="0",
    )
    assert tot.gross_cents == 105000
    assert tot.superable_cents == 100000
    assert tot.super_cents == 12000


def test_calc_payg_capped_at_taxable():
    tot = pc.calculate_employee_pay(
        lines=[_line(code="ORD", calc_type="fixed", rate_cents=50000)],
        sg_rate_decimal="0.12", manual_payg_dollars="9999",
    )
    assert tot.payg_cents == 50000
    assert tot.net_cents == 0


def test_aggregate_pay_run_totals():
    e1 = pc.calculate_employee_pay(
        [_line(code="A", calc_type="fixed", rate_cents=100000)],
        "0.12", "0")
    e2 = pc.calculate_employee_pay(
        [_line(code="B", calc_type="fixed", rate_cents=200000)],
        "0.12", "100")
    agg = pc.aggregate_pay_run([e1, e2])
    assert agg["employee_count"] == 2
    assert agg["gross_cents"] == 300000
    assert agg["payg_cents"] == 10000
    assert agg["super_cents"] == e1.super_cents + e2.super_cents
    assert agg["net_cents"] == e1.net_cents + e2.net_cents
