"""Payroll pay-run routes (Phase 2).

Endpoints (all scoped by business_id, all require auth, no public URLs):

    POST   /api/payroll/pay-runs                    create draft
    GET    /api/payroll/pay-runs                    list (filtered by status/fy)
    GET    /api/payroll/pay-runs/{ref}              full run (header + employees + lines)
    POST   /api/payroll/pay-runs/{ref}/load         load eligible active employees + defaults
    PUT    /api/payroll/pay-runs/{ref}/employees/{eid}   edit one employee's lines/payg
    POST   /api/payroll/pay-runs/{ref}/calculate    recompute totals (idempotent)
    POST   /api/payroll/pay-runs/{ref}/finalise     freeze snapshot, immutable
    POST   /api/payroll/pay-runs/{ref}/void         status=voided (never delete)
    GET    /api/payroll/dashboard                   Phase-2 KPIs

Phase 2 explicitly does NOT write into the `transactions` collection.
That accounting integration lands in Phase 5.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user, get_business_id
from core import db, new_id, now_iso, audit, fy_of, month_key_of, current_fy
import payroll_calc as pc

router = APIRouter(prefix="/api/payroll", tags=["payroll-runs"])

STATUSES = {"draft", "calculated", "finalised", "voided"}
IMMUTABLE = {"finalised", "voided"}


# ---------------------------------------------------------------------------
# Reference generator: UD-PR-YYYY-NNNNNN
# ---------------------------------------------------------------------------
async def _next_run_ref(business_id: str) -> str:
    year = datetime.utcnow().year
    prefix = f"UD-PR-{year}-"
    last = await db.pay_runs.find_one(
        {"business_id": business_id, "pay_run_ref": {"$regex": f"^{prefix}"}},
        sort=[("pay_run_ref", -1)],
    )
    seq = 1
    if last and last.get("pay_run_ref"):
        try:
            seq = int(last["pay_run_ref"].split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:06d}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_run(business_id: str, pay_run_ref: str) -> dict:
    run = await db.pay_runs.find_one(
        {"business_id": business_id, "pay_run_ref": pay_run_ref}, {"_id": 0}
    )
    if not run:
        raise HTTPException(404, "Pay run not found")
    return run


def _require_editable(run: dict):
    if run.get("status") in IMMUTABLE:
        raise HTTPException(400, f"Pay run is {run['status']} and cannot be edited")


async def _current_pay_settings(business_id: str, employee_id: str, on_date: str) -> Optional[dict]:
    """Return the pay-settings row whose effective_from <= on_date."""
    doc = await db.employee_pay_settings.find_one(
        {"business_id": business_id, "employee_id": employee_id,
         "effective_from": {"$lte": on_date}},
        sort=[("effective_from", -1)], projection={"_id": 0},
    )
    return doc


# ---------------------------------------------------------------------------
# Create / list
# ---------------------------------------------------------------------------
class PayRunIn(BaseModel):
    period_start: str
    period_end: str
    payment_date: str
    pay_frequency: str = Field(default="fortnightly")
    notes: str = ""

    @field_validator("pay_frequency")
    @classmethod
    def _f(cls, v):
        if v not in {"weekly", "fortnightly", "monthly", "custom"}:
            raise ValueError("pay_frequency invalid")
        return v


@router.post("/pay-runs")
async def create_pay_run(body: PayRunIn, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    if body.period_end < body.period_start:
        raise HTTPException(422, "period_end must be on or after period_start")

    # Guard duplicates by (frequency + period_start + period_end + not voided)
    dup = await db.pay_runs.find_one({
        "business_id": business_id, "pay_frequency": body.pay_frequency,
        "period_start": body.period_start, "period_end": body.period_end,
        "status": {"$ne": "voided"},
    })
    if dup:
        raise HTTPException(400, f"A non-voided pay run for this period already exists ({dup['pay_run_ref']})")

    ref = await _next_run_ref(business_id)
    payment = body.payment_date
    doc = {
        "pay_run_id": new_id("pr"),
        "pay_run_ref": ref,
        "business_id": business_id,
        "period_start": body.period_start,
        "period_end": body.period_end,
        "payment_date": payment,
        "pay_frequency": body.pay_frequency,
        "status": "draft",
        "fy": fy_of(payment),
        "month_key": month_key_of(payment),
        "notes": body.notes,
        "totals": {"employee_count": 0, "gross_cents": 0, "taxable_cents": 0,
                    "payg_cents": 0, "pretax_ded_cents": 0, "posttax_ded_cents": 0,
                    "net_cents": 0, "super_cents": 0, "total_employer_cost_cents": 0},
        "created_at": now_iso(), "created_by": user.get("email"),
    }
    await db.pay_runs.insert_one(doc)
    await audit(business_id, user, "pay_run", ref, "create", after={"ref": ref})
    doc.pop("_id", None)
    return doc


@router.get("/pay-runs")
async def list_pay_runs(status: Optional[str] = None, fy: Optional[str] = None,
                        business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if status:
        q["status"] = status
    if fy:
        q["fy"] = fy
    items = await db.pay_runs.find(q, {"_id": 0}).sort("payment_date", -1).to_list(500)
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Load eligible employees into a draft
# ---------------------------------------------------------------------------
@router.post("/pay-runs/{ref}/load")
async def load_employees(ref: str, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    run = await _get_run(business_id, ref)
    _require_editable(run)

    # Wipe any previous draft rows for this run
    await db.pay_run_employees.delete_many({"business_id": business_id, "pay_run_ref": ref})
    await db.pay_run_lines.delete_many({"business_id": business_id, "pay_run_ref": ref})

    active = await db.employees.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "status": "active"},
        {"_id": 0},
    ).to_list(1000)

    included = []
    for emp in active:
        ps = await _current_pay_settings(business_id, emp["employee_id"], run["period_end"])
        if not ps:
            continue
        # Include only employees whose pay_frequency matches (unless run is custom)
        if run["pay_frequency"] not in ("custom",) and ps.get("pay_frequency") != run["pay_frequency"]:
            continue

        sup = await db.employee_super.find_one(
            {"business_id": business_id, "employee_id": emp["employee_id"]}, {"_id": 0}
        ) or {}
        tax = await db.employee_tax_settings.find_one(
            {"business_id": business_id, "employee_id": emp["employee_id"]}, {"_id": 0}
        ) or {}

        gross_default = pc.ordinary_gross_cents(ps)
        rate_cents = pc.to_cents(ps.get("base_hourly_rate"))
        hours_default = pc.suggested_hours_for_period(ps)
        sg_rate = str(sup.get("sg_rate") or "0.12")
        manual_payg = str(tax.get("manual_payg_override") or "0")

        # Build the default ORDINARY earnings line
        if ps.get("pay_basis") == "hourly":
            line = {
                "line_id": new_id("prl"),
                "pay_run_ref": ref, "business_id": business_id,
                "employee_id": emp["employee_id"],
                "pay_item_id": None,
                "code": "ORD", "label": "Ordinary Hours",
                "kind": "earning", "calc_type": "hourly",
                "hours_or_units": hours_default, "rate_cents": rate_cents,
                "base_rate_cents": rate_cents,
                "taxable": True, "super_liable": True,
                "deduction_category": None, "date": None,
                "amount_cents": pc.line_amount_cents("hourly", hours_default, rate_cents),
                "amount_cents_override": None,
            }
        else:
            line = {
                "line_id": new_id("prl"),
                "pay_run_ref": ref, "business_id": business_id,
                "employee_id": emp["employee_id"],
                "pay_item_id": None,
                "code": "ORD", "label": "Ordinary Earnings",
                "kind": "earning", "calc_type": "fixed",
                "hours_or_units": "0", "rate_cents": gross_default,
                "base_rate_cents": rate_cents or gross_default,
                "taxable": True, "super_liable": True,
                "deduction_category": None, "date": None,
                "amount_cents": gross_default,
                "amount_cents_override": None,
            }

        await db.pay_run_lines.insert_one(line)

        totals = pc.calculate_employee_pay(
            lines=[pc.LineIn(
                pay_item_id=None, code=line["code"], label=line["label"],
                kind=line["kind"], calc_type=line["calc_type"],
                hours_or_units=line["hours_or_units"], rate_cents=line["rate_cents"],
                base_rate_cents=line["base_rate_cents"],
                taxable=line["taxable"], super_liable=line["super_liable"],
                deduction_category=None, date=None,
                amount_cents_override=line["amount_cents_override"],
            )],
            sg_rate_decimal=sg_rate, manual_payg_dollars=manual_payg,
            base_rate_cents=rate_cents,
        )

        pre = {
            "pay_run_ref": ref, "business_id": business_id,
            "employee_id": emp["employee_id"],
            "employee_name": f"{emp.get('preferred_name') or emp.get('first_name','')} {emp.get('last_name','')}".strip(),
            "pay_basis": ps.get("pay_basis"),
            "pay_frequency": ps.get("pay_frequency"),
            "base_rate_cents": rate_cents,
            "sg_rate": sg_rate,
            "manual_payg_default": manual_payg,
            "payg_override_cents": None,
            **{k: getattr(totals, k) for k in (
                "gross_cents", "taxable_cents", "pretax_ded_cents", "posttax_ded_cents",
                "payg_cents", "net_cents", "superable_cents", "super_cents",
                "total_employer_cost_cents")},
            "created_at": now_iso(),
        }
        await db.pay_run_employees.insert_one(pre)
        included.append(emp["employee_id"])

    await _refresh_totals(business_id, ref)
    await audit(business_id, user, "pay_run", ref, "load", after={"count": len(included)})
    return {"ok": True, "included": included, "count": len(included)}


# ---------------------------------------------------------------------------
# Recalc a single employee's totals from their stored lines
# ---------------------------------------------------------------------------
class EmployeeEditIn(BaseModel):
    lines: List[dict] = Field(default_factory=list)   # {code,label,kind,calc_type,hours_or_units,rate_cents,base_rate_cents,taxable,super_liable,deduction_category,pay_item_id,date,amount_cents_override}
    payg_override_cents: Optional[int] = None
    sg_rate: Optional[str] = None


@router.put("/pay-runs/{ref}/employees/{employee_id}")
async def edit_employee_lines(ref: str, employee_id: str, body: EmployeeEditIn,
                               business_id: str = Depends(get_business_id),
                               user: dict = Depends(get_current_user)):
    run = await _get_run(business_id, ref)
    _require_editable(run)
    row = await db.pay_run_employees.find_one(
        {"business_id": business_id, "pay_run_ref": ref, "employee_id": employee_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(404, "Employee not in this pay run")

    # Validate lines
    for L in body.lines:
        if _d_neg(L.get("hours_or_units", "0")):
            raise HTTPException(422, "Negative hours are not allowed")
        if int(L.get("rate_cents") or 0) < 0:
            raise HTTPException(422, "Negative rates are not allowed")
        if L.get("kind") not in {"earning", "deduction", "leave"}:
            raise HTTPException(422, f"Invalid line kind {L.get('kind')!r}")

    # Replace stored lines atomically
    await db.pay_run_lines.delete_many(
        {"business_id": business_id, "pay_run_ref": ref, "employee_id": employee_id}
    )
    docs = []
    for L in body.lines:
        rate = int(L.get("rate_cents") or 0)
        base = int(L.get("base_rate_cents") or row.get("base_rate_cents") or 0)
        amount = (int(L["amount_cents_override"]) if L.get("amount_cents_override") is not None
                  else pc.line_amount_cents(
                      L.get("calc_type", "hourly"),
                      L.get("hours_or_units", "0"), rate, base))
        docs.append({
            "line_id": new_id("prl"),
            "pay_run_ref": ref, "business_id": business_id, "employee_id": employee_id,
            "pay_item_id": L.get("pay_item_id"),
            "code": L.get("code", ""), "label": L.get("label", ""),
            "kind": L["kind"], "calc_type": L.get("calc_type", "hourly"),
            "hours_or_units": str(L.get("hours_or_units", "0")),
            "rate_cents": rate, "base_rate_cents": base,
            "taxable": bool(L.get("taxable", True)),
            "super_liable": bool(L.get("super_liable", True)),
            "deduction_category": L.get("deduction_category"),
            "date": L.get("date"),
            "amount_cents_override": L.get("amount_cents_override"),
            "amount_cents": amount,
        })
    if docs:
        await db.pay_run_lines.insert_many(docs)

    sg_rate = body.sg_rate or row.get("sg_rate") or "0.12"
    totals = pc.calculate_employee_pay(
        lines=[pc.LineIn(
            pay_item_id=d.get("pay_item_id"), code=d["code"], label=d["label"],
            kind=d["kind"], calc_type=d["calc_type"],
            hours_or_units=d["hours_or_units"], rate_cents=d["rate_cents"],
            base_rate_cents=d.get("base_rate_cents") or row.get("base_rate_cents"),
            taxable=d["taxable"], super_liable=d["super_liable"],
            deduction_category=d.get("deduction_category"), date=d.get("date"),
            amount_cents_override=d.get("amount_cents_override"),
        ) for d in docs],
        sg_rate_decimal=sg_rate,
        manual_payg_dollars=row.get("manual_payg_default", "0"),
        payg_override_cents=body.payg_override_cents,
    )
    upd = {
        "sg_rate": sg_rate,
        "payg_override_cents": body.payg_override_cents,
        **{k: getattr(totals, k) for k in (
            "gross_cents", "taxable_cents", "pretax_ded_cents", "posttax_ded_cents",
            "payg_cents", "net_cents", "superable_cents", "super_cents",
            "total_employer_cost_cents")},
        "updated_at": now_iso(),
    }
    await db.pay_run_employees.update_one(
        {"business_id": business_id, "pay_run_ref": ref, "employee_id": employee_id},
        {"$set": upd},
    )
    await _refresh_totals(business_id, ref)
    await audit(business_id, user, "pay_run_employee",
                f"{ref}:{employee_id}", "recalc",
                after={"gross_cents": totals.gross_cents, "net_cents": totals.net_cents})
    # Remove _id from docs before returning
    for d in docs:
        d.pop("_id", None)
    return {"employee_id": employee_id, **upd, "lines": docs}


def _d_neg(v) -> bool:
    try:
        from decimal import Decimal
        return Decimal(str(v or "0")) < 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Recalculate totals cache from stored per-employee rows
# ---------------------------------------------------------------------------
async def _refresh_totals(business_id: str, ref: str):
    rows = await db.pay_run_employees.find(
        {"business_id": business_id, "pay_run_ref": ref}, {"_id": 0}
    ).to_list(1000)
    agg = {"employee_count": len(rows)}
    for k in ("gross_cents", "taxable_cents", "payg_cents", "pretax_ded_cents",
              "posttax_ded_cents", "net_cents", "super_cents", "total_employer_cost_cents"):
        agg[k] = sum(r.get(k, 0) for r in rows)
    await db.pay_runs.update_one(
        {"business_id": business_id, "pay_run_ref": ref},
        {"$set": {"totals": agg, "updated_at": now_iso()}},
    )
    return agg


@router.post("/pay-runs/{ref}/calculate")
async def recalculate(ref: str, business_id: str = Depends(get_business_id)):
    await _get_run(business_id, ref)
    return await _refresh_totals(business_id, ref)


# ---------------------------------------------------------------------------
# Full run detail
# ---------------------------------------------------------------------------
@router.get("/pay-runs/{ref}")
async def get_run_detail(ref: str, business_id: str = Depends(get_business_id)):
    run = await _get_run(business_id, ref)
    rows = await db.pay_run_employees.find(
        {"business_id": business_id, "pay_run_ref": ref}, {"_id": 0}
    ).sort("employee_name", 1).to_list(1000)
    lines = await db.pay_run_lines.find(
        {"business_id": business_id, "pay_run_ref": ref}, {"_id": 0}
    ).to_list(5000)
    by_emp: dict = {}
    for L in lines:
        by_emp.setdefault(L["employee_id"], []).append(L)
    for r in rows:
        r["lines"] = by_emp.get(r["employee_id"], [])
    return {**run, "employees": rows}


# ---------------------------------------------------------------------------
# Finalise / void
# ---------------------------------------------------------------------------
@router.post("/pay-runs/{ref}/finalise")
async def finalise(ref: str, business_id: str = Depends(get_business_id),
                    user: dict = Depends(get_current_user)):
    run = await _get_run(business_id, ref)
    if run["status"] in IMMUTABLE:
        raise HTTPException(400, f"Pay run is already {run['status']}")
    totals = await _refresh_totals(business_id, ref)
    if totals["employee_count"] == 0:
        raise HTTPException(400, "Cannot finalise an empty pay run")
    for k in ("gross_cents",):
        if totals.get(k, 0) < 0:
            raise HTTPException(400, "Cannot finalise a pay run with negative gross")

    await db.pay_runs.update_one(
        {"business_id": business_id, "pay_run_ref": ref},
        {"$set": {"status": "finalised", "finalised_at": now_iso(),
                   "finalised_by": user.get("email")}},
    )
    await audit(business_id, user, "pay_run", ref, "finalise", after=totals)
    return {"ok": True, "status": "finalised", "totals": totals}


class VoidIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("/pay-runs/{ref}/void")
async def void_run(ref: str, body: VoidIn,
                    business_id: str = Depends(get_business_id),
                    user: dict = Depends(get_current_user)):
    run = await _get_run(business_id, ref)
    if run["status"] == "voided":
        raise HTTPException(400, "Pay run is already voided")
    await db.pay_runs.update_one(
        {"business_id": business_id, "pay_run_ref": ref},
        {"$set": {"status": "voided", "voided_at": now_iso(),
                   "voided_by": user.get("email"), "void_reason": body.reason}},
    )
    await audit(business_id, user, "pay_run", ref, "void", after={"reason": body.reason})
    return {"ok": True, "status": "voided"}


# ---------------------------------------------------------------------------
# Dashboard KPIs (Phase 2 subset)
# ---------------------------------------------------------------------------
@router.get("/dashboard")
async def payroll_dashboard(fy: Optional[str] = None,
                            business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    active_count = await db.employees.count_documents(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "status": "active"}
    )
    drafts = await db.pay_runs.count_documents(
        {"business_id": business_id, "status": {"$in": ["draft", "calculated"]}}
    )
    finalised = await db.pay_runs.find(
        {"business_id": business_id, "status": "finalised", "fy": fy},
        {"_id": 0, "pay_run_ref": 1, "payment_date": 1, "totals": 1, "period_start": 1, "period_end": 1},
    ).sort("payment_date", -1).to_list(20)
    ytd = {"gross_cents": 0, "payg_cents": 0, "net_cents": 0, "super_cents": 0,
           "total_employer_cost_cents": 0}
    for r in finalised:
        t = r.get("totals") or {}
        for k in ytd:
            ytd[k] += int(t.get(k, 0) or 0)
    return {
        "fy": fy,
        "active_employees": active_count,
        "drafts_count": drafts,
        "recent_finalised": finalised[:8],
        "ytd": ytd,
        "payg_status": pc.PAYG_STATUS_NOTE,
    }


__all__ = ["router"]
