"""Payroll calculation engine (Phase 2).

Pure functions, decimal-safe, isolated from web/DB layers so unit tests can
exercise every branch without a database. All money is INT CENTS at every
public boundary; internal arithmetic uses Decimal with ROUND_HALF_UP.

PAYG STATUS
-----------
This module does NOT implement Australian PAYG withholding tables. `payg_manual`
returns whatever manual value the caller provides (from the employee's
`manual_payg_override` or the per-pay-run editable field). The presence of a
dedicated `payg_calculate` entry point is intentional: when verified ATO tax
tables are supplied, they can be dropped in behind the same interface without
touching pay-run code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence

CENT = Decimal("0.01")


def _d(v) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    return Decimal(str(v))


def to_cents(dollars) -> int:
    """Dollars (str/Decimal/int/float) -> int cents, banker-neutral half-up."""
    return int((_d(dollars) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_dollars_str(cents: int) -> str:
    d = (Decimal(int(cents or 0)) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    return format(d, ".2f")


# ============================================================================
# Ordinary earnings per pay period (salary / fixed employees)
# ============================================================================
FREQ_DIVISOR = {
    "weekly": Decimal(52),
    "fortnightly": Decimal(26),
    "monthly": Decimal(12),
}


def ordinary_gross_cents(pay_settings: dict) -> int:
    """Return the DEFAULT ordinary earnings for one pay period, in cents.

    For hourly employees this is std_hours_per_(week|fortnight|month) times the
    base hourly rate. For salary/fixed employees it is derived from the annual
    salary and pay frequency, or the fixed pay amount.

    The result is a starting suggestion for the pay-run editor; the user may
    override individual line hours before finalisation.
    """
    basis = pay_settings.get("pay_basis", "hourly")
    freq = pay_settings.get("pay_frequency", "fortnightly")
    if basis == "hourly":
        rate = _d(pay_settings.get("base_hourly_rate"))
        hours = _d({
            "weekly": pay_settings.get("std_hours_per_week"),
            "fortnightly": pay_settings.get("std_hours_per_fortnight")
                            or (_d(pay_settings.get("std_hours_per_week")) * 2),
            "monthly": pay_settings.get("std_hours_per_month")
                            or (_d(pay_settings.get("std_hours_per_week")) * Decimal("52") / Decimal("12")),
            "custom": pay_settings.get("std_hours_per_week"),
        }.get(freq, pay_settings.get("std_hours_per_week")))
        return to_cents(rate * hours)
    if basis == "annual_salary":
        annual = _d(pay_settings.get("annual_salary"))
        div = FREQ_DIVISOR.get(freq, Decimal(26))
        return to_cents(annual / div)
    if basis == "monthly_salary":
        monthly = _d(pay_settings.get("monthly_salary"))
        # If a monthly-salary employee is on weekly pay we still divide correctly.
        if freq == "weekly":
            return to_cents(monthly * Decimal(12) / Decimal(52))
        if freq == "fortnightly":
            return to_cents(monthly * Decimal(12) / Decimal(26))
        return to_cents(monthly)
    if basis == "fixed_pay":
        return to_cents(pay_settings.get("fixed_pay_amount"))
    return 0


def suggested_hours_for_period(pay_settings: dict) -> str:
    """Return the default hours to pre-fill on the hourly pay-run editor."""
    freq = pay_settings.get("pay_frequency", "fortnightly")
    hpw = _d(pay_settings.get("std_hours_per_week"))
    if freq == "weekly":
        return format(hpw, "f")
    if freq == "fortnightly":
        v = _d(pay_settings.get("std_hours_per_fortnight")) or (hpw * 2)
        return format(v, "f")
    if freq == "monthly":
        v = _d(pay_settings.get("std_hours_per_month")) or (hpw * Decimal("52") / Decimal("12"))
        return format(v.quantize(CENT, rounding=ROUND_HALF_UP), "f")
    return format(hpw, "f")


# ============================================================================
# Line-item amount
# ============================================================================
def line_amount_cents(calc_type: str, hours_or_units, rate_cents: int,
                      base_rate_cents: Optional[int] = None) -> int:
    """Given a pay-item calc_type + hours/units + rate, return line amount in cents.

    - fixed          : `rate_cents` IS the fixed amount (hours ignored)
    - hourly         : hours * rate_cents
    - units_rate     : units * rate_cents
    - percent_of_base: rate_cents is a percent * 10000, applied to base_rate_cents
                       times hours (e.g. 17500 => 175% loading on ordinary rate)
    - percent_loading: same math as percent_of_base but conceptually a loading
                       ON TOP of the base (e.g. Saturday 25% loading -> rate_cents=12500)
    """
    hours = _d(hours_or_units)
    r = Decimal(int(rate_cents or 0))
    if calc_type == "fixed":
        return int(r.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if calc_type in ("hourly", "units_rate"):
        return int((hours * r).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if calc_type in ("percent_of_base", "percent_loading"):
        base = Decimal(int(base_rate_cents or 0))
        pct = r / Decimal(10000)     # rate stored as percent * 10000 (i.e. bps of 100)
        return int((hours * base * pct).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    raise ValueError(f"Unknown calc_type: {calc_type}")


# ============================================================================
# Super
# ============================================================================
def super_amount_cents(superable_cents: int, sg_rate_decimal) -> int:
    """Employer super = superable_earnings * sg_rate. Never negative."""
    if superable_cents <= 0:
        return 0
    rate = _d(sg_rate_decimal)
    if rate <= 0:
        return 0
    return int((Decimal(int(superable_cents)) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ============================================================================
# PAYG withholding
# ============================================================================
def payg_manual(manual_payg_dollars, override_cents: Optional[int] = None) -> int:
    """Return the manual PAYG withholding for this pay run in cents.

    An explicit per-pay-run override wins; otherwise use the employee's default.
    NOT an ATO tax-table calculation. This is a placeholder interface.
    """
    if override_cents is not None:
        return max(0, int(override_cents))
    return max(0, to_cents(manual_payg_dollars))


PAYG_STATUS_NOTE = (
    "PAYG withholding is entered manually per employee/pay run. This deployment "
    "does not include verified ATO tax tables. Review every value before "
    "finalising and reconcile with your accountant."
)


# ============================================================================
# Full pay-run-line aggregation
# ============================================================================
@dataclass
class LineIn:
    """Input line as it arrives from the frontend / API."""
    pay_item_id: Optional[str]
    code: str
    label: str
    kind: str                       # earning | deduction | leave
    calc_type: str
    hours_or_units: str = "0"
    rate_cents: int = 0
    base_rate_cents: Optional[int] = None
    taxable: bool = True
    super_liable: bool = True
    deduction_category: Optional[str] = None   # pretax | posttax (only if kind==deduction)
    date: Optional[str] = None
    amount_cents_override: Optional[int] = None  # user manually typed an amount


@dataclass
class LineOut(LineIn):
    amount_cents: int = 0


@dataclass
class EmployeeTotals:
    lines: list = field(default_factory=list)
    gross_cents: int = 0
    taxable_cents: int = 0
    pretax_ded_cents: int = 0
    posttax_ded_cents: int = 0
    payg_cents: int = 0
    net_cents: int = 0
    superable_cents: int = 0
    super_cents: int = 0
    super_rate: str = "0"
    total_employer_cost_cents: int = 0

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["lines"] = [l.__dict__ for l in self.lines]  # noqa: E741
        return d


def calculate_employee_pay(lines: Sequence[LineIn], sg_rate_decimal,
                            manual_payg_dollars, payg_override_cents: Optional[int] = None,
                            base_rate_cents: Optional[int] = None) -> EmployeeTotals:
    """Aggregate lines into totals. Deterministic, pure. Never mutates inputs."""
    out = EmployeeTotals(super_rate=str(_d(sg_rate_decimal)))
    for src in lines:
        # Compute the effective amount for this line
        if src.amount_cents_override is not None:
            amount = int(src.amount_cents_override)
        else:
            amount = line_amount_cents(
                calc_type=src.calc_type,
                hours_or_units=src.hours_or_units,
                rate_cents=src.rate_cents,
                base_rate_cents=src.base_rate_cents or base_rate_cents,
            )
        line = LineOut(**{**src.__dict__, "amount_cents": amount})
        out.lines.append(line)
        if src.kind == "earning":
            out.gross_cents += amount
            if src.super_liable:
                out.superable_cents += amount
        elif src.kind == "deduction":
            if src.deduction_category == "pretax":
                out.pretax_ded_cents += amount
            else:
                out.posttax_ded_cents += amount
        # 'leave' lines with pay attached are treated as earnings when kind==earning;
        # a pure-leave-only ledger line has kind='leave' and does not affect totals here.

    out.taxable_cents = max(0, out.gross_cents - out.pretax_ded_cents)
    out.payg_cents = payg_manual(manual_payg_dollars, payg_override_cents)
    if out.payg_cents > out.taxable_cents:
        out.payg_cents = out.taxable_cents
    out.net_cents = out.taxable_cents - out.payg_cents - out.posttax_ded_cents
    out.super_cents = super_amount_cents(out.superable_cents, sg_rate_decimal)
    out.total_employer_cost_cents = out.gross_cents + out.super_cents
    return out


def aggregate_pay_run(employee_totals: Iterable[EmployeeTotals]) -> dict:
    agg = {"employee_count": 0, "gross_cents": 0, "taxable_cents": 0,
           "payg_cents": 0, "pretax_ded_cents": 0, "posttax_ded_cents": 0,
           "net_cents": 0, "super_cents": 0, "total_employer_cost_cents": 0}
    for et in employee_totals:
        agg["employee_count"] += 1
        for k in ("gross_cents", "taxable_cents", "payg_cents", "pretax_ded_cents",
                  "posttax_ded_cents", "net_cents", "super_cents", "total_employer_cost_cents"):
            agg[k] += getattr(et, k)
    return agg
