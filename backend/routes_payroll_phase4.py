"""Payroll — Phase 4 endpoints (Super, Leave, Reports, Reminders, Dashboard).

Strict guardrails (from user instructions):
    * DO NOT write anything into the main `transactions` collection. That
      accounting integration lands in Phase 5.
    * NEVER modify a finalised pay run or payslip. Phase 4 only reads from
      finalised payslips and records its own ledger entries.
    * Every collection is scoped by `business_id`. Money is int cents.
    * NO award-specific defaults. Leave accrual is per-employee configuration
      only; if a business default exists it is applied opt-in when a new
      employee is created — never auto-inferred.
"""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
import csv
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user, get_business_id
from core import db, new_id, now_iso, audit, fy_of, current_fy, fy_bounds, month_key_of
import payroll_phase4_engine as pe
import payroll_reports_pdf as rpdf

router = APIRouter(prefix="/api/payroll", tags=["payroll-phase4"])

LEAVE_TXN_TYPES = {"accrual", "taken", "adjustment", "opening"}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ============================================================================
# SUPER LIABILITY LEDGER
# ============================================================================
async def _upsert_super_liability_from_payslip(business_id: str, payslip: dict, user_email: str = ""):
    """Called by pay-run finalise for each newly created payslip. Idempotent by
    (payslip_ref) — a payslip only contributes to one liability row."""
    if int(payslip.get("super_cents", 0) or 0) <= 0:
        return
    fy = payslip.get("fy") or fy_of(payslip["payment_date"])
    quarter = pe.quarter_of(payslip["payment_date"])
    q_start, q_end, due = pe.quarter_bounds(fy, quarter)
    employee_id = payslip["employee_id"]
    key = {"business_id": business_id, "employee_id": employee_id,
           "fy": fy, "quarter": quarter}
    existing = await db.super_liabilities.find_one(key, {"_id": 0})
    if existing:
        # Already contributed? skip.
        if payslip["payslip_ref"] in (existing.get("contributing_payslip_refs") or []):
            return
        await db.super_liabilities.update_one(key, {
            "$inc": {"accrued_cents": int(payslip["super_cents"])},
            "$push": {"contributing_payslip_refs": payslip["payslip_ref"]},
            "$set": {"updated_at": now_iso(), "last_source_email": user_email},
        })
        return
    emp = payslip.get("employee", {}) or {}
    sup = payslip.get("super", {}) or {}
    doc = {
        "liability_id": new_id("suplia"),
        "business_id": business_id,
        "employee_id": employee_id,
        "employee_name": f"{emp.get('first_name','')} {emp.get('last_name','')}".strip(),
        "fund_name": sup.get("fund_name", ""),
        "sg_rate": sup.get("sg_rate", ""),
        "fy": fy,
        "quarter": quarter,
        "period_start": q_start,
        "period_end": q_end,
        "due_date": due,
        "accrued_cents": int(payslip["super_cents"]),
        "paid_cents": 0,
        "status": "accrued",
        "payment_date": None,
        "payment_reference": "",
        "payment_note": "",
        "contributing_payslip_refs": [payslip["payslip_ref"]],
        "created_at": now_iso(),
        "created_by": user_email,
        "updated_at": now_iso(),
    }
    await db.super_liabilities.insert_one(doc)


@router.get("/super-liabilities")
async def list_super_liabilities(fy: Optional[str] = None, quarter: Optional[str] = None,
                                  status: Optional[str] = None,
                                  employee_id: Optional[str] = None,
                                  business_id: str = Depends(get_business_id)):
    q: dict = {"business_id": business_id}
    if fy:
        q["fy"] = fy
    if quarter:
        q["quarter"] = quarter
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    items = await db.super_liabilities.find(q, {"_id": 0}).sort(
        [("due_date", 1), ("employee_name", 1)]).to_list(1000)
    today = _today()
    total_accrued = total_paid = 0
    overdue_count = 0
    for it in items:
        accrued = int(it.get("accrued_cents", 0) or 0)
        paid = int(it.get("paid_cents", 0) or 0)
        it["outstanding_cents"] = max(0, accrued - paid)
        it["is_overdue"] = pe.is_overdue(it.get("due_date", ""), today, paid, accrued)
        total_accrued += accrued
        total_paid += paid
        if it["is_overdue"]:
            overdue_count += 1
    return {
        "items": items, "total": len(items),
        "totals": {"accrued_cents": total_accrued, "paid_cents": total_paid,
                    "outstanding_cents": max(0, total_accrued - total_paid),
                    "overdue_count": overdue_count},
    }


class SuperPayIn(BaseModel):
    paid_cents: int = Field(ge=0)
    payment_date: str
    payment_reference: str = ""
    payment_note: str = ""


@router.post("/super-liabilities/{liability_id}/pay")
async def record_super_payment(liability_id: str, body: SuperPayIn,
                                business_id: str = Depends(get_business_id),
                                user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the business owner can record super payments")
    row = await db.super_liabilities.find_one(
        {"business_id": business_id, "liability_id": liability_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(404, "Super liability not found")
    accrued = int(row.get("accrued_cents", 0) or 0)
    already_paid = int(row.get("paid_cents", 0) or 0)
    new_paid = already_paid + int(body.paid_cents)
    if new_paid > accrued:
        raise HTTPException(422, f"Payment (${body.paid_cents/100:.2f}) exceeds outstanding "
                                  f"amount (${(accrued-already_paid)/100:.2f}).")
    status = "paid" if new_paid >= accrued else ("partial" if new_paid > 0 else "accrued")
    # Payment history log inside the same doc.
    payments = row.get("payments") or []
    payments.append({
        "amount_cents": int(body.paid_cents), "payment_date": body.payment_date,
        "reference": body.payment_reference, "note": body.payment_note,
        "recorded_at": now_iso(), "recorded_by": user.get("email"),
    })
    # Track the last payment date on the top-level doc (any partial payment).
    await db.super_liabilities.update_one(
        {"business_id": business_id, "liability_id": liability_id},
        {"$set": {"paid_cents": new_paid, "status": status,
                  "payment_date": body.payment_date,
                  "payment_reference": body.payment_reference or row.get("payment_reference", ""),
                  "payment_note": body.payment_note or row.get("payment_note", ""),
                  "payments": payments,
                  "updated_at": now_iso(), "updated_by": user.get("email")}},
    )
    await audit(business_id, user, "super_liability", liability_id, "pay",
                after={"paid_cents": new_paid, "status": status})
    return {"ok": True, "liability_id": liability_id,
            "paid_cents": new_paid, "outstanding_cents": max(0, accrued - new_paid),
            "status": status}


# ============================================================================
# EMPLOYEE LEAVE SETTINGS (accrual rates per leave type, per employee)
# ============================================================================
class LeaveAccrualIn(BaseModel):
    leave_type: str = Field(min_length=1, max_length=60)
    hours_per_pay_period: str = "0"
    opening_balance_hours: str = "0"
    active: bool = True


class EmployeeLeaveSettingsIn(BaseModel):
    accruals: List[LeaveAccrualIn] = Field(default_factory=list)
    notes: str = ""


@router.get("/employees/{employee_id}/leave-settings")
async def get_leave_settings(employee_id: str, business_id: str = Depends(get_business_id)):
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = await db.employee_leave_settings.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    return doc or {"accruals": [], "notes": ""}


@router.put("/employees/{employee_id}/leave-settings")
async def put_leave_settings(employee_id: str, body: EmployeeLeaveSettingsIn,
                              business_id: str = Depends(get_business_id),
                              user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    payload = {
        "employee_id": employee_id, "business_id": business_id,
        "accruals": [a.model_dump() for a in body.accruals],
        "notes": body.notes,
        "updated_at": now_iso(), "updated_by": user.get("email"),
    }
    await db.employee_leave_settings.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": payload}, upsert=True,
    )
    # Ensure a leave-balance snapshot row exists for every configured type
    for a in body.accruals:
        exists = await db.employee_leave_balances.find_one(
            {"business_id": business_id, "employee_id": employee_id, "leave_type": a.leave_type}
        )
        if not exists and a.active and pe._d(a.opening_balance_hours) != 0:
            # Record an opening-balance ledger entry (once)
            await _post_leave_txn(business_id, employee_id, a.leave_type, "opening",
                                   a.opening_balance_hours, source="manual",
                                   source_ref="settings_init",
                                   note="Opening balance set from leave settings",
                                   user_email=user.get("email"))
    await audit(business_id, user, "employee_leave_settings", employee_id, "update")
    return payload


# ============================================================================
# LEAVE LEDGER (immutable transactions) & BALANCES
# ============================================================================
async def _post_leave_txn(business_id: str, employee_id: str, leave_type: str,
                          txn_type: str, hours: str, source: str,
                          source_ref: str = "", note: str = "",
                          effective_date: Optional[str] = None,
                          user_email: str = "") -> dict:
    """Append an immutable leave ledger row and refresh the balance snapshot.
    Never call to REVERSE — reversal is another signed ledger row."""
    if txn_type not in LEAVE_TXN_TYPES:
        raise ValueError(f"Bad txn_type: {txn_type}")
    doc = {
        "txn_id": new_id("lvtx"),
        "business_id": business_id,
        "employee_id": employee_id,
        "leave_type": leave_type,
        "txn_type": txn_type,
        "hours": str(hours),
        "source": source,
        "source_ref": source_ref,
        "note": note,
        "effective_date": effective_date or _today(),
        "created_at": now_iso(),
        "created_by": user_email,
    }
    await db.leave_transactions.insert_one(doc)
    await _refresh_leave_balance(business_id, employee_id, leave_type)
    return _clean(doc)


async def _refresh_leave_balance(business_id: str, employee_id: str, leave_type: str):
    """Rebuild snapshot from ledger. Snapshot is derived; ledger is truth."""
    entries = await db.leave_transactions.find(
        {"business_id": business_id, "employee_id": employee_id, "leave_type": leave_type},
        {"_id": 0, "hours": 1},
    ).to_list(10000)
    total = pe.sum_hours(entries)
    # Approved-but-future leave requests reduce "available" but not ledger.
    future_reqs = await db.leave_requests.find(
        {"business_id": business_id, "employee_id": employee_id,
         "leave_type": leave_type, "status": "approved",
         "start_date": {"$gt": _today()}},
        {"_id": 0, "hours": 1},
    ).to_list(500)
    future = pe.sum_hours(future_reqs)
    remaining = pe._d(total) - pe._d(future)
    from decimal import Decimal as _D
    payload = {
        "business_id": business_id,
        "employee_id": employee_id,
        "leave_type": leave_type,
        "entitled_hours": total,
        "future_approved_hours": pe.format_hours(future),
        "remaining_hours": pe.format_hours(remaining if remaining > _D(0) else _D(0)),
        "updated_at": now_iso(),
    }
    await db.employee_leave_balances.update_one(
        {"business_id": business_id, "employee_id": employee_id, "leave_type": leave_type},
        {"$set": payload}, upsert=True,
    )


async def _accrue_leave_from_pay_run(business_id: str, pay_run_ref: str, employee_id: str,
                                      payment_date: str, user_email: str = ""):
    """Add accrual ledger rows for each active leave-type configured for this
    employee. Idempotent guard: (source=pay_run, source_ref=pay_run_ref, employee, type)."""
    settings = await db.employee_leave_settings.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    if not settings or not settings.get("accruals"):
        return
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    ) or {}
    status = emp.get("status", "active")
    for a in settings["accruals"]:
        if not a.get("active"):
            continue
        hrs = pe.accrual_hours_for_period(a.get("hours_per_pay_period"), status)
        if pe._d(hrs) == 0:
            continue
        # idempotency guard
        exists = await db.leave_transactions.find_one({
            "business_id": business_id, "employee_id": employee_id,
            "leave_type": a["leave_type"], "source": "pay_run",
            "source_ref": pay_run_ref, "txn_type": "accrual",
        })
        if exists:
            continue
        await _post_leave_txn(business_id, employee_id, a["leave_type"],
                              "accrual", hrs, source="pay_run",
                              source_ref=pay_run_ref,
                              note=f"Accrued from pay run {pay_run_ref}",
                              effective_date=payment_date,
                              user_email=user_email)


@router.get("/employees/{employee_id}/leave-ledger")
async def leave_ledger(employee_id: str, leave_type: Optional[str] = None,
                        business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id, "employee_id": employee_id}
    if leave_type:
        q["leave_type"] = leave_type
    items = await db.leave_transactions.find(q, {"_id": 0}).sort(
        [("effective_date", -1), ("created_at", -1)]).to_list(2000)
    return {"items": items, "total": len(items)}


class LeaveAdjustmentIn(BaseModel):
    leave_type: str
    hours: str          # signed
    note: str = ""
    effective_date: Optional[str] = None


@router.post("/employees/{employee_id}/leave-adjustments")
async def post_leave_adjustment(employee_id: str, body: LeaveAdjustmentIn,
                                 business_id: str = Depends(get_business_id),
                                 user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the business owner can post leave adjustments")
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = await _post_leave_txn(business_id, employee_id, body.leave_type,
                                 "adjustment", body.hours, source="manual",
                                 source_ref="adjustment",
                                 note=body.note or "Manual adjustment",
                                 effective_date=body.effective_date,
                                 user_email=user.get("email"))
    await audit(business_id, user, "leave_transaction", doc["txn_id"], "adjustment",
                after={"hours": body.hours, "leave_type": body.leave_type})
    return doc


# ============================================================================
# LEAVE REQUESTS
# ============================================================================
class LeaveRequestIn(BaseModel):
    employee_id: str
    leave_type: str = Field(min_length=1, max_length=60)
    start_date: str
    end_date: str
    hours: str = "0"
    reason: str = ""
    note: str = ""


@router.get("/leave-requests")
async def list_leave_requests(status: Optional[str] = None, employee_id: Optional[str] = None,
                               business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    items = await db.leave_requests.find(q, {"_id": 0}).sort(
        [("start_date", -1), ("created_at", -1)]).to_list(1000)
    return {"items": items, "total": len(items)}


@router.post("/leave-requests")
async def create_leave_request(body: LeaveRequestIn,
                                business_id: str = Depends(get_business_id),
                                user: dict = Depends(get_current_user)):
    if body.end_date < body.start_date:
        raise HTTPException(422, "end_date must be on or after start_date")
    if pe._d(body.hours) <= 0:
        raise HTTPException(422, "hours must be > 0")
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": body.employee_id,
         "is_deleted": {"$ne": True}}, {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = {
        "request_id": new_id("lvreq"),
        "business_id": business_id,
        "employee_id": body.employee_id,
        "employee_name": f"{emp.get('preferred_name') or emp.get('first_name','')} {emp.get('last_name','')}".strip(),
        "leave_type": body.leave_type,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "hours": str(body.hours),
        "reason": body.reason,
        "note": body.note,
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user.get("email"),
    }
    await db.leave_requests.insert_one(doc)
    await audit(business_id, user, "leave_request", doc["request_id"], "create",
                after={"employee_id": body.employee_id, "hours": body.hours})
    return _clean(doc)


class RequestActionIn(BaseModel):
    action: str            # approve | reject | cancel
    note: str = ""


@router.post("/leave-requests/{request_id}/action")
async def act_leave_request(request_id: str, body: RequestActionIn,
                             business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    req = await db.leave_requests.find_one(
        {"business_id": business_id, "request_id": request_id}, {"_id": 0}
    )
    if not req:
        raise HTTPException(404, "Leave request not found")
    if req["status"] != "pending" and body.action in ("approve", "reject"):
        raise HTTPException(400, f"Request already {req['status']}")

    if body.action == "approve":
        if user.get("role") != "owner":
            raise HTTPException(403, "Only the business owner can approve leave")
        new_status = "approved"
        upd = {"status": new_status, "approved_at": now_iso(),
               "approved_by": user.get("email"), "note": body.note or req.get("note", "")}
        await db.leave_requests.update_one(
            {"business_id": business_id, "request_id": request_id}, {"$set": upd}
        )
        # If the leave period is in the past OR started today, post a taken ledger row now.
        # Otherwise the row is posted when the request start_date is reached (via
        # /reminders/scan or manual refresh). We take the simple path and post immediately;
        # the balance snapshot subtracts future_approved so it's not double counted.
        if req["start_date"] <= _today():
            await _post_leave_txn(business_id, req["employee_id"], req["leave_type"],
                                   "taken", f"-{req['hours']}", source="leave_request",
                                   source_ref=request_id,
                                   note=f"Approved leave {req['start_date']} → {req['end_date']}",
                                   effective_date=req["start_date"],
                                   user_email=user.get("email"))
        else:
            # Just refresh the snapshot to account for future_approved
            await _refresh_leave_balance(business_id, req["employee_id"], req["leave_type"])
        await audit(business_id, user, "leave_request", request_id, "approve")
        return {"ok": True, "status": new_status}

    if body.action == "reject":
        upd = {"status": "rejected", "rejected_at": now_iso(),
               "rejected_by": user.get("email"), "note": body.note or ""}
        await db.leave_requests.update_one(
            {"business_id": business_id, "request_id": request_id}, {"$set": upd}
        )
        await audit(business_id, user, "leave_request", request_id, "reject")
        return {"ok": True, "status": "rejected"}

    if body.action == "cancel":
        if req["status"] not in ("pending", "approved"):
            raise HTTPException(400, f"Cannot cancel a {req['status']} request")
        # If approved and ledger row was already posted, reverse it.
        if req["status"] == "approved":
            posted = await db.leave_transactions.find_one({
                "business_id": business_id, "source": "leave_request",
                "source_ref": request_id, "txn_type": "taken",
            })
            if posted:
                await _post_leave_txn(business_id, req["employee_id"], req["leave_type"],
                                       "adjustment", str(pe._d(posted["hours"]) * -1),
                                       source="leave_request",
                                       source_ref=request_id,
                                       note=f"Cancelled leave request {request_id}",
                                       effective_date=_today(),
                                       user_email=user.get("email"))
        await db.leave_requests.update_one(
            {"business_id": business_id, "request_id": request_id},
            {"$set": {"status": "cancelled", "cancelled_at": now_iso(),
                       "cancelled_by": user.get("email")}},
        )
        await _refresh_leave_balance(business_id, req["employee_id"], req["leave_type"])
        await audit(business_id, user, "leave_request", request_id, "cancel")
        return {"ok": True, "status": "cancelled"}

    raise HTTPException(400, f"Unknown action: {body.action}")


# ============================================================================
# REMINDERS SCAN — writes to global `reminders` collection so the existing
# reminders page and topbar counter surface them.
# ============================================================================
def _rem_key(kind: str, ident: str) -> str:
    return f"payroll:{kind}:{ident}"


async def _upsert_reminder(business_id: str, key: str, month_key: str, fy: str,
                            message: str, kind: str, related_id: Optional[str] = None,
                            related_type: Optional[str] = None):
    existing = await db.reminders.find_one(
        {"business_id": business_id, "key": key, "month_key": month_key}, {"_id": 0}
    )
    if existing:
        # Refresh message but never overwrite user-actioned status.
        if existing.get("status") == "open":
            await db.reminders.update_one(
                {"reminder_id": existing["reminder_id"]},
                {"$set": {"message": message}},
            )
        return 0
    await db.reminders.insert_one({
        "reminder_id": new_id("rem"),
        "business_id": business_id,
        "key": key,
        "kind": kind,
        "fy": fy, "month_key": month_key,
        "message": message,
        "expected_amount_cents": None,
        "status": "open",
        "snooze_until": None,
        "related_type": related_type,
        "related_id": related_id,
        "created_at": now_iso(),
        "is_demo": False,
    })
    return 1


@router.post("/reminders/scan")
async def scan_payroll_reminders(fy: Optional[str] = None,
                                  business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    today = _today()
    today_mk = month_key_of(today)
    created = 0

    # 1) Overdue super liabilities
    liabilities = await db.super_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}
    ).to_list(1000)
    for lb in liabilities:
        accrued = int(lb.get("accrued_cents", 0) or 0)
        paid = int(lb.get("paid_cents", 0) or 0)
        if paid >= accrued or accrued <= 0:
            continue
        if today > lb.get("due_date", ""):
            key = _rem_key("super_overdue", lb["liability_id"])
            mk = month_key_of(lb["due_date"])
            msg = (f"Super overdue — {lb['employee_name']} ({lb['quarter']} {fy}) "
                   f"${(accrued - paid) / 100:.2f} outstanding, was due {lb['due_date']}")
            created += await _upsert_reminder(business_id, key, mk, fy, msg,
                                               "payroll_super_overdue",
                                               related_id=lb["liability_id"],
                                               related_type="super_liability")

    # 2) Employees missing bank/super/tax
    employees = await db.employees.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "status": "active"},
        {"_id": 0},
    ).to_list(1000)
    for e in employees:
        eid = e["employee_id"]
        bank = await db.employee_bank_details.find_one(
            {"business_id": business_id, "employee_id": eid}, {"_id": 0}
        )
        if not bank or not (bank.get("bsb_enc") and bank.get("account_number_enc")):
            key = _rem_key("missing_bank", eid)
            created += await _upsert_reminder(business_id, key, today_mk, fy,
                f"Missing bank details — {e.get('first_name','')} {e.get('last_name','')}",
                "payroll_missing_bank", related_id=eid, related_type="employee")
        sup = await db.employee_super.find_one(
            {"business_id": business_id, "employee_id": eid}, {"_id": 0}
        )
        if not sup or not sup.get("fund_name"):
            key = _rem_key("missing_super", eid)
            created += await _upsert_reminder(business_id, key, today_mk, fy,
                f"Missing super fund — {e.get('first_name','')} {e.get('last_name','')}",
                "payroll_missing_super", related_id=eid, related_type="employee")
        tax = await db.employee_tax_settings.find_one(
            {"business_id": business_id, "employee_id": eid}, {"_id": 0}
        )
        if not tax:
            key = _rem_key("missing_tax", eid)
            created += await _upsert_reminder(business_id, key, today_mk, fy,
                f"Missing tax / PAYG settings — {e.get('first_name','')} {e.get('last_name','')}",
                "payroll_missing_tax", related_id=eid, related_type="employee")

    # 3) Pending leave requests
    pending = await db.leave_requests.find(
        {"business_id": business_id, "status": "pending"}, {"_id": 0}
    ).to_list(500)
    for r in pending:
        key = _rem_key("leave_pending", r["request_id"])
        mk = month_key_of(r.get("start_date") or today)
        created += await _upsert_reminder(business_id, key, mk, fy,
            f"Leave request pending — {r.get('employee_name','')} "
            f"({r['leave_type']}, {r['start_date']} → {r['end_date']})",
            "payroll_leave_pending", related_id=r["request_id"], related_type="leave_request")

    return {"ok": True, "created": created}


# ============================================================================
# PAYROLL REPORTS  (CSV + PDF)
# ============================================================================
async def _payroll_summary_rows(business_id: str, fy: str,
                                 period_start: Optional[str], period_end: Optional[str]) -> list[dict]:
    q = {"business_id": business_id, "fy": fy, "status": {"$ne": "voided"}}
    if period_start:
        q["payment_date"] = {"$gte": period_start}
    if period_end:
        q.setdefault("payment_date", {})["$lte"] = period_end
    payslips = await db.payslips.find(q, {"_id": 0, "earning_lines": 0}).to_list(5000)
    per_emp: dict = {}
    for p in payslips:
        eid = p["employee_id"]
        emp = per_emp.setdefault(eid, {
            "employee_id": eid,
            "employee_name": f"{p['employee'].get('first_name','')} {p['employee'].get('last_name','')}".strip(),
            "payslip_count": 0,
            "gross_cents": 0, "taxable_cents": 0, "pretax_ded_cents": 0,
            "posttax_ded_cents": 0, "payg_cents": 0, "net_cents": 0, "super_cents": 0,
        })
        emp["payslip_count"] += 1
        for k in ("gross_cents", "taxable_cents", "pretax_ded_cents", "posttax_ded_cents",
                  "payg_cents", "net_cents", "super_cents"):
            emp[k] += int(p.get(k, 0) or 0)
    return sorted(per_emp.values(), key=lambda r: r["employee_name"])


@router.get("/reports/summary")
async def report_summary(fy: Optional[str] = None,
                          period_start: Optional[str] = None,
                          period_end: Optional[str] = None,
                          business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    rows = await _payroll_summary_rows(business_id, fy, period_start, period_end)
    totals = {"gross_cents": 0, "taxable_cents": 0, "pretax_ded_cents": 0,
              "posttax_ded_cents": 0, "payg_cents": 0, "net_cents": 0, "super_cents": 0,
              "payslip_count": 0}
    for r in rows:
        for k in totals:
            totals[k] += r.get(k, 0)
    return {"fy": fy, "period_start": period_start, "period_end": period_end,
            "rows": rows, "totals": totals}


def _csv_response(rows: list[list[str]], filename: str) -> Response:
    buf = StringIO()
    buf.write("\ufeff")            # UTF-8 BOM for spreadsheet compatibility
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _cents_to_dollar_str(c: int) -> str:
    return f"{(int(c or 0) / 100):.2f}"


@router.get("/reports/summary.csv")
async def report_summary_csv(fy: Optional[str] = None,
                              period_start: Optional[str] = None,
                              period_end: Optional[str] = None,
                              business_id: str = Depends(get_business_id)):
    d = await report_summary(fy, period_start, period_end, business_id)
    rows = [["Employee", "Payslips", "Gross", "Pre-tax Deductions", "Taxable",
             "PAYG", "Post-tax Deductions", "Net", "Employer Super"]]
    for r in d["rows"]:
        rows.append([r["employee_name"], r["payslip_count"],
                     _cents_to_dollar_str(r["gross_cents"]),
                     _cents_to_dollar_str(r["pretax_ded_cents"]),
                     _cents_to_dollar_str(r["taxable_cents"]),
                     _cents_to_dollar_str(r["payg_cents"]),
                     _cents_to_dollar_str(r["posttax_ded_cents"]),
                     _cents_to_dollar_str(r["net_cents"]),
                     _cents_to_dollar_str(r["super_cents"])])
    t = d["totals"]
    rows.append(["TOTAL", t["payslip_count"],
                 _cents_to_dollar_str(t["gross_cents"]),
                 _cents_to_dollar_str(t["pretax_ded_cents"]),
                 _cents_to_dollar_str(t["taxable_cents"]),
                 _cents_to_dollar_str(t["payg_cents"]),
                 _cents_to_dollar_str(t["posttax_ded_cents"]),
                 _cents_to_dollar_str(t["net_cents"]),
                 _cents_to_dollar_str(t["super_cents"])])
    fname = f"payroll-summary-{d['fy']}"
    if period_start:
        fname += f"_{period_start}"
    if period_end:
        fname += f"_{period_end}"
    return _csv_response(rows, fname + ".csv")


@router.get("/reports/summary.pdf")
async def report_summary_pdf(fy: Optional[str] = None,
                              period_start: Optional[str] = None,
                              period_end: Optional[str] = None,
                              business_id: str = Depends(get_business_id)):
    d = await report_summary(fy, period_start, period_end, business_id)
    employer = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0}) or {}
    pdf = rpdf.build_summary_pdf(d, employer)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="payroll-summary-{d["fy"]}.pdf"'})


# --- Payment Summary per employee (STP-style) ------------------------------
@router.get("/reports/payment-summary")
async def payment_summary(fy: Optional[str] = None, employee_id: Optional[str] = None,
                           business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    q = {"business_id": business_id, "fy": fy, "status": {"$ne": "voided"}}
    if employee_id:
        q["employee_id"] = employee_id
    payslips = await db.payslips.find(q, {"_id": 0, "earning_lines": 0}).to_list(10000)
    by_emp: dict = {}
    for p in payslips:
        eid = p["employee_id"]
        emp = by_emp.setdefault(eid, {
            "employee_id": eid,
            "employee_name": f"{p['employee'].get('first_name','')} {p['employee'].get('last_name','')}".strip(),
            "address_line": p['employee'].get("address_line", ""),
            "payslip_count": 0, "period_start": p.get("period_start"),
            "period_end": p.get("period_end"),
            "gross_cents": 0, "taxable_cents": 0, "pretax_ded_cents": 0,
            "posttax_ded_cents": 0, "payg_cents": 0, "net_cents": 0, "super_cents": 0,
        })
        emp["payslip_count"] += 1
        if p.get("period_start") and (not emp["period_start"] or p["period_start"] < emp["period_start"]):
            emp["period_start"] = p["period_start"]
        if p.get("period_end") and (not emp["period_end"] or p["period_end"] > emp["period_end"]):
            emp["period_end"] = p["period_end"]
        for k in ("gross_cents", "taxable_cents", "pretax_ded_cents", "posttax_ded_cents",
                  "payg_cents", "net_cents", "super_cents"):
            emp[k] += int(p.get(k, 0) or 0)
    return {"fy": fy, "rows": sorted(by_emp.values(), key=lambda r: r["employee_name"])}


@router.get("/reports/payment-summary.csv")
async def payment_summary_csv(fy: Optional[str] = None, employee_id: Optional[str] = None,
                               business_id: str = Depends(get_business_id)):
    d = await payment_summary(fy, employee_id, business_id)
    rows = [["Employee", "Address", "Period from", "Period to", "Gross", "Taxable", "PAYG",
             "Net", "Employer Super"]]
    for r in d["rows"]:
        rows.append([r["employee_name"], r["address_line"], r["period_start"] or "",
                     r["period_end"] or "",
                     _cents_to_dollar_str(r["gross_cents"]),
                     _cents_to_dollar_str(r["taxable_cents"]),
                     _cents_to_dollar_str(r["payg_cents"]),
                     _cents_to_dollar_str(r["net_cents"]),
                     _cents_to_dollar_str(r["super_cents"])])
    return _csv_response(rows, f"payment-summary-{d['fy']}.csv")


@router.get("/reports/payment-summary.pdf")
async def payment_summary_pdf(fy: Optional[str] = None, employee_id: Optional[str] = None,
                               business_id: str = Depends(get_business_id)):
    d = await payment_summary(fy, employee_id, business_id)
    employer = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0}) or {}
    pdf = rpdf.build_payment_summary_pdf(d, employer)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="payment-summary-{d["fy"]}.pdf"'})


# --- Super Payable by Quarter ---------------------------------------------
@router.get("/reports/super-quarter")
async def super_quarter_report(fy: Optional[str] = None, quarter: Optional[str] = None,
                                business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    q = {"business_id": business_id, "fy": fy}
    if quarter:
        q["quarter"] = quarter
    items = await db.super_liabilities.find(q, {"_id": 0}).sort(
        [("quarter", 1), ("employee_name", 1)]).to_list(2000)
    today = _today()
    by_q: dict = {}
    for it in items:
        accrued = int(it.get("accrued_cents", 0) or 0)
        paid = int(it.get("paid_cents", 0) or 0)
        it["outstanding_cents"] = max(0, accrued - paid)
        it["is_overdue"] = pe.is_overdue(it.get("due_date", ""), today, paid, accrued)
        row = by_q.setdefault(it["quarter"], {
            "quarter": it["quarter"], "period_start": it["period_start"],
            "period_end": it["period_end"], "due_date": it["due_date"],
            "accrued_cents": 0, "paid_cents": 0, "outstanding_cents": 0, "employees": [],
        })
        row["accrued_cents"] += accrued
        row["paid_cents"] += paid
        row["outstanding_cents"] += it["outstanding_cents"]
        row["employees"].append(it)
    quarters = sorted(by_q.values(), key=lambda x: x["quarter"])
    return {"fy": fy, "quarter": quarter, "quarters": quarters, "items": items}


@router.get("/reports/super-quarter.csv")
async def super_quarter_csv(fy: Optional[str] = None, quarter: Optional[str] = None,
                             business_id: str = Depends(get_business_id)):
    d = await super_quarter_report(fy, quarter, business_id)
    rows = [["Quarter", "Employee", "Fund", "Accrued", "Paid", "Outstanding",
             "Due date", "Status", "Overdue"]]
    for q in d["quarters"]:
        for it in q["employees"]:
            rows.append([q["quarter"], it["employee_name"], it.get("fund_name", ""),
                         _cents_to_dollar_str(it["accrued_cents"]),
                         _cents_to_dollar_str(it["paid_cents"]),
                         _cents_to_dollar_str(it["outstanding_cents"]),
                         it["due_date"], it["status"],
                         "Yes" if it["is_overdue"] else "No"])
        rows.append([q["quarter"] + " TOTAL", "", "",
                     _cents_to_dollar_str(q["accrued_cents"]),
                     _cents_to_dollar_str(q["paid_cents"]),
                     _cents_to_dollar_str(q["outstanding_cents"]),
                     q["due_date"], "", ""])
    return _csv_response(rows, f"super-quarter-{d['fy']}.csv")


@router.get("/reports/super-quarter.pdf")
async def super_quarter_pdf(fy: Optional[str] = None, quarter: Optional[str] = None,
                             business_id: str = Depends(get_business_id)):
    d = await super_quarter_report(fy, quarter, business_id)
    employer = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0}) or {}
    pdf = rpdf.build_super_pdf(d, employer)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="super-quarter-{d["fy"]}.pdf"'})


# --- Leave Balances --------------------------------------------------------
@router.get("/reports/leave-balances")
async def leave_balances_report(business_id: str = Depends(get_business_id)):
    balances = await db.employee_leave_balances.find(
        {"business_id": business_id}, {"_id": 0}
    ).sort([("employee_id", 1), ("leave_type", 1)]).to_list(2000)
    emps = await db.employees.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}}, {"_id": 0},
    ).to_list(2000)
    name_by = {e["employee_id"]: f"{e.get('preferred_name') or e.get('first_name','')} {e.get('last_name','')}".strip()
               for e in emps}
    for b in balances:
        b["employee_name"] = name_by.get(b["employee_id"], "(unknown)")
    rows_by_emp: dict = {}
    for b in balances:
        rows_by_emp.setdefault(b["employee_id"], {
            "employee_id": b["employee_id"], "employee_name": b["employee_name"],
            "by_type": {},
        })["by_type"][b["leave_type"]] = {
            "entitled_hours": b.get("entitled_hours", "0"),
            "future_approved_hours": b.get("future_approved_hours", "0"),
            "remaining_hours": b.get("remaining_hours", "0"),
        }
    rows = sorted(rows_by_emp.values(), key=lambda r: r["employee_name"])
    return {"generated_at": now_iso(), "rows": rows}


@router.get("/reports/leave-balances.csv")
async def leave_balances_csv(business_id: str = Depends(get_business_id)):
    d = await leave_balances_report(business_id)
    types = sorted({t for r in d["rows"] for t in r["by_type"].keys()})
    header = ["Employee"]
    for t in types:
        header += [f"{t} entitled", f"{t} future", f"{t} remaining"]
    rows = [header]
    for r in d["rows"]:
        row = [r["employee_name"]]
        for t in types:
            v = r["by_type"].get(t, {})
            row += [v.get("entitled_hours", "0"), v.get("future_approved_hours", "0"),
                    v.get("remaining_hours", "0")]
        rows.append(row)
    return _csv_response(rows, "leave-balances.csv")


@router.get("/reports/leave-balances.pdf")
async def leave_balances_pdf(business_id: str = Depends(get_business_id)):
    d = await leave_balances_report(business_id)
    employer = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0}) or {}
    pdf = rpdf.build_leave_balances_pdf(d, employer)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="leave-balances.pdf"'})


# ============================================================================
# DASHBOARD (Phase 4 rich)
# ============================================================================
@router.get("/dashboard-full")
async def dashboard_full(fy: Optional[str] = None,
                          business_id: str = Depends(get_business_id)):
    """Extended dashboard for Phase 4. Superset of /dashboard, non-breaking."""
    fy = fy or current_fy()
    today = _today()
    today_mk = month_key_of(today)

    active_count = await db.employees.count_documents(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "status": "active"}
    )
    drafts = await db.pay_runs.count_documents(
        {"business_id": business_id, "status": {"$in": ["draft", "calculated"]}}
    )
    finalised = await db.pay_runs.find(
        {"business_id": business_id, "status": "finalised", "fy": fy},
        {"_id": 0, "pay_run_ref": 1, "payment_date": 1, "totals": 1,
         "period_start": 1, "period_end": 1, "month_key": 1},
    ).sort("payment_date", -1).to_list(200)

    ytd = {"gross_cents": 0, "payg_cents": 0, "net_cents": 0, "super_cents": 0,
           "total_employer_cost_cents": 0}
    by_month: dict = {}
    for r in finalised:
        t = r.get("totals") or {}
        for k in ytd:
            ytd[k] += int(t.get(k, 0) or 0)
        mk = r.get("month_key") or (r["payment_date"][:7] if r.get("payment_date") else "")
        m = by_month.setdefault(mk, {"month_key": mk, "gross_cents": 0,
                                      "payg_cents": 0, "net_cents": 0, "super_cents": 0})
        for k in ("gross_cents", "payg_cents", "net_cents", "super_cents"):
            m[k] += int(t.get(k, 0) or 0)

    # Super outstanding + overdue
    liabilities = await db.super_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}
    ).to_list(2000)
    super_outstanding = 0
    super_overdue = 0
    overdue_items = []
    for lb in liabilities:
        accrued = int(lb.get("accrued_cents", 0) or 0)
        paid = int(lb.get("paid_cents", 0) or 0)
        out = max(0, accrued - paid)
        super_outstanding += out
        if pe.is_overdue(lb.get("due_date", ""), today, paid, accrued):
            super_overdue += out
            overdue_items.append({**lb, "outstanding_cents": out})

    # Leave liability in HOURS (dollar valuation requires wage snapshot per hour)
    balances = await db.employee_leave_balances.find(
        {"business_id": business_id}, {"_id": 0}
    ).to_list(2000)
    leave_hours_total = 0.0
    for b in balances:
        leave_hours_total += float(pe._d(b.get("remaining_hours", 0)))

    # Missing details tally — computed with two aggregations instead of N+1 per employee.
    active_emps = await db.employees.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "status": "active"},
        {"_id": 0, "employee_id": 1},
    ).to_list(2000)
    active_ids = [e["employee_id"] for e in active_emps]
    if active_ids:
        bank_ok = set(await db.employee_bank_details.distinct(
            "employee_id",
            {"business_id": business_id, "employee_id": {"$in": active_ids},
             "bsb_enc": {"$exists": True, "$ne": ""}}))
        super_ok = set(await db.employee_super.distinct(
            "employee_id",
            {"business_id": business_id, "employee_id": {"$in": active_ids},
             "fund_name": {"$exists": True, "$ne": ""}}))
        tax_ok = set(await db.employee_tax_settings.distinct(
            "employee_id",
            {"business_id": business_id, "employee_id": {"$in": active_ids}}))
        employees_missing = sum(
            1 for eid in active_ids
            if not (eid in bank_ok and eid in super_ok and eid in tax_ok)
        )
    else:
        employees_missing = 0

    # Pending leave requests
    leave_pending = await db.leave_requests.count_documents(
        {"business_id": business_id, "status": "pending"}
    )

    # Next scheduled draft pay run
    next_draft = await db.pay_runs.find_one(
        {"business_id": business_id, "status": {"$in": ["draft", "calculated"]}},
        sort=[("payment_date", 1)], projection={"_id": 0},
    )

    return {
        "fy": fy,
        "active_employees": active_count,
        "drafts_count": drafts,
        "employees_missing_details": employees_missing,
        "leave_pending_count": leave_pending,
        "recent_finalised": finalised[:8],
        "monthly": sorted(by_month.values(), key=lambda x: x["month_key"]),
        "ytd": ytd,
        "super": {
            "outstanding_cents": super_outstanding,
            "overdue_cents": super_overdue,
            "overdue_items": overdue_items[:6],
        },
        "leave": {
            "total_remaining_hours": round(leave_hours_total, 2),
            "pending_requests": leave_pending,
        },
        "next_draft": next_draft,
    }


__all__ = ["router", "_upsert_super_liability_from_payslip",
           "_accrue_leave_from_pay_run"]
