"""Core: db handle, money/GST engine, Australian FY helpers, audit."""
import os
import uuid
from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

APP_NAME = "urbandotted-expense-book"
TZ = "Australia/Adelaide"
CENT = Decimal("0.01")

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- money ----------
def to_cents(value) -> int:
    if value is None or value == "":
        return 0
    d = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    return int(d * 100)


def to_dollars(cents: Optional[int]) -> float:
    return float((Decimal(int(cents or 0)) / Decimal(100)).quantize(CENT))


def pct(part, whole):
    """Percentage, or None when mathematically invalid."""
    if not whole:
        return None
    return round(float(Decimal(str(part)) / Decimal(str(whole)) * 100), 2)


def change_pct(current, previous):
    if previous in (None, 0):
        return None
    return round(float((Decimal(str(current)) - Decimal(str(previous))) / abs(Decimal(str(previous))) * 100), 2)


# ---------- Australian financial year ----------
def parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)[:10]).date()


def fy_of(d) -> str:
    """1 July -> 30 June. 2026-07-01 => FY2026-27."""
    d = parse_date(d)
    start = d.year if d.month >= 7 else d.year - 1
    return f"FY{start}-{str(start + 1)[2:]}"


def fy_bounds(fy: str):
    start_year = int(fy.replace("FY", "").split("-")[0])
    return date(start_year, 7, 1), date(start_year + 1, 6, 30)


def fy_month_keys(fy: str):
    """12 month keys in FY order: YYYY-MM from July to June."""
    start_year = int(fy.replace("FY", "").split("-")[0])
    keys = []
    for i in range(12):
        m = 7 + i
        y = start_year + (0 if m <= 12 else 1)
        mm = m if m <= 12 else m - 12
        keys.append(f"{y}-{mm:02d}")
    return keys


def month_key_of(d) -> str:
    d = parse_date(d)
    return f"{d.year}-{d.month:02d}"


def month_label(month_key: str) -> str:
    y, m = month_key.split("-")
    return f"{MONTH_NAMES[int(m) - 1]} {y}"


def quarter_of(month_key: str) -> str:
    """Australian BAS quarters: Q1 Jul-Sep, Q2 Oct-Dec, Q3 Jan-Mar, Q4 Apr-Jun."""
    m = int(month_key.split("-")[1])
    if m in (7, 8, 9):
        return "Q1 (Jul-Sep)"
    if m in (10, 11, 12):
        return "Q2 (Oct-Dec)"
    if m in (1, 2, 3):
        return "Q3 (Jan-Mar)"
    return "Q4 (Apr-Jun)"


def current_fy() -> str:
    return fy_of(datetime.now(timezone.utc).date())


def fy_options(count: int = 8):
    """Return the current AU FY and the previous `count-1` historical FYs.
    Never emits a future FY. Ordered newest-first.
    Example: on 2026-08-15 (FY2026-27) with count=8 returns
        ['FY2026-27','FY2025-26','FY2024-25', ... 'FY2019-20']
    """
    cur = int(current_fy().replace("FY", "").split("-")[0])
    return [f"FY{y}-{str(y + 1)[2:]}" for y in range(cur, cur - count, -1)]


# ---------- GST engine ----------
GST_TREATMENTS = ["gst_included", "gst_excluded", "gst_free", "no_gst", "custom", "unknown"]
GST_LABELS = {
    "gst_included": "GST included",
    "gst_excluded": "GST excluded",
    "gst_free": "GST-free",
    "no_gst": "No GST",
    "custom": "Custom tax rate",
    "unknown": "Unknown / needs accountant review",
}


def compute_gst(amount, treatment: str, rate=None, custom_inclusive: bool = True, default_rate="0.10"):
    """Returns (ex_cents, gst_cents, inc_cents, needs_review). Decimal-safe."""
    amt = Decimal(str(amount or 0))
    r = Decimal(str(rate)) if rate not in (None, "") else Decimal(str(default_rate))
    needs_review = False

    if treatment == "gst_included":
        inc = amt
        ex = (inc / (Decimal(1) + r)).quantize(CENT, rounding=ROUND_HALF_UP)
        gst = inc - ex
    elif treatment == "gst_excluded":
        ex = amt
        gst = (ex * r).quantize(CENT, rounding=ROUND_HALF_UP)
        inc = ex + gst
    elif treatment == "custom":
        if custom_inclusive:
            inc = amt
            ex = (inc / (Decimal(1) + r)).quantize(CENT, rounding=ROUND_HALF_UP)
            gst = inc - ex
        else:
            ex = amt
            gst = (ex * r).quantize(CENT, rounding=ROUND_HALF_UP)
            inc = ex + gst
    elif treatment in ("gst_free", "no_gst"):
        ex = inc = amt
        gst = Decimal(0)
        r = Decimal(0)
    else:  # unknown
        ex = inc = amt
        gst = Decimal(0)
        needs_review = True

    return to_cents(ex), to_cents(gst), to_cents(inc), needs_review


# ---------- audit ----------
async def audit(business_id: str, user, entity: str, entity_id: str, action: str,
                before=None, after=None):
    await db.audit_logs.insert_one({
        "log_id": new_id("log"),
        "business_id": business_id,
        "user_id": (user or {}).get("user_id"),
        "user_email": (user or {}).get("email"),
        "entity": entity,
        "entity_id": entity_id,
        "action": action,
        "before": before,
        "after": after,
        "at": now_iso(),
    })


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id")
    await db.user_sessions.create_index("session_token")
    await db.login_attempts.create_index("identifier")
    await db.transactions.create_index([("business_id", 1), ("date", -1)])
    await db.transactions.create_index([("business_id", 1), ("fy", 1), ("month_key", 1)])
    await db.transactions.create_index([("business_id", 1), ("category_id", 1)])
    await db.transactions.create_index([("business_id", 1), ("txn_type", 1)])
    await db.transactions.create_index(
        [("business_id", 1), ("external_source", 1), ("external_id", 1)], sparse=True)
    await db.categories.create_index([("business_id", 1), ("parent_id", 1)])
    await db.documents.create_index([("business_id", 1), ("is_deleted", 1)])
    await db.inventory_purchases.create_index([("business_id", 1), ("date", -1)])
    await db.assets.create_index([("business_id", 1), ("date", -1)])
    await db.suppliers.create_index([("business_id", 1), ("name", 1)])
    await db.reminders.create_index([("business_id", 1), ("month_key", 1)])
    # Daily Entry: backs the upsert that guarantees one transaction per field per day
    await db.transactions.create_index(
        [("business_id", 1), ("daily_entry_id", 1), ("daily_field_id", 1)], sparse=True)
    await db.daily_fields.create_index([("business_id", 1), ("sort", 1)])
    await db.daily_entries.create_index([("business_id", 1), ("entry_date", -1)])
    await db.daily_entries.create_index([("business_id", 1), ("fy", 1), ("month_key", 1)])
    # ----- Payroll (Phase 1) -----
    await db.payroll_settings.create_index("business_id", unique=True)
    await db.employees.create_index([("business_id", 1), ("last_name", 1)])
    await db.employees.create_index([("business_id", 1), ("employee_id", 1)], unique=True)
    await db.employees.create_index([("business_id", 1), ("status", 1)])
    await db.employee_pay_settings.create_index(
        [("business_id", 1), ("employee_id", 1), ("effective_from", -1)])
    await db.employee_super.create_index(
        [("business_id", 1), ("employee_id", 1)], unique=True)
    await db.employee_tax_settings.create_index(
        [("business_id", 1), ("employee_id", 1)], unique=True)
    await db.employee_bank_details.create_index(
        [("business_id", 1), ("employee_id", 1)], unique=True)
    await db.employee_leave_balances.create_index(
        [("business_id", 1), ("employee_id", 1), ("leave_type", 1)], unique=True)
    await db.pay_items.create_index(
        [("business_id", 1), ("code", 1)], unique=True)
    await db.pay_leave_types.create_index(
        [("business_id", 1), ("code", 1)], unique=True)
    # Pay runs (Phase 2)
    await db.pay_runs.create_index(
        [("business_id", 1), ("pay_run_ref", 1)], unique=True)
    await db.pay_runs.create_index([("business_id", 1), ("status", 1), ("payment_date", -1)])
    await db.pay_runs.create_index([("business_id", 1), ("fy", 1)])
    await db.pay_run_employees.create_index(
        [("business_id", 1), ("pay_run_ref", 1), ("employee_id", 1)], unique=True)
    await db.pay_run_lines.create_index(
        [("business_id", 1), ("pay_run_ref", 1), ("employee_id", 1)])
    # Payslips (Phase 3)
    await db.payslips.create_index(
        [("business_id", 1), ("payslip_ref", 1)], unique=True)
    await db.payslips.create_index(
        [("business_id", 1), ("employee_id", 1), ("fy", 1)])
    await db.payslips.create_index(
        [("business_id", 1), ("pay_run_ref", 1)])
    # ----- Payroll Phase 4: super, leave, reports -----
    await db.super_liabilities.create_index(
        [("business_id", 1), ("employee_id", 1), ("fy", 1), ("quarter", 1)], unique=True)
    await db.super_liabilities.create_index(
        [("business_id", 1), ("status", 1), ("due_date", 1)])
    await db.leave_transactions.create_index(
        [("business_id", 1), ("employee_id", 1), ("leave_type", 1),
         ("effective_date", -1)])
    await db.leave_transactions.create_index(
        [("business_id", 1), ("source", 1), ("source_ref", 1), ("txn_type", 1)])
    await db.leave_requests.create_index(
        [("business_id", 1), ("status", 1), ("start_date", -1)])
    await db.leave_requests.create_index(
        [("business_id", 1), ("employee_id", 1)])
    await db.employee_leave_settings.create_index(
        [("business_id", 1), ("employee_id", 1)], unique=True)
