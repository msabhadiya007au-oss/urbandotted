"""Payroll — Phase 1 endpoints.

Scope:
    - Employer profile  : Settings > Payroll > Employer Details
    - Employees CRUD    : identity + employment + pay settings + super + tax + leave
    - Bank details      : owner-only, encrypted at rest, masked in normal reads
    - Payroll settings sub-resources (pay items, deductions, leave types) — CRUD only

NOT in Phase 1 (later phases):
    - Pay runs / calculations / PDFs
    - Accounting integration
    - Payroll dashboard KPI / reports
    - STP / email

All writes are scoped by business_id. All routes require the standard auth
dependency. Endpoints that expose PII (bank, tax) additionally require `owner`
role. No public URLs — everything is under `/api/payroll/*` behind auth.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator

from auth import get_current_user, get_business_id
from core import db, new_id, now_iso, audit
import payroll_crypto as pc

router = APIRouter(prefix="/api/payroll", tags=["payroll"])


# ============================================================================
# Helpers
# ============================================================================
def _require_owner(user: dict):
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can access this resource")


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def _iso_or_none(v):
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return str(v)[:10]


PAY_BASIS = {"hourly", "annual_salary", "monthly_salary", "fixed_pay", "custom"}
PAY_FREQ = {"weekly", "fortnightly", "monthly", "custom"}
EMP_STATUS = {"active", "on_leave", "terminated", "archived"}
EMP_TYPE = {"full_time", "part_time", "casual", "contractor_other"}


# ============================================================================
# Employer profile (payroll_settings collection, 1 doc per business)
# ============================================================================
class EmployerIn(BaseModel):
    legal_business_name: str = Field(min_length=1, max_length=200)
    trading_name: str = ""
    abn: str = ""
    business_address: str = ""
    suburb: str = ""
    state: str = ""
    postcode: str = ""
    country: str = "Australia"
    business_phone: str = ""
    payroll_email: str = ""
    business_email: str = ""
    logo_document_id: Optional[str] = None
    default_currency: str = "AUD"
    default_timezone: str = "Australia/Adelaide"
    default_pay_frequency: str = "fortnightly"
    default_super_rate: str = "0.12"  # decimal fraction — 12% SG for FY2026-27
    default_payment_method: str = "bank_transfer"
    default_bank_account_ref: str = ""

    @field_validator("default_pay_frequency")
    @classmethod
    def _f(cls, v):
        if v not in PAY_FREQ:
            raise ValueError(f"pay_frequency must be one of {sorted(PAY_FREQ)}")
        return v


@router.get("/employer")
async def get_employer(business_id: str = Depends(get_business_id)):
    doc = await db.payroll_settings.find_one({"business_id": business_id})
    return _clean(doc) or {}


@router.put("/employer")
async def put_employer(body: EmployerIn, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    _require_owner(user)
    now = now_iso()
    prev = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0})
    payload = {**body.model_dump(), "business_id": business_id, "updated_at": now}
    if not prev:
        payload["created_at"] = now
    await db.payroll_settings.update_one(
        {"business_id": business_id}, {"$set": payload}, upsert=True
    )
    await audit(business_id, user, "payroll_employer", business_id, "update",
                before=prev, after=payload)
    return payload


# ============================================================================
# Employees CRUD
# ============================================================================
class EmployeeIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    middle_name: str = ""
    last_name: str = Field(min_length=1, max_length=80)
    preferred_name: str = ""
    dob: Optional[str] = None
    email: Optional[EmailStr] = None
    work_email: Optional[str] = ""
    mobile: str = ""
    alt_phone: str = ""
    # Residential
    address: str = ""
    address_line_2: str = ""
    suburb: str = ""
    state: str = ""
    postcode: str = ""
    country: str = "Australia"
    # Postal — if same_as_residential the below are ignored on read
    postal_same_as_residential: bool = True
    postal_address: str = ""
    postal_address_line_2: str = ""
    postal_suburb: str = ""
    postal_state: str = ""
    postal_postcode: str = ""
    postal_country: str = "Australia"
    # Emergency contact
    emergency_contact_name: str = ""
    emergency_contact_relationship: str = ""
    emergency_contact_mobile: str = ""
    emergency_contact_alt_phone: str = ""
    # Employment
    employment_start_date: Optional[str] = None
    employment_end_date: Optional[str] = None
    probation_end_date: Optional[str] = None
    status: str = "active"
    employment_type: str = "full_time"
    job_title: str = ""
    department: str = ""
    location: str = ""
    manager: str = ""
    award: str = ""
    classification: str = ""
    # Ordinary working arrangement (independent of pay-settings history)
    std_hours_per_day: str = "0"
    std_hours_per_week: str = "0"
    std_hours_per_fortnight: str = "0"
    std_hours_per_month: str = "0"
    std_working_days: str = "0"
    # Optional per-day pattern (Mon..Sun); zero if not tracked
    pattern_mon_hours: str = "0"
    pattern_tue_hours: str = "0"
    pattern_wed_hours: str = "0"
    pattern_thu_hours: str = "0"
    pattern_fri_hours: str = "0"
    pattern_sat_hours: str = "0"
    pattern_sun_hours: str = "0"
    # Optional profile photo (id of an already-uploaded document)
    photo_document_id: Optional[str] = None
    notes: str = ""

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v not in EMP_STATUS:
            raise ValueError(f"status must be one of {sorted(EMP_STATUS)}")
        return v

    @field_validator("employment_type")
    @classmethod
    def _t(cls, v):
        if v not in EMP_TYPE:
            raise ValueError(f"employment_type must be one of {sorted(EMP_TYPE)}")
        return v


@router.get("/employees")
async def list_employees(status: Optional[str] = None, q: Optional[str] = None,
                          include_terminated: bool = False,
                          business_id: str = Depends(get_business_id)):
    query: dict = {"business_id": business_id, "is_deleted": {"$ne": True}}
    if status and status != "all":
        query["status"] = status
    elif not include_terminated:
        # Default listing hides archived; terminated stays visible unless explicitly filtered
        query["status"] = {"$ne": "archived"}
    if q:
        query["$or"] = [
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"preferred_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"job_title": {"$regex": q, "$options": "i"}},
            {"employee_id": {"$regex": q, "$options": "i"}},
        ]
    items = await db.employees.find(query, {"_id": 0}).sort("last_name", 1).to_list(2000)
    # Batch-attach current pay-basis/frequency (single query, latest per employee).
    ids = [e["employee_id"] for e in items]
    if ids:
        pay_rows = await db.employee_pay_settings.find(
            {"business_id": business_id, "employee_id": {"$in": ids}},
            {"_id": 0, "employee_id": 1, "pay_basis": 1, "pay_frequency": 1,
             "base_hourly_rate": 1, "annual_salary": 1, "effective_from": 1},
        ).sort([("employee_id", 1), ("effective_from", -1)]).to_list(20000)
        current: dict = {}
        for p in pay_rows:
            if p["employee_id"] not in current:
                current[p["employee_id"]] = p
        for e in items:
            c = current.get(e["employee_id"]) or {}
            e["current_pay_basis"] = c.get("pay_basis")
            e["current_pay_frequency"] = c.get("pay_frequency")
    return {"items": items, "total": len(items)}


# --- Duplicate detection --------------------------------------------------
class DuplicateCheckIn(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: Optional[str] = ""
    mobile: Optional[str] = ""
    dob: Optional[str] = None


def _norm_mobile(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


async def _find_duplicates(business_id: str, body: "DuplicateCheckIn | EmployeeIn") -> list[dict]:
    email = (getattr(body, "email", "") or "").strip().lower()
    mobile = _norm_mobile(getattr(body, "mobile", "") or "")
    dob = getattr(body, "dob", None)
    first = (getattr(body, "first_name", "") or "").strip()
    last = (getattr(body, "last_name", "") or "").strip()
    or_clauses = []
    if email:
        or_clauses.append({"email": {"$regex": f"^{re_escape(email)}$", "$options": "i"}})
    if mobile:
        # Match against normalised digits-only field written at create time.
        or_clauses.append({"mobile_norm": {"$regex": f"{mobile[-8:] if len(mobile) > 4 else mobile}$"}})
    if first and last and dob:
        or_clauses.append({
            "first_name": {"$regex": f"^{re_escape(first)}$", "$options": "i"},
            "last_name": {"$regex": f"^{re_escape(last)}$", "$options": "i"},
            "dob": dob,
        })
    if not or_clauses:
        return []
    docs = await db.employees.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}, "$or": or_clauses},
        {"_id": 0, "employee_id": 1, "first_name": 1, "last_name": 1,
         "preferred_name": 1, "email": 1, "mobile": 1, "dob": 1,
         "status": 1, "employment_start_date": 1, "job_title": 1},
    ).to_list(20)
    return docs


def re_escape(s: str) -> str:
    import re
    return re.escape(s)


@router.post("/employees/check-duplicate")
async def check_duplicate(body: DuplicateCheckIn,
                          business_id: str = Depends(get_business_id)):
    matches = await _find_duplicates(business_id, body)
    return {"matches": matches, "count": len(matches)}


@router.post("/employees")
async def create_employee(body: EmployeeIn, force: bool = False,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    if not force:
        matches = await _find_duplicates(business_id, body)
        if matches:
            raise HTTPException(status_code=409, detail={
                "code": "possible_duplicate",
                "message": "Possible matching employee found.",
                "matches": matches,
            })
    emp_id = new_id("emp")
    now = now_iso()
    start = _iso_or_none(body.employment_start_date)
    doc = {
        **body.model_dump(),
        "employee_id": emp_id,
        "business_id": business_id,
        "dob": _iso_or_none(body.dob),
        "mobile_norm": _norm_mobile(body.mobile or ""),
        "employment_start_date": start,
        "employment_end_date": _iso_or_none(body.employment_end_date),
        "probation_end_date": _iso_or_none(body.probation_end_date),
        # Employment periods ledger — first period opens on create
        "employment_periods": [{
            "period_id": new_id("emppd"),
            "start_date": start,
            "end_date": None,
            "termination_reason": None,
            "termination_note": None,
            "terminated_at": None,
            "terminated_by": None,
            "rehired_at": None,
            "rehired_by": None,
            "created_at": now,
            "created_by": user.get("email"),
        }],
        "is_deleted": False,
        "created_at": now,
        "created_by": user.get("email"),
    }
    await db.employees.insert_one(doc)
    await audit(business_id, user, "employee", emp_id, "create", after={"employee_id": emp_id})
    return _clean(doc)


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: str, business_id: str = Depends(get_business_id)):
    doc = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    return _clean(doc)


@router.put("/employees/{employee_id}")
async def update_employee(employee_id: str, body: EmployeeIn,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    prev = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not prev:
        raise HTTPException(status_code=404, detail="Employee not found")
    # Never overwrite the employment_periods history from the payload.
    update = {
        **body.model_dump(),
        "dob": _iso_or_none(body.dob),
        "mobile_norm": _norm_mobile(body.mobile or ""),
        "employment_start_date": _iso_or_none(body.employment_start_date),
        "employment_end_date": _iso_or_none(body.employment_end_date),
        "probation_end_date": _iso_or_none(body.probation_end_date),
        "updated_at": now_iso(),
        "updated_by": user.get("email"),
    }
    await db.employees.update_one(
        {"business_id": business_id, "employee_id": employee_id}, {"$set": update}
    )
    await audit(business_id, user, "employee", employee_id, "update",
                before=None, after={"updated_by": user.get("email")})
    return {**prev, **update}


class TerminateIn(BaseModel):
    termination_date: str
    reason: str = ""
    note: str = ""


@router.post("/employees/{employee_id}/terminate")
async def terminate_employee(employee_id: str, body: TerminateIn,
                              business_id: str = Depends(get_business_id),
                              user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.get("status") == "terminated":
        raise HTTPException(400, "Employee is already terminated")
    periods = emp.get("employment_periods") or []
    # Close the currently-open period.
    for p in periods:
        if p.get("end_date") is None:
            p["end_date"] = body.termination_date
            p["termination_reason"] = body.reason
            p["termination_note"] = body.note
            p["terminated_at"] = now_iso()
            p["terminated_by"] = user.get("email")
            break
    await db.employees.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": {
            "status": "terminated",
            "employment_end_date": body.termination_date,
            "termination_reason": body.reason,
            "termination_note": body.note,
            "terminated_at": now_iso(),
            "terminated_by": user.get("email"),
            "employment_periods": periods,
            "updated_at": now_iso(),
        }},
    )
    await audit(business_id, user, "employee", employee_id, "terminate",
                after={"termination_date": body.termination_date, "reason": body.reason})
    return {"ok": True, "status": "terminated", "termination_date": body.termination_date}


class RehireIn(BaseModel):
    start_date: str
    employment_type: str = "full_time"
    job_title: str = ""
    note: str = ""

    @field_validator("employment_type")
    @classmethod
    def _t(cls, v):
        if v not in EMP_TYPE:
            raise ValueError(f"employment_type must be one of {sorted(EMP_TYPE)}")
        return v


@router.post("/employees/{employee_id}/rehire")
async def rehire_employee(employee_id: str, body: RehireIn,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.get("status") == "active":
        raise HTTPException(400, "Employee is already active")
    now = now_iso()
    new_period = {
        "period_id": new_id("emppd"),
        "start_date": body.start_date,
        "end_date": None,
        "termination_reason": None,
        "termination_note": None,
        "terminated_at": None,
        "terminated_by": None,
        "rehired_at": now,
        "rehired_by": user.get("email"),
        "rehire_note": body.note,
        "created_at": now,
        "created_by": user.get("email"),
    }
    periods = emp.get("employment_periods") or []
    periods.append(new_period)
    await db.employees.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": {
            "status": "active",
            "employment_start_date": body.start_date,   # 'current' start date
            "employment_end_date": None,
            "employment_type": body.employment_type,
            "job_title": body.job_title or emp.get("job_title", ""),
            "employment_periods": periods,
            "updated_at": now,
            # Clear the top-level termination markers (history is preserved in periods)
            "termination_reason": None, "termination_note": None,
            "terminated_at": None, "terminated_by": None,
        }},
    )
    await audit(business_id, user, "employee", employee_id, "rehire",
                after={"start_date": body.start_date})
    return {"ok": True, "status": "active", "period": new_period}


@router.get("/employees/{employee_id}/history")
async def employee_history(employee_id: str, business_id: str = Depends(get_business_id),
                            user: dict = Depends(get_current_user)):
    # Termination reason/note may contain sensitive HR info — owner-only.
    _require_owner(user)
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0},
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    return {"employee_id": employee_id, "periods": emp.get("employment_periods") or []}


@router.delete("/employees/{employee_id}")
async def archive_employee(employee_id: str, business_id: str = Depends(get_business_id),
                            user: dict = Depends(get_current_user)):
    """Soft-delete: sets status=archived and is_deleted=True.
    Historical payroll records are never removed."""
    prev = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    if not prev:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.employees.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": {"is_deleted": True, "status": "archived",
                  "archived_at": now_iso(), "archived_by": user.get("email")}},
    )
    await audit(business_id, user, "employee", employee_id, "archive", before=prev)
    return {"ok": True}


# ============================================================================
# Pay settings — history preserved by writing new documents (never overwrite)
# ============================================================================
class PaySettingsIn(BaseModel):
    pay_basis: str = "hourly"
    pay_frequency: str = "fortnightly"
    base_hourly_rate: str = "0"          # dollars (decimal string) for safety
    annual_salary: str = "0"
    monthly_salary: str = "0"
    fixed_pay_amount: str = "0"
    std_hours_per_day: str = "0"
    std_hours_per_week: str = "0"
    std_hours_per_fortnight: str = "0"
    std_hours_per_month: str = "0"
    std_working_days: str = "0"
    effective_from: str                  # YYYY-MM-DD required so history is meaningful
    notes: str = ""

    @field_validator("pay_basis")
    @classmethod
    def _pb(cls, v):
        if v not in PAY_BASIS:
            raise ValueError(f"pay_basis must be one of {sorted(PAY_BASIS)}")
        return v

    @field_validator("pay_frequency")
    @classmethod
    def _pf(cls, v):
        if v not in PAY_FREQ:
            raise ValueError(f"pay_frequency must be one of {sorted(PAY_FREQ)}")
        return v


async def _ensure_employee(business_id: str, employee_id: str) -> dict:
    emp = await db.employees.find_one(
        {"business_id": business_id, "employee_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.get("/employees/{employee_id}/pay-settings")
async def list_pay_settings(employee_id: str, business_id: str = Depends(get_business_id)):
    await _ensure_employee(business_id, employee_id)
    items = await db.employee_pay_settings.find(
        {"business_id": business_id, "employee_id": employee_id},
        {"_id": 0},
    ).sort("effective_from", -1).to_list(200)
    return {"items": items, "current": items[0] if items else None}


@router.post("/employees/{employee_id}/pay-settings")
async def add_pay_settings(employee_id: str, body: PaySettingsIn,
                            business_id: str = Depends(get_business_id),
                            user: dict = Depends(get_current_user)):
    """Create a new pay-settings row. Also caps the previous row's
    `effective_to` so the history is contiguous and non-overlapping."""
    await _ensure_employee(business_id, employee_id)
    new_from = _iso_or_none(body.effective_from)
    if not new_from:
        raise HTTPException(status_code=422, detail="effective_from is required")
    # cap previous open-ended row
    await db.employee_pay_settings.update_many(
        {"business_id": business_id, "employee_id": employee_id, "effective_to": None},
        {"$set": {"effective_to": new_from}},
    )
    row_id = new_id("payset")
    doc = {
        **body.model_dump(),
        "effective_from": new_from,
        "effective_to": None,
        "pay_setting_id": row_id,
        "employee_id": employee_id,
        "business_id": business_id,
        "created_at": now_iso(),
        "created_by": user.get("email"),
    }
    await db.employee_pay_settings.insert_one(doc)
    await audit(business_id, user, "employee_pay_settings", row_id, "create", after=doc)
    return _clean(doc)


# ============================================================================
# Super profile
# ============================================================================
class SuperIn(BaseModel):
    super_enabled: bool = True
    fund_name: str = ""
    member_number: str = ""
    usi: str = ""
    fund_abn: str = ""
    fund_source: str = "employee_nominated"       # or employer_default
    sg_rate: str = "0.12"                         # decimal fraction; per-employee override
    additional_employer_pct: str = "0"
    voluntary_pct: str = "0"
    salary_sacrifice_amount: str = "0"


@router.get("/employees/{employee_id}/super")
async def get_super(employee_id: str, business_id: str = Depends(get_business_id)):
    await _ensure_employee(business_id, employee_id)
    doc = await db.employee_super.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    return doc or {}


@router.put("/employees/{employee_id}/super")
async def put_super(employee_id: str, body: SuperIn,
                     business_id: str = Depends(get_business_id),
                     user: dict = Depends(get_current_user)):
    await _ensure_employee(business_id, employee_id)
    prev = await db.employee_super.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    doc = {
        **body.model_dump(),
        "employee_id": employee_id,
        "business_id": business_id,
        "updated_at": now_iso(),
        "updated_by": user.get("email"),
    }
    await db.employee_super.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": doc}, upsert=True,
    )
    await audit(business_id, user, "employee_super", employee_id, "update",
                before=prev, after=doc)
    return doc


# ============================================================================
# Tax / PAYG settings  (owner-only — sensitive)
# ============================================================================
class TaxIn(BaseModel):
    payg_enabled: bool = True
    tax_free_threshold: bool = True
    australian_resident: bool = True
    help_loan: bool = False
    other_withholding_pct: str = "0"
    manual_payg_override: str = "0"               # dollars default per pay
    tfn: str = ""                                  # optional; encrypted at rest
    tfn_declared: bool = False
    notes: str = ""


@router.get("/employees/{employee_id}/tax")
async def get_tax(employee_id: str,
                   reveal_tfn: bool = Query(False, description="Owner only — returns full TFN"),
                   business_id: str = Depends(get_business_id),
                   user: dict = Depends(get_current_user)):
    _require_owner(user)
    await _ensure_employee(business_id, employee_id)
    doc = await db.employee_tax_settings.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    ) or {}
    # Never leak the encrypted TFN in normal reads. `tfn_masked` is the display value.
    out = {k: v for k, v in doc.items() if k != "tfn_enc"}
    out["has_tfn"] = bool(doc.get("tfn_enc"))
    out["tfn_masked"] = doc.get("tfn_masked", "")
    if reveal_tfn and doc.get("tfn_enc"):
        try:
            out["tfn"] = pc.decrypt(doc["tfn_enc"])
        except Exception as e:
            raise HTTPException(500, str(e))
        await audit(business_id, user, "employee_tax_settings", employee_id, "reveal_tfn")
    return out


@router.put("/employees/{employee_id}/tax")
async def put_tax(employee_id: str, body: TaxIn,
                   business_id: str = Depends(get_business_id),
                   user: dict = Depends(get_current_user)):
    _require_owner(user)
    await _ensure_employee(business_id, employee_id)
    doc = {
        "payg_enabled": body.payg_enabled,
        "tax_free_threshold": body.tax_free_threshold,
        "australian_resident": body.australian_resident,
        "help_loan": body.help_loan,
        "other_withholding_pct": body.other_withholding_pct,
        "manual_payg_override": body.manual_payg_override,
        "tfn_declared": body.tfn_declared,
        "notes": body.notes,
        "employee_id": employee_id,
        "business_id": business_id,
        "updated_at": now_iso(),
        "updated_by": user.get("email"),
    }
    # Only overwrite tfn_enc if a new TFN string is supplied. Sending "" is
    # treated as "no change" so the reveal-then-save flow doesn't wipe it.
    if body.tfn:
        doc["tfn_enc"] = pc.encrypt(body.tfn)
        doc["tfn_masked"] = pc.mask_tfn(body.tfn)
    await db.employee_tax_settings.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": doc}, upsert=True,
    )
    # Audit records the change but never the actual TFN
    await audit(business_id, user, "employee_tax_settings", employee_id, "update")
    return {k: v for k, v in doc.items() if k != "tfn_enc"}


# ============================================================================
# Bank details (owner-only, encrypted at rest, masked on normal reads)
# ============================================================================
class BankIn(BaseModel):
    account_name: str = ""
    bsb: str = ""
    account_number: str = ""
    payment_reference: str = ""


def _bank_out(doc: Optional[dict], reveal: bool = False) -> dict:
    if not doc:
        return {}
    out = {
        "account_name": doc.get("account_name", ""),
        "payment_reference": doc.get("payment_reference", ""),
        "bsb_masked": doc.get("bsb_masked", ""),
        "account_number_masked": doc.get("account_number_masked", ""),
        "has_details": bool(doc.get("bsb_enc") or doc.get("account_number_enc")),
        "updated_at": doc.get("updated_at"),
    }
    if reveal:
        try:
            out["bsb"] = pc.decrypt(doc.get("bsb_enc", ""))
            out["account_number"] = pc.decrypt(doc.get("account_number_enc", ""))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return out


@router.get("/employees/{employee_id}/bank")
async def get_bank(employee_id: str,
                    reveal: bool = Query(False, description="Owner only — returns full BSB/account"),
                    business_id: str = Depends(get_business_id),
                    user: dict = Depends(get_current_user)):
    _require_owner(user)
    await _ensure_employee(business_id, employee_id)
    doc = await db.employee_bank_details.find_one(
        {"business_id": business_id, "employee_id": employee_id}, {"_id": 0}
    )
    if reveal and doc:
        await audit(business_id, user, "employee_bank_details", employee_id, "reveal")
    return _bank_out(doc, reveal=reveal)


@router.put("/employees/{employee_id}/bank")
async def put_bank(employee_id: str, body: BankIn,
                    business_id: str = Depends(get_business_id),
                    user: dict = Depends(get_current_user)):
    _require_owner(user)
    await _ensure_employee(business_id, employee_id)
    doc = {
        "employee_id": employee_id,
        "business_id": business_id,
        "account_name": body.account_name,
        "payment_reference": body.payment_reference,
        "bsb_enc": pc.encrypt(body.bsb),
        "account_number_enc": pc.encrypt(body.account_number),
        "bsb_masked": pc.mask_bsb(body.bsb),
        "account_number_masked": pc.mask_account(body.account_number),
        "updated_at": now_iso(),
        "updated_by": user.get("email"),
    }
    await db.employee_bank_details.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": doc}, upsert=True,
    )
    # Audit records the change but never the actual account number
    await audit(business_id, user, "employee_bank_details", employee_id, "update")
    return _bank_out(doc)


# ============================================================================
# Leave balances (snapshots — transactions ledger added in Phase 4)
# ============================================================================
class LeaveBalanceIn(BaseModel):
    leave_type: str = Field(min_length=1, max_length=60)
    entitled_hours: str = "0"
    future_approved_hours: str = "0"
    remaining_hours: str = "0"


@router.get("/employees/{employee_id}/leave-balances")
async def list_leave_balances(employee_id: str, business_id: str = Depends(get_business_id)):
    await _ensure_employee(business_id, employee_id)
    items = await db.employee_leave_balances.find(
        {"business_id": business_id, "employee_id": employee_id},
        {"_id": 0},
    ).sort("leave_type", 1).to_list(50)
    return {"items": items}


@router.put("/employees/{employee_id}/leave-balances/{leave_type}")
async def upsert_leave_balance(employee_id: str, leave_type: str, body: LeaveBalanceIn,
                                business_id: str = Depends(get_business_id),
                                user: dict = Depends(get_current_user)):
    await _ensure_employee(business_id, employee_id)
    prev = await db.employee_leave_balances.find_one(
        {"business_id": business_id, "employee_id": employee_id, "leave_type": leave_type},
        {"_id": 0},
    )
    doc = {
        **body.model_dump(),
        "employee_id": employee_id,
        "business_id": business_id,
        "updated_at": now_iso(),
        "updated_by": user.get("email"),
    }
    await db.employee_leave_balances.update_one(
        {"business_id": business_id, "employee_id": employee_id, "leave_type": leave_type},
        {"$set": doc}, upsert=True,
    )
    await audit(business_id, user, "employee_leave_balances",
                f"{employee_id}:{leave_type}", "update", before=prev, after=doc)
    return doc


# ============================================================================
# Payroll settings: pay-items / deductions / leave-types (CRUD only in Ph1)
# ============================================================================
class PayItemIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    kind: str = "earning"                 # earning | deduction | leave
    calc_type: str = "hourly"             # fixed|hourly|percent_of_base|percent_loading|units_rate
    default_rate: str = "0"
    taxable: bool = True
    super_liable: bool = True
    is_active: bool = True

    @field_validator("kind")
    @classmethod
    def _k(cls, v):
        if v not in {"earning", "deduction", "leave"}:
            raise ValueError("kind must be earning|deduction|leave")
        return v

    @field_validator("calc_type")
    @classmethod
    def _c(cls, v):
        if v not in {"fixed", "hourly", "percent_of_base", "percent_loading", "units_rate"}:
            raise ValueError("invalid calc_type")
        return v


@router.get("/pay-items")
async def list_pay_items(business_id: str = Depends(get_business_id)):
    items = await db.pay_items.find(
        {"business_id": business_id}, {"_id": 0}
    ).sort([("kind", 1), ("label", 1)]).to_list(500)
    return {"items": items}


@router.post("/pay-items")
async def create_pay_item(body: PayItemIn, business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    _require_owner(user)
    existing = await db.pay_items.find_one({"business_id": business_id, "code": body.code})
    if existing:
        raise HTTPException(status_code=400, detail=f"Pay item code '{body.code}' already exists")
    doc = {
        **body.model_dump(),
        "pay_item_id": new_id("pi"),
        "business_id": business_id,
        "created_at": now_iso(),
        "created_by": user.get("email"),
    }
    await db.pay_items.insert_one(doc)
    await audit(business_id, user, "pay_item", doc["pay_item_id"], "create", after=doc)
    return _clean(doc)


@router.put("/pay-items/{pay_item_id}")
async def update_pay_item(pay_item_id: str, body: PayItemIn,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    _require_owner(user)
    prev = await db.pay_items.find_one(
        {"business_id": business_id, "pay_item_id": pay_item_id}, {"_id": 0}
    )
    if not prev:
        raise HTTPException(status_code=404, detail="Pay item not found")
    update = {**body.model_dump(), "updated_at": now_iso(), "updated_by": user.get("email")}
    await db.pay_items.update_one(
        {"business_id": business_id, "pay_item_id": pay_item_id}, {"$set": update}
    )
    await audit(business_id, user, "pay_item", pay_item_id, "update", before=prev, after=update)
    return {**prev, **update}


# --- Leave types (labels + defaults) — light CRUD -------------------------
class LeaveTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    accrual_hours_per_year: str = "0"
    is_active: bool = True


@router.get("/leave-types")
async def list_leave_types(business_id: str = Depends(get_business_id)):
    items = await db.pay_leave_types.find(
        {"business_id": business_id}, {"_id": 0}
    ).sort("label", 1).to_list(200)
    return {"items": items}


@router.post("/leave-types")
async def create_leave_type(body: LeaveTypeIn, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    _require_owner(user)
    if await db.pay_leave_types.find_one({"business_id": business_id, "code": body.code}):
        raise HTTPException(status_code=400, detail=f"Leave code '{body.code}' already exists")
    doc = {
        **body.model_dump(),
        "leave_type_id": new_id("lt"),
        "business_id": business_id,
        "created_at": now_iso(),
        "created_by": user.get("email"),
    }
    await db.pay_leave_types.insert_one(doc)
    await audit(business_id, user, "leave_type", doc["leave_type_id"], "create", after=doc)
    return _clean(doc)


# ============================================================================
# Compliance / status flags surfaced to the UI
# ============================================================================
@router.get("/status")
async def payroll_status(business_id: str = Depends(get_business_id)):
    """Non-sensitive: whether module features are configured / enabled.
    Used by the UI to show STP:NOT CONNECTED / PAYG:MANUAL / Super:TRACKED banners."""
    employer = await db.payroll_settings.find_one({"business_id": business_id}, {"_id": 0})
    return {
        "stp": {"enabled": False, "status": "NOT CONNECTED"},
        "payg": {"mode": "manual", "note": "Verify against ATO tax tables before finalising pay."},
        "super": {"mode": "tracked", "note": "Payments are tracked, not automatically transferred."},
        "email": {"enabled": False, "note": "Email service not configured. Download PDF is available."},
        "employer_configured": bool(employer and employer.get("legal_business_name")),
    }


__all__ = ["router"]
