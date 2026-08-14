"""Payroll accounting integration (Phase 5 — final integration pass).

CRITICAL RULES ENFORCED HERE (see problem statement):
    * A finalised, non-voided Pay Run is the source of truth for payroll
      accounting. All posting is IDEMPOTENT via (business_id, pay_run_ref, kind).
    * GROSS wages expense recognised EXACTLY ONCE at finalisation.
    * EMPLOYER SUPER expense recognised EXACTLY ONCE at finalisation.
    * PAYG withholding is NOT an expense — it is a liability.
    * NET wages payment is NOT an expense — it is a cash outflow that closes
      a payable. No P&L impact at payment time.
    * SUPER payment is NOT an expense — Phase 4 already tracks liabilities.
      Payment is a cash outflow only.
    * NO GST on any payroll accounting line.
    * Void reversal soft-deletes the posted transactions and voids
      associated liabilities. History is preserved.
    * All queries scoped by business_id (multi-tenant isolation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user, get_business_id
from core import db, new_id, now_iso, audit, fy_of, month_key_of, current_fy

router = APIRouter(prefix="/api/payroll", tags=["payroll-accounting"])


# ---- Category helpers -------------------------------------------------
WAGES_CAT_NAME = "Wages & Salaries"
SUPER_CAT_NAME = "Employer Superannuation"


async def _ensure_category(business_id: str, name: str) -> dict:
    """Idempotently ensure a Payroll parent + named subcategory exists.
    Returns the SUB category document (used on posted expense lines)."""
    parent = await db.categories.find_one(
        {"business_id": business_id, "name": "Payroll", "parent_id": None},
        {"_id": 0},
    )
    if not parent:
        parent = {
            "category_id": new_id("cat"),
            "business_id": business_id,
            "name": "Payroll",
            "parent_id": None,
            "kind": "expense",
            "sort": 900,
            "is_deleted": False,
            "is_system": True,
            "created_at": now_iso(),
        }
        await db.categories.insert_one(parent)
    sub = await db.categories.find_one(
        {"business_id": business_id, "name": name, "parent_id": parent["category_id"]},
        {"_id": 0},
    )
    if not sub:
        sub = {
            "category_id": new_id("cat"),
            "business_id": business_id,
            "name": name,
            "parent_id": parent["category_id"],
            "kind": "expense",
            "sort": 901 if name == WAGES_CAT_NAME else 902,
            "is_deleted": False,
            "is_system": True,
            "created_at": now_iso(),
        }
        await db.categories.insert_one(sub)
    return {"parent": parent, "sub": sub}


# ---- Posting on finalise ---------------------------------------------
async def _idempotent_expense_txn(business_id: str, pay_run_ref: str, kind: str,
                                    date: str, amount_cents: int, description: str,
                                    parent_cat: dict, sub_cat: dict, user_email: str):
    """Insert (or return existing) a payroll expense transaction.
    Idempotency key: (business_id, external_source='payroll', payroll_kind=kind, pay_run_ref)."""
    if amount_cents <= 0:
        return None
    existing = await db.transactions.find_one({
        "business_id": business_id,
        "external_source": "payroll",
        "payroll_kind": kind,
        "pay_run_ref": pay_run_ref,
    }, {"_id": 0})
    if existing:
        return existing
    doc = {
        "txn_id": new_id("txn"),
        "business_id": business_id,
        "txn_type": "expense",
        "date": date, "fy": fy_of(date), "month_key": month_key_of(date),
        "category_id": sub_cat["category_id"], "category_name": parent_cat["name"],
        "subcategory_id": sub_cat["category_id"], "subcategory_name": sub_cat["name"],
        "supplier_id": None, "supplier_name": None, "account_id": None, "account_name": None,
        "description": description,
        "amount_ex_cents": int(amount_cents),
        "gst_cents": 0,
        "amount_inc_cents": int(amount_cents),
        "gst_treatment": "no_gst",
        "gst_rate": None,
        "reference": pay_run_ref,
        "notes": f"System-posted at pay run finalise ({pay_run_ref})",
        "tags": ["payroll"],
        "recurring_template_id": None,
        "receipt_document_ids": [],
        "needs_review": False,
        "ask_accountant": False,
        "accountant_note": "",
        "reconcile_status": "unreconciled",
        "sale": None, "refund": None, "ad_metrics": None, "items": [],
        # Payroll metadata — critical flags
        "external_source": "payroll",
        "external_id": f"{pay_run_ref}:{kind}",
        "payroll_kind": kind,
        "pay_run_ref": pay_run_ref,
        "payroll_accrual": True,       # Cash Flow excludes accrual-only expenses
        "is_deleted": False, "is_demo": False,
        "created_at": now_iso(), "created_by": user_email,
    }
    await db.transactions.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def post_payroll_accounting_for_run(business_id: str, pay_run_ref: str,
                                            user_email: str = "") -> dict:
    """Called by the pay-run finalise route AFTER payslips are created and after
    Phase-4 super/leave hooks. Fully idempotent."""
    run = await db.pay_runs.find_one(
        {"business_id": business_id, "pay_run_ref": pay_run_ref}, {"_id": 0}
    )
    if not run:
        raise HTTPException(404, "Pay run not found")
    if run.get("status") != "finalised":
        raise HTTPException(409, "Only finalised pay runs may be posted to accounting")
    totals = run.get("totals") or {}
    gross = int(totals.get("gross_cents", 0) or 0)
    sup = int(totals.get("super_cents", 0) or 0)
    payg = int(totals.get("payg_cents", 0) or 0)
    net = int(totals.get("net_cents", 0) or 0)
    payment_date = run.get("payment_date")

    cats = await _ensure_category(business_id, WAGES_CAT_NAME)
    wages_cat_pair = cats
    wages_txn = await _idempotent_expense_txn(
        business_id, pay_run_ref, "wages_expense", payment_date, gross,
        f"Gross wages — pay run {pay_run_ref}",
        cats["parent"], cats["sub"], user_email,
    )
    cats_sup = await _ensure_category(business_id, SUPER_CAT_NAME)
    super_txn = await _idempotent_expense_txn(
        business_id, pay_run_ref, "super_expense", payment_date, sup,
        f"Employer superannuation — pay run {pay_run_ref}",
        cats_sup["parent"], cats_sup["sub"], user_email,
    )

    # Wages payable (net cash owed to employees)
    if net > 0:
        wp_key = {"business_id": business_id, "pay_run_ref": pay_run_ref}
        exists = await db.wages_payables.find_one(wp_key, {"_id": 0})
        if not exists:
            await db.wages_payables.insert_one({
                "payable_id": new_id("wpayb"),
                "business_id": business_id,
                "pay_run_ref": pay_run_ref,
                "fy": run.get("fy"),
                "month_key": run.get("month_key"),
                "period_start": run.get("period_start"),
                "period_end": run.get("period_end"),
                "payment_date": payment_date,
                "net_cents": net,
                "paid_cents": 0,
                "status": "outstanding",
                "payment_reference": "",
                "payments": [],
                "created_at": now_iso(),
                "created_by": user_email,
            })

    # PAYG liability
    if payg > 0:
        pg_key = {"business_id": business_id, "pay_run_ref": pay_run_ref}
        exists = await db.payg_liabilities.find_one(pg_key, {"_id": 0})
        if not exists:
            await db.payg_liabilities.insert_one({
                "liability_id": new_id("payglia"),
                "business_id": business_id,
                "pay_run_ref": pay_run_ref,
                "fy": run.get("fy"),
                "month_key": run.get("month_key"),
                "period_start": run.get("period_start"),
                "period_end": run.get("period_end"),
                "payment_date": payment_date,
                "payg_cents": payg,
                "paid_cents": 0,
                "status": "outstanding",   # outstanding | partial | paid | needs_review | voided
                "payment_reference": "",
                "payments": [],
                "created_at": now_iso(),
                "created_by": user_email,
            })

    # Log posting (audit trail — separate from `audit_log`)
    await db.payroll_postings.update_one(
        {"business_id": business_id, "pay_run_ref": pay_run_ref},
        {"$set": {
            "posting_id": new_id("post"),
            "business_id": business_id,
            "pay_run_ref": pay_run_ref,
            "kind": "finalise",
            "wages_txn_id": (wages_txn or {}).get("txn_id"),
            "super_txn_id": (super_txn or {}).get("txn_id"),
            "gross_cents": gross, "super_cents": sup, "payg_cents": payg, "net_cents": net,
            "posted_at": now_iso(), "posted_by": user_email,
            "is_reversed": False,
        }}, upsert=True,
    )
    return {
        "wages_txn_id": (wages_txn or {}).get("txn_id"),
        "super_txn_id": (super_txn or {}).get("txn_id"),
        "gross_cents": gross, "super_cents": sup, "payg_cents": payg, "net_cents": net,
    }


async def reverse_payroll_accounting_for_run(business_id: str, pay_run_ref: str,
                                              user_email: str = "") -> dict:
    """Called by the pay-run VOID route. Soft-deletes payroll transactions,
    marks liabilities voided. History (payslips + payroll_postings) preserved."""
    await db.transactions.update_many(
        {"business_id": business_id, "external_source": "payroll",
         "pay_run_ref": pay_run_ref},
        {"$set": {"is_deleted": True, "voided_at": now_iso(), "voided_by": user_email}},
    )
    await db.wages_payables.update_many(
        {"business_id": business_id, "pay_run_ref": pay_run_ref,
         "status": {"$ne": "voided"}},
        {"$set": {"status": "voided", "voided_at": now_iso(), "voided_by": user_email}},
    )
    await db.payg_liabilities.update_many(
        {"business_id": business_id, "pay_run_ref": pay_run_ref,
         "status": {"$ne": "voided"}},
        {"$set": {"status": "voided", "voided_at": now_iso(), "voided_by": user_email}},
    )
    # NOTE: super_liabilities are quarter-scoped and may aggregate multiple pay
    # runs; we cannot blanket-void a quarter. Instead we deduct this run's
    # contribution from accrued_cents so overdue/outstanding recalculates cleanly.
    slips = await db.payslips.find(
        {"business_id": business_id, "pay_run_ref": pay_run_ref}, {"_id": 0}
    ).to_list(1000)
    for s in slips:
        s_cents = int(s.get("super_cents", 0) or 0)
        if s_cents <= 0:
            continue
        # Find the quarter row this payslip contributed to and remove it.
        row = await db.super_liabilities.find_one({
            "business_id": business_id, "employee_id": s["employee_id"],
            "contributing_payslip_refs": s["payslip_ref"],
        }, {"_id": 0})
        if row:
            new_accrued = max(0, int(row.get("accrued_cents", 0) or 0) - s_cents)
            new_status = "paid" if int(row.get("paid_cents", 0) or 0) >= new_accrued and new_accrued > 0 else \
                          ("accrued" if int(row.get("paid_cents", 0) or 0) == 0 else "partial")
            if new_accrued == 0 and int(row.get("paid_cents", 0) or 0) == 0:
                new_status = "voided"
            await db.super_liabilities.update_one(
                {"liability_id": row["liability_id"]},
                {"$set": {"accrued_cents": new_accrued, "status": new_status,
                          "updated_at": now_iso()},
                 "$pull": {"contributing_payslip_refs": s["payslip_ref"]}},
            )
    await db.payroll_postings.update_one(
        {"business_id": business_id, "pay_run_ref": pay_run_ref},
        {"$set": {"is_reversed": True, "reversed_at": now_iso(),
                   "reversed_by": user_email}},
    )
    return {"reversed": True, "pay_run_ref": pay_run_ref}


# ============================================================================
# Wages Payable — read + mark paid
# ============================================================================
@router.get("/wages-payables")
async def list_wages_payables(fy: Optional[str] = None, status: Optional[str] = None,
                               business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if fy:
        q["fy"] = fy
    if status and status != "all":
        q["status"] = status
    items = await db.wages_payables.find(q, {"_id": 0}).sort(
        [("payment_date", 1)]).to_list(1000)
    total_out = sum(max(0, int(i.get("net_cents", 0)) - int(i.get("paid_cents", 0))) for i in items if i.get("status") != "voided")
    return {"items": items, "total": len(items), "totals": {"outstanding_cents": total_out}}


class PayIn(BaseModel):
    paid_cents: int = Field(ge=0)
    payment_date: str
    payment_reference: str = ""
    payment_note: str = ""
    account_id: Optional[str] = None


@router.post("/wages-payables/{payable_id}/pay")
async def pay_wages_payable(payable_id: str, body: PayIn,
                             business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the business owner can record wage payments")
    row = await db.wages_payables.find_one(
        {"business_id": business_id, "payable_id": payable_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(404, "Wages payable not found")
    if row.get("status") == "voided":
        raise HTTPException(400, "Cannot pay a voided payable")
    already = int(row.get("paid_cents", 0) or 0)
    new_total = already + int(body.paid_cents)
    net = int(row["net_cents"])
    if new_total > net:
        raise HTTPException(422, f"Payment exceeds outstanding "
                                  f"(${(net - already) / 100:.2f})")
    status = "paid" if new_total >= net else ("partial" if new_total > 0 else "outstanding")
    payments = row.get("payments") or []
    payments.append({
        "amount_cents": int(body.paid_cents),
        "payment_date": body.payment_date,
        "reference": body.payment_reference,
        "note": body.payment_note,
        "account_id": body.account_id,
        "recorded_at": now_iso(),
        "recorded_by": user.get("email"),
    })
    await db.wages_payables.update_one(
        {"business_id": business_id, "payable_id": payable_id},
        {"$set": {"paid_cents": new_total, "status": status,
                   "payment_reference": body.payment_reference or row.get("payment_reference", ""),
                   "payments": payments, "updated_at": now_iso(),
                   "updated_by": user.get("email"),
                   "payment_date_actual": body.payment_date}},
    )
    await audit(business_id, user, "wages_payable", payable_id, "pay",
                after={"paid_cents": new_total, "status": status})
    return {"ok": True, "status": status, "paid_cents": new_total,
            "outstanding_cents": max(0, net - new_total)}


# ============================================================================
# PAYG liability — read + mark paid
# ============================================================================
@router.get("/payg-liabilities")
async def list_payg_liabilities(fy: Optional[str] = None, status: Optional[str] = None,
                                 business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if fy:
        q["fy"] = fy
    if status and status != "all":
        q["status"] = status
    items = await db.payg_liabilities.find(q, {"_id": 0}).sort(
        [("payment_date", 1)]).to_list(1000)
    outstanding = sum(max(0, int(i.get("payg_cents", 0)) - int(i.get("paid_cents", 0)))
                      for i in items if i.get("status") != "voided")
    return {"items": items, "total": len(items),
            "totals": {"outstanding_cents": outstanding}}


@router.post("/payg-liabilities/{liability_id}/pay")
async def pay_payg_liability(liability_id: str, body: PayIn,
                              business_id: str = Depends(get_business_id),
                              user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the business owner can record PAYG remittance")
    row = await db.payg_liabilities.find_one(
        {"business_id": business_id, "liability_id": liability_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(404, "PAYG liability not found")
    if row.get("status") == "voided":
        raise HTTPException(400, "Cannot pay a voided liability")
    already = int(row.get("paid_cents", 0) or 0)
    new_total = already + int(body.paid_cents)
    payg = int(row["payg_cents"])
    if new_total > payg:
        raise HTTPException(422, f"Payment exceeds outstanding "
                                  f"(${(payg - already) / 100:.2f})")
    status = "paid" if new_total >= payg else ("partial" if new_total > 0 else "outstanding")
    payments = row.get("payments") or []
    payments.append({
        "amount_cents": int(body.paid_cents),
        "payment_date": body.payment_date,
        "reference": body.payment_reference,
        "note": body.payment_note,
        "account_id": body.account_id,
        "recorded_at": now_iso(),
        "recorded_by": user.get("email"),
    })
    await db.payg_liabilities.update_one(
        {"business_id": business_id, "liability_id": liability_id},
        {"$set": {"paid_cents": new_total, "status": status,
                   "payment_reference": body.payment_reference or row.get("payment_reference", ""),
                   "payments": payments, "updated_at": now_iso(),
                   "updated_by": user.get("email"),
                   "payment_date_actual": body.payment_date}},
    )
    await audit(business_id, user, "payg_liability", liability_id, "pay",
                after={"paid_cents": new_total, "status": status})
    return {"ok": True, "status": status, "paid_cents": new_total,
            "outstanding_cents": max(0, payg - new_total)}


# ============================================================================
# Payroll liabilities summary + postings audit
# ============================================================================
@router.get("/liabilities-summary")
async def liabilities_summary(fy: Optional[str] = None,
                               business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    q = {"business_id": business_id, "fy": fy, "status": {"$ne": "voided"}}
    wages = await db.wages_payables.find(q, {"_id": 0}).to_list(2000)
    payg = await db.payg_liabilities.find(q, {"_id": 0}).to_list(2000)
    sup = await db.super_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}).to_list(2000)

    wages_out = sum(max(0, int(w["net_cents"]) - int(w.get("paid_cents", 0))) for w in wages)
    payg_out = sum(max(0, int(p["payg_cents"]) - int(p.get("paid_cents", 0))) for p in payg)
    sup_out = sum(max(0, int(s.get("accrued_cents", 0)) - int(s.get("paid_cents", 0)))
                   for s in sup)
    return {
        "fy": fy,
        "wages_outstanding_cents": wages_out,
        "payg_outstanding_cents": payg_out,
        "super_outstanding_cents": sup_out,
        "total_outstanding_cents": wages_out + payg_out + sup_out,
        "counts": {"wages": len(wages), "payg": len(payg), "super": len(sup)},
    }


@router.get("/postings")
async def list_postings(fy: Optional[str] = None,
                         business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if fy:
        # postings are looked up via pay_run_ref → filter via associated pay_runs
        runs = await db.pay_runs.distinct("pay_run_ref",
                                          {"business_id": business_id, "fy": fy})
        q["pay_run_ref"] = {"$in": runs}
    items = await db.payroll_postings.find(q, {"_id": 0}).sort(
        [("posted_at", -1)]).to_list(1000)
    return {"items": items, "total": len(items)}


@router.post("/pay-runs/{pay_run_ref}/post-accounting")
async def post_accounting_for_run(pay_run_ref: str,
                                    business_id: str = Depends(get_business_id),
                                    user: dict = Depends(get_current_user)):
    """Idempotent — safe to re-run. Used to backfill accounting for
    pre-Phase-5 finalised pay runs."""
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the business owner may post accounting")
    return await post_payroll_accounting_for_run(business_id, pay_run_ref,
                                                    user.get("email", ""))


__all__ = [
    "router", "post_payroll_accounting_for_run",
    "reverse_payroll_accounting_for_run",
]
