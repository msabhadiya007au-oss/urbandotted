"""Automated tests for critical financial calculation functions."""
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

import pytest
from core import (compute_gst, to_cents, to_dollars, pct, change_pct, fy_of, fy_bounds,
                  fy_month_keys, month_key_of, quarter_of)


# ---------- GST ----------
def test_gst_inclusive():
    ex, gst, inc, review = compute_gst(110, "gst_included")
    assert (ex, gst, inc, review) == (10000, 1000, 11000, False)


def test_gst_inclusive_rounding():
    ex, gst, inc, _ = compute_gst(100, "gst_included")
    assert ex == 9091 and gst == 909 and inc == 10000
    assert ex + gst == inc  # no lost cents


def test_gst_exclusive():
    ex, gst, inc, _ = compute_gst(100, "gst_excluded")
    assert (ex, gst, inc) == (10000, 1000, 11000)


def test_gst_free():
    ex, gst, inc, review = compute_gst(250.55, "gst_free")
    assert (ex, gst, inc, review) == (25055, 0, 25055, False)


def test_no_gst():
    ex, gst, inc, _ = compute_gst(12, "no_gst")
    assert (ex, gst, inc) == (1200, 0, 1200)


def test_custom_rate_inclusive():
    ex, gst, inc, _ = compute_gst(100, "custom", "0.05", True)
    assert (ex, gst, inc) == (9524, 476, 10000)
    assert ex + gst == inc


def test_custom_rate_exclusive():
    ex, gst, inc, _ = compute_gst(200, "custom", "0.15", False)
    assert (ex, gst, inc) == (20000, 3000, 23000)


def test_unknown_flags_review():
    ex, gst, inc, review = compute_gst(99.99, "unknown")
    assert review is True and gst == 0 and ex == inc == 9999


def test_gst_default_rate_override():
    ex, gst, inc, _ = compute_gst(100, "gst_excluded", None, True, "0.20")
    assert (ex, gst, inc) == (10000, 2000, 12000)


# ---------- money safety ----------
def test_to_cents_decimal_safe():
    assert to_cents("0.145") == 15  # ROUND_HALF_UP
    assert to_cents(0.1 + 0.2) == 30  # float artefact does not leak
    assert to_cents("19.99") == 1999
    assert to_cents(None) == 0


def test_to_dollars_roundtrip():
    for v in ["0.01", "19.99", "12345.67", "1000000.00"]:
        assert to_dollars(to_cents(v)) == float(v)


def test_negative_adjustment():
    ex, gst, inc, _ = compute_gst(-50, "gst_included")
    assert inc == -5000 and ex + gst == inc


def test_large_sum_no_drift():
    total = sum(to_cents("0.01") for _ in range(10000))
    assert total == 100_00  # $100.00 exactly


# ---------- percentages ----------
def test_pct_and_guard():
    assert pct(50, 200) == 25.0
    assert pct(10, 0) is None  # never invented
    assert change_pct(120, 100) == 20.0
    assert change_pct(80, 100) == -20.0
    assert change_pct(100, 0) is None
    assert change_pct(100, None) is None


# ---------- Australian financial year ----------
def test_fy_boundaries():
    assert fy_of("2026-07-01") == "FY2026-27"   # first day of new FY
    assert fy_of("2026-06-30") == "FY2025-26"   # last day of old FY
    assert fy_of("2026-01-15") == "FY2025-26"
    assert fy_of("2025-12-31") == "FY2025-26"


def test_fy_bounds():
    start, end = fy_bounds("FY2026-27")
    assert start.isoformat() == "2026-07-01"
    assert end.isoformat() == "2027-06-30"


def test_fy_month_keys_order():
    keys = fy_month_keys("FY2025-26")
    assert len(keys) == 12
    assert keys[0] == "2025-07" and keys[5] == "2025-12"
    assert keys[6] == "2026-01" and keys[-1] == "2026-06"


def test_month_key():
    assert month_key_of("2026-03-09") == "2026-03"


def test_bas_quarters():
    assert quarter_of("2025-07") == "Q1 (Jul-Sep)"
    assert quarter_of("2025-11") == "Q2 (Oct-Dec)"
    assert quarter_of("2026-02") == "Q3 (Jan-Mar)"
    assert quarter_of("2026-05") == "Q4 (Apr-Jun)"


# ---------- profit & COGS arithmetic ----------
def _pnl(gross, discounts, refunds, cogs, opex):
    net = gross - discounts - refunds
    gp = net - cogs
    return net, gp, gp - opex


def test_profit_chain():
    net, gp, op = _pnl(10000, 500, 300, 4000, 2500)
    assert net == 9200 and gp == 5200 and op == 2700


def test_refund_rate_and_margins():
    net, gp, op = _pnl(10000, 0, 1000, 3000, 2000)
    assert pct(1000, 10000) == 10.0        # refund rate
    assert pct(gp, net) == 66.67           # gross margin
    assert pct(op, net) == 44.44           # operating margin


def test_landed_unit_cost():
    qty, unit = 1000, Decimal("5.00")
    total = to_cents(unit * qty) + to_cents(500) + to_cents(300) + to_cents(580) + to_cents(100)
    assert total == 648000  # $6,480.00
    landed_unit = round(total / qty)
    assert landed_unit == 648  # $6.48 per unit


def test_cogs_not_purchase():
    """COGS for 200 units at $6.48 landed is $1,296 — not the $6,480 purchase."""
    landed_unit_cents = 648
    cogs = 200 * landed_unit_cents
    assert to_dollars(cogs) == 1296.00
    assert to_dollars(cogs) != 6480.00


def test_fifo_consumption_across_lots():
    lots = [{"remaining": 100, "landed": 500}, {"remaining": 100, "landed": 600}]
    need, cogs = 150, 0
    for lot in lots:
        take = min(lot["remaining"], need)
        cogs += take * lot["landed"]
        lot["remaining"] -= take
        need -= take
    assert need == 0
    assert to_dollars(cogs) == 800.00  # 100@5.00 + 50@6.00
    assert lots[1]["remaining"] == 50


# ---------- CSV import parsers ----------
def test_csv_amount_and_date_parsing():
    from routes_reports import _parse_amount, _parse_date_flexible
    assert _parse_amount("$1,234.56") == 1234.56
    assert _parse_amount("(50.00)") == 50.00
    assert _parse_amount("") is None
    assert _parse_amount("abc") is None
    assert _parse_date_flexible("09/03/2026") == "2026-03-09"  # AU day-first
    assert _parse_date_flexible("2026-03-09") == "2026-03-09"
    assert _parse_date_flexible("not a date") is None
