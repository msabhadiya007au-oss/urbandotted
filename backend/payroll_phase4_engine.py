"""Payroll Phase 4 — pure calculation & quarter helpers.

No DB / no web dependencies so this stays unit-testable. Handles:
    * Australian SG quarter derivation (Q1..Q4) and due dates.
    * Leave accrual math for a pay period, given an employee's configured rate.
    * Balance derivation from an immutable leave-transaction ledger.

Phase 4 rules (explicit):
    * NEVER assume award-specific defaults. Every accrual is driven by the
      employee's own configured `hours_per_pay_period` or an explicit
      business-level default that the owner has entered.
    * Casual employees do NOT accrue paid leave unless the owner has
      explicitly configured an accrual > 0. This is enforced at the
      call site by only reading from configured accruals.
    * All hours are stored as strings (decimal-safe) at rest and only
      converted to Decimal for math here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional


CENT = Decimal("0.01")


def _d(v) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# Australian SG super quarters
# ---------------------------------------------------------------------------
# Q1: Jul-Sep  (payment due 28 Oct)
# Q2: Oct-Dec  (payment due 28 Jan)
# Q3: Jan-Mar  (payment due 28 Apr)
# Q4: Apr-Jun  (payment due 28 Jul)
QUARTER_MONTHS = {
    "Q1": (7, 9), "Q2": (10, 12), "Q3": (1, 3), "Q4": (4, 6),
}


def quarter_of(payment_date: str) -> str:
    m = int(payment_date[5:7])
    if 7 <= m <= 9:
        return "Q1"
    if 10 <= m <= 12:
        return "Q2"
    if 1 <= m <= 3:
        return "Q3"
    return "Q4"


def quarter_bounds(fy: str, quarter: str) -> tuple[str, str, str]:
    """Return (period_start, period_end, due_date) as YYYY-MM-DD strings."""
    start_year = int(fy.replace("FY", "").split("-")[0])   # FY2026-27 -> 2026
    if quarter == "Q1":       # Jul-Sep of start_year
        return f"{start_year}-07-01", f"{start_year}-09-30", f"{start_year}-10-28"
    if quarter == "Q2":       # Oct-Dec of start_year
        return f"{start_year}-10-01", f"{start_year}-12-31", f"{start_year + 1}-01-28"
    if quarter == "Q3":       # Jan-Mar of start_year+1
        return f"{start_year + 1}-01-01", f"{start_year + 1}-03-31", f"{start_year + 1}-04-28"
    # Q4: Apr-Jun of start_year+1
    return f"{start_year + 1}-04-01", f"{start_year + 1}-06-30", f"{start_year + 1}-07-28"


def is_overdue(due_date: str, today_iso: str, paid_cents: int, accrued_cents: int) -> bool:
    """Overdue = past due date AND not fully paid."""
    if paid_cents >= accrued_cents and accrued_cents > 0:
        return False
    return today_iso > due_date and accrued_cents > 0


# ---------------------------------------------------------------------------
# Leave accrual
# ---------------------------------------------------------------------------
def accrual_hours_for_period(config_hours_per_period, employee_status: str = "active") -> str:
    """Return the number of hours accrued this pay period as a decimal string.

    * If the employee is on leave or terminated, we still accrue if a rate is
      configured (the owner decides; we do not silently zero it out).
    * If archived, we return 0 (safety).
    """
    if employee_status == "archived":
        return "0"
    h = _d(config_hours_per_period)
    if h <= 0:
        return "0"
    # 4dp precision is more than enough for leave hours
    q = h.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(q, "f")


def sum_hours(entries: Iterable[dict]) -> str:
    """Sum a ledger of {hours: str} entries. Signed. Returns decimal string."""
    total = Decimal(0)
    for e in entries or []:
        total += _d(e.get("hours"))
    return format(total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def format_hours(v) -> str:
    """Canonical hours display: strip trailing zeros but keep at least 1 decimal."""
    d = _d(v).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    s = format(d.normalize(), "f")
    if "." not in s:
        s += ".0"
    return s


__all__ = [
    "quarter_of", "quarter_bounds", "is_overdue",
    "accrual_hours_for_period", "sum_hours", "format_hours",
]
