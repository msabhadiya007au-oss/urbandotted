"""Daily Entry: reusable manual template + per-day entry that writes real transactions.

Daily Entry is an ENTRY INTERFACE only. Every value becomes a normal `transactions`
record (linked by daily_entry_id + field_id), so Dashboard / Advertising / COGS /
Cash Flow / GST / Reports / Month-End / Accountant Export all read the SAME records.
Nothing is ever counted twice.
"""
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, to_cents, to_dollars, compute_gst, pct,
                  fy_of, month_key_of, month_label, parse_date, fy_month_keys, current_fy,
                  GST_TREATMENTS)

router = APIRouter(prefix="/api/daily", tags=["daily"])

SECTIONS = [
    ("sales", "Sales"),
    ("advertising", "Advertising"),
    ("courier", "Courier / Shipping"),
    ("product_cogs", "Product / COGS"),
    ("production", "Production Costs"),
    ("packaging", "Packaging"),
    ("other", "Other Daily Expenses"),
    ("custom", "Custom"),
]
FIELD_TYPES = ["currency", "number", "quantity", "unit_cost", "calc_qty_unit",
               "percentage", "text", "yesno"]
REQUIREMENTS = ["required", "optional", "recurring", "not_expected"]
STATUSES = ["not_started", "in_progress", "complete", "closed"]
ROLES = ["sales_total", "orders", "refunds", "other_revenue", "expense"]

# section -> (category name, subcategory name or None) used when seeding the template
DEFAULT_TEMPLATE = [
    ("sales", "Total Sales Received", "currency", "sales_total", "required", "Product Sales", "Online Store", "gst_included", None),
    ("sales", "Total Orders", "number", "orders", "required", None, None, "no_gst", None),
    ("sales", "Total Refunds", "currency", "refunds", "required", "Product Sales", "Online Store", "gst_included", None),
    ("sales", "Other Revenue", "currency", "other_revenue", "optional", "Other Income", "Miscellaneous", "gst_included", None),

    ("advertising", "Meta / Facebook Ads", "currency", "expense", "required", "Advertising", "Meta / Facebook Ads", "gst_free", None),
    ("advertising", "Google Ads", "currency", "expense", "required", "Advertising", "Google Ads", "gst_included", None),
    ("advertising", "Snapchat Ads", "currency", "expense", "optional", "Advertising", "Snapchat Ads", "gst_free", None),
    ("advertising", "TikTok Ads", "currency", "expense", "optional", "Advertising", "TikTok Ads", "gst_free", None),

    ("courier", "Domestic Standard", "currency", "expense", "required", "Shipping", "Australia Post", "gst_included", None),
    ("courier", "Domestic Express", "currency", "expense", "optional", "Shipping", "Australia Post", "gst_included", None),
    ("courier", "International Standard", "currency", "expense", "optional", "Shipping", "Other Shipping", "gst_free", None),
    ("courier", "International Express", "currency", "expense", "optional", "Shipping", "Other Shipping", "gst_free", None),
    ("courier", "Other Courier", "currency", "expense", "optional", "Shipping", "Couriers", "gst_included", None),

    ("product_cogs", "Orders Shipped", "number", "orders_shipped", "optional", None, None, "no_gst", None),
    ("product_cogs", "Mobile Covers Used", "calc_qty_unit", "expense", "required", "Inventory", "Stock Purchases", "gst_included", "1.00"),

    ("production", "Sublimation Paper", "currency", "expense", "optional", "Office Expenses", "Stationery", "gst_included", None),
    ("production", "Printing Cost", "currency", "expense", "optional", "Office Expenses", "Stationery", "gst_included", None),

    ("packaging", "Packaging", "currency", "expense", "optional", "Packaging", "Boxes & Mailers", "gst_included", None),

    ("other", "Electricity", "currency", "expense", "optional", "Electricity", None, "gst_included", None),
    ("other", "Other Expense", "currency", "expense", "optional", "Other Expenses", None, "gst_included", None),
]


def field_out(f: dict) -> dict:
    return {
        "field_id": f["field_id"], "section": f["section"], "label": f["label"],
        "field_type": f["field_type"], "role": f.get("role", "expense"),
        "requirement": f.get("requirement", "optional"),
        "category_id": f.get("category_id"), "category_name": f.get("category_name"),
        "subcategory_id": f.get("subcategory_id"), "subcategory_name": f.get("subcategory_name"),
        "supplier_id": f.get("supplier_id"), "supplier_name": f.get("supplier_name"),
        "account_id": f.get("account_id"),
        "gst_treatment": f.get("gst_treatment", "gst_included"),
        "gst_rate": f.get("gst_rate"),
        "default_unit_cost": to_dollars(f["default_unit_cost_cents"]) if f.get("default_unit_cost_cents") is not None else None,
        "sku": f.get("sku", ""), "unit_label": f.get("unit_label", ""),
        "is_hidden": bool(f.get("is_hidden")), "is_archived": bool(f.get("is_archived")),
        "sort": f.get("sort", 0), "notes_enabled": f.get("notes_enabled", True),
    }


async def _lookup_names(business_id: str, category_name, subcategory_name):
    cat = sub = None
    if category_name:
        cat = await db.categories.find_one(
            {"business_id": business_id, "name": category_name, "parent_id": None}, {"_id": 0})
    if subcategory_name and cat:
        sub = await db.categories.find_one(
            {"business_id": business_id, "name": subcategory_name, "parent_id": cat["category_id"]}, {"_id": 0})
    return cat, sub


async def ensure_template(business_id: str):
    """Seed the default daily template once per business (also covers pre-existing businesses)."""
    if await db.daily_fields.find_one({"business_id": business_id}):
        return
    for i, (section, label, ftype, role, req, cat_name, sub_name, gst, unit_cost) in enumerate(DEFAULT_TEMPLATE):
        cat, sub = await _lookup_names(business_id, cat_name, sub_name)
        await db.daily_fields.insert_one({
            "field_id": new_id("dfld"), "business_id": business_id, "section": section,
            "label": label, "field_type": ftype, "role": role, "requirement": req,
            "category_id": cat["category_id"] if cat else None,
            "category_name": cat["name"] if cat else None,
            "subcategory_id": sub["category_id"] if sub else None,
            "subcategory_name": sub["name"] if sub else None,
            "supplier_id": None, "account_id": None,
            "gst_treatment": gst, "gst_rate": None,
            "default_unit_cost_cents": to_cents(unit_cost) if unit_cost else None,
            "sku": "", "unit_label": "", "is_hidden": False, "is_archived": False,
            "notes_enabled": True, "sort": i + 1, "created_at": now_iso(),
        })


# ---------------- template CRUD ----------------
class FieldIn(BaseModel):
    section: str = "custom"
    label: str = Field(min_length=1, max_length=120)
    field_type: str = "currency"
    role: str = "expense"
    requirement: str = "optional"
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    supplier_id: Optional[str] = None
    account_id: Optional[str] = None
    gst_treatment: str = "gst_included"
    gst_rate: Optional[str] = None
    default_unit_cost: Optional[float] = None
    sku: str = ""
    unit_label: str = ""
    is_hidden: bool = False
    sort: Optional[int] = None

    @field_validator("field_type")
    @classmethod
    def _ft(cls, v):
        if v not in FIELD_TYPES:
            raise ValueError(f"field_type must be one of {FIELD_TYPES}")
        return v

    @field_validator("gst_treatment")
    @classmethod
    def _gt(cls, v):
        if v not in GST_TREATMENTS:
            raise ValueError(f"gst_treatment must be one of {GST_TREATMENTS}")
        return v

    @field_validator("requirement")
    @classmethod
    def _rq(cls, v):
        if v not in REQUIREMENTS:
            raise ValueError(f"requirement must be one of {REQUIREMENTS}")
        return v


async def _resolve(business_id: str, body: FieldIn) -> dict:
    out = {}
    for key, coll, idf, namef in [("category_id", db.categories, "category_id", "category_name"),
                                  ("subcategory_id", db.categories, "category_id", "subcategory_name"),
                                  ("supplier_id", db.suppliers, "supplier_id", "supplier_name")]:
        val = getattr(body, key)
        if val:
            doc = await coll.find_one({"business_id": business_id, idf: val}, {"_id": 0})
            if not doc:
                raise HTTPException(400, f"Invalid {key}")
            out[namef] = doc["name"]
        else:
            out[namef] = None
    return out


@router.get("/fields")
async def list_fields(include_hidden: bool = True, business_id: str = Depends(get_business_id)):
    await ensure_template(business_id)
    q = {"business_id": business_id, "is_archived": {"$ne": True}}
    if not include_hidden:
        q["is_hidden"] = {"$ne": True}
    docs = await db.daily_fields.find(q, {"_id": 0}).sort("sort", 1).to_list(500)
    return {
        "sections": [{"key": k, "label": l} for k, l in SECTIONS],
        "field_types": FIELD_TYPES,
        "requirements": REQUIREMENTS,
        "fields": [field_out(d) for d in docs],
    }


@router.post("/fields")
async def create_field(body: FieldIn, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    count = await db.daily_fields.count_documents({"business_id": business_id})
    doc = {
        "field_id": new_id("dfld"), "business_id": business_id,
        **body.model_dump(exclude={"default_unit_cost", "sort"}),
        "default_unit_cost_cents": to_cents(body.default_unit_cost) if body.default_unit_cost else None,
        "is_archived": False, "notes_enabled": True,
        "sort": body.sort if body.sort is not None else count + 1, "created_at": now_iso(),
    }
    doc.update(await _resolve(business_id, body))
    await db.daily_fields.insert_one(doc)
    await audit(business_id, user, "daily_field", doc["field_id"], "create")
    return field_out(doc)


@router.put("/fields/{field_id}")
async def update_field(field_id: str, body: FieldIn, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    before = await db.daily_fields.find_one({"business_id": business_id, "field_id": field_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Field not found")
    upd = {**body.model_dump(exclude={"default_unit_cost", "sort"}),
           "default_unit_cost_cents": to_cents(body.default_unit_cost) if body.default_unit_cost else None}
    if body.sort is not None:
        upd["sort"] = body.sort
    upd.update(await _resolve(business_id, body))
    await db.daily_fields.update_one({"business_id": business_id, "field_id": field_id}, {"$set": upd})
    # Changing a default unit cost must never alter history: past transactions keep the
    # unit cost frozen on the record, so nothing else is touched here.
    await audit(business_id, user, "daily_field", field_id, "update", field_out(before), upd)
    doc = await db.daily_fields.find_one({"field_id": field_id}, {"_id": 0})
    return field_out(doc)


@router.post("/fields/{field_id}/archive")
async def archive_field(field_id: str, archived: bool = True,
                        business_id: str = Depends(get_business_id),
                        user: dict = Depends(get_current_user)):
    res = await db.daily_fields.update_one({"business_id": business_id, "field_id": field_id},
                                          {"$set": {"is_archived": archived}})
    if not res.matched_count:
        raise HTTPException(404, "Field not found")
    await audit(business_id, user, "daily_field", field_id, "archive" if archived else "restore")
    return {"ok": True, "note": "Existing transactions are untouched."}


class ReorderIn(BaseModel):
    field_ids: List[str]


@router.post("/fields/reorder")
async def reorder_fields(body: ReorderIn, business_id: str = Depends(get_business_id)):
    for i, fid in enumerate(body.field_ids):
        await db.daily_fields.update_one({"business_id": business_id, "field_id": fid},
                                        {"$set": {"sort": i + 1}})
    return {"ok": True}


# ---------------- entry ----------------
class ValueIn(BaseModel):
    value: Optional[float] = None      # currency / number / percentage
    qty: Optional[float] = None        # calc_qty_unit
    unit_cost: Optional[float] = None  # overrides the field default for this day only
    text: Optional[str] = None
    yesno: Optional[bool] = None
    note: str = ""
    no_spend: bool = False             # explicit "$0 / no spend" confirmation


class EntryIn(BaseModel):
    entry_date: str
    values: Dict[str, ValueIn] = {}
    status: str = "in_progress"
    notes: str = ""

    @field_validator("entry_date")
    @classmethod
    def _d(cls, v):
        return parse_date(v).isoformat()

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v


def _amount_for(field: dict, v: ValueIn):
    """Returns (amount, qty, unit_cost_cents, is_blank). Blank is NOT zero."""
    ftype = field["field_type"]
    if ftype == "calc_qty_unit":
        if v.qty is None and not v.no_spend:
            return None, None, None, True
        qty = Decimal(str(v.qty or 0))
        unit = v.unit_cost if v.unit_cost is not None else \
            (to_dollars(field["default_unit_cost_cents"]) if field.get("default_unit_cost_cents") else 0)
        unit_d = Decimal(str(unit or 0))
        return float(qty * unit_d), float(qty), to_cents(unit_d), False
    if ftype in ("text", "yesno"):
        return None, None, None, True
    if v.value is None and not v.no_spend:
        return None, None, None, True
    return float(v.value or 0), None, None, False


async def _write_transaction(business_id: str, user: dict, field: dict, entry_date: str,
                             amount: float, qty, unit_cost_cents, note: str,
                             entry_id: str, default_rate: str):
    role = field.get("role", "expense")
    if role == "orders" or role == "orders_shipped":
        return None
    txn_type = {"sales_total": "sale", "refunds": "refund",
                "other_revenue": "other_income"}.get(role, "expense")
    ex, gst, inc, review = compute_gst(amount, field.get("gst_treatment", "gst_included"),
                                      field.get("gst_rate"), True, default_rate)
    doc = {
        "business_id": business_id, "txn_type": txn_type, "date": entry_date,
        "fy": fy_of(entry_date), "month_key": month_key_of(entry_date),
        "category_id": field.get("category_id"), "category_name": field.get("category_name"),
        "subcategory_id": field.get("subcategory_id"), "subcategory_name": field.get("subcategory_name"),
        "supplier_id": field.get("supplier_id"), "supplier_name": field.get("supplier_name"),
        "account_id": field.get("account_id"), "account_name": None,
        "description": field["label"],
        "amount_ex_cents": ex, "gst_cents": gst, "amount_inc_cents": inc,
        "gst_treatment": field.get("gst_treatment", "gst_included"),
        "gst_rate": field.get("gst_rate") or default_rate,
        "reference": "", "notes": note or "", "tags": ["daily-entry"],
        "needs_review": review, "ask_accountant": False, "accountant_note": "",
        "reconcile_status": "unreconciled", "receipt_document_ids": [],
        "source": "daily_entry", "daily_entry_id": entry_id, "daily_field_id": field["field_id"],
        # unit cost is frozen on the record so changing the default later never rewrites history
        "daily_qty": qty, "daily_unit_cost_cents": unit_cost_cents,
        "is_deleted": False, "is_demo": False,
        "updated_at": now_iso(), "updated_by": user["email"],
    }
    if txn_type == "sale":
        doc["sale"] = {"gross": amount, "discounts": 0, "shipping_revenue": 0,
                       "other_income": 0, "gift_cards": 0, "fees": 0}
    if txn_type == "refund":
        doc["refund"] = {"reason": "Daily entry", "original_order": "", "sku": field.get("sku", "")}
    if qty and field.get("sku"):
        doc["items"] = [{"sku": field["sku"], "qty": int(qty)}]

    existing = await db.transactions.find_one(
        {"business_id": business_id, "daily_entry_id": entry_id,
         "daily_field_id": field["field_id"]}, {"_id": 0})
    if existing:
        # preserve accountant-facing edits made outside Daily Entry
        keep = {k: existing[k] for k in
                ("receipt_document_ids", "ask_accountant", "accountant_note",
                 "reconcile_status", "reference") if existing.get(k)}
        doc.update(keep)
        await db.transactions.update_one({"txn_id": existing["txn_id"]}, {"$set": doc})
        return existing["txn_id"]
    doc.update({"txn_id": new_id("txn"), "created_at": now_iso(), "created_by": user["email"]})
    await db.transactions.insert_one(doc)
    return doc["txn_id"]


async def _build_entry(business_id: str, entry_date: str) -> dict:
    await ensure_template(business_id)
    fields = await db.daily_fields.find(
        {"business_id": business_id, "is_archived": {"$ne": True}, "is_hidden": {"$ne": True}},
        {"_id": 0}).sort("sort", 1).to_list(500)
    entry = await db.daily_entries.find_one(
        {"business_id": business_id, "entry_date": entry_date}, {"_id": 0})
    values = (entry or {}).get("values", {})
    txns = await db.transactions.find(
        {"business_id": business_id, "date": entry_date, "source": "daily_entry",
         "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    by_field = {t["daily_field_id"]: t for t in txns if t.get("daily_field_id")}

    out_fields, missing = [], []
    for f in fields:
        fo = field_out(f)
        v = values.get(f["field_id"], {})
        t = by_field.get(f["field_id"])
        fo["value"] = v.get("value")
        fo["qty"] = v.get("qty")
        # show the unit cost frozen on the saved record; only fall back to the current
        # template default for days that have not been entered yet.
        if t and t.get("daily_unit_cost_cents") is not None:
            fo["unit_cost"] = to_dollars(t["daily_unit_cost_cents"])
        elif v.get("unit_cost") is not None:
            fo["unit_cost"] = v.get("unit_cost")
        else:
            fo["unit_cost"] = fo["default_unit_cost"]
        fo["text"] = v.get("text")
        fo["yesno"] = v.get("yesno")
        fo["note"] = v.get("note", "")
        fo["no_spend"] = bool(v.get("no_spend"))
        fo["txn_id"] = t["txn_id"] if t else None
        fo["amount"] = to_dollars(t["amount_inc_cents"]) if t else None
        fo["receipt_document_ids"] = (t or {}).get("receipt_document_ids", [])
        fo["is_blank"] = fo["value"] is None and fo["qty"] is None and not fo["no_spend"] \
            and fo["field_type"] not in ("text", "yesno")
        if f.get("requirement") == "required" and fo["is_blank"]:
            missing.append(f["label"])
        out_fields.append(fo)

    totals = _totals(out_fields)
    return {
        "entry_date": entry_date,
        "date_label": parse_date(entry_date).strftime("%d/%m/%Y"),
        "fy": fy_of(entry_date), "month_key": month_key_of(entry_date),
        "status": (entry or {}).get("status", "not_started"),
        "notes": (entry or {}).get("notes", ""),
        "sections": [{"key": k, "label": l} for k, l in SECTIONS],
        "fields": out_fields,
        "missing_required": missing,
        "can_complete": len(missing) == 0,
        "totals": totals,
        "updated_at": (entry or {}).get("updated_at"),
    }


def _totals(fields: List[dict]) -> dict:
    def s(pred):
        return round(sum(f["amount"] or 0 for f in fields if pred(f) and f["amount"] is not None), 2)

    sales = s(lambda f: f["role"] == "sales_total")
    refunds = s(lambda f: f["role"] == "refunds")
    other_rev = s(lambda f: f["role"] == "other_revenue")
    ads = s(lambda f: f["section"] == "advertising" and f["role"] == "expense")
    courier = s(lambda f: f["section"] == "courier")
    cogs = s(lambda f: f["section"] == "product_cogs" and f["role"] == "expense")
    production = s(lambda f: f["section"] == "production")
    packaging = s(lambda f: f["section"] == "packaging")
    other = s(lambda f: f["section"] in ("other", "custom") and f["role"] == "expense")
    orders = next((int(f["value"]) for f in fields if f["role"] == "orders" and f["value"] is not None), 0)

    net_sales = round(sales - refunds + other_rev, 2)
    expenses = round(ads + courier + cogs + production + packaging + other, 2)
    profit = round(net_sales - expenses, 2)
    return {
        "sales": sales, "orders": orders, "refunds": refunds, "other_revenue": other_rev,
        "net_sales": net_sales, "advertising": ads, "courier": courier, "cogs": cogs,
        "production": production, "packaging": packaging, "other_expenses": other,
        "total_expenses": expenses, "estimated_profit": profit,
        "profit_margin_pct": pct(profit, net_sales),
        "section_subtotals": {
            key: round(sum(f["amount"] or 0 for f in fields
                           if f["section"] == key and f["amount"] is not None), 2)
            for key, _ in SECTIONS
        },
    }


@router.get("/entry")
async def get_entry(entry_date: Optional[str] = None, business_id: str = Depends(get_business_id)):
    d = parse_date(entry_date).isoformat() if entry_date else \
        (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    return await _build_entry(business_id, d)


@router.post("/entry")
async def save_entry(body: EntryIn, business_id: str = Depends(get_business_id),
                     user: dict = Depends(get_current_user)):
    await ensure_template(business_id)
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    default_rate = (biz or {}).get("default_gst_rate", "0.10")
    entry_id = f"day_{business_id}_{body.entry_date}"
    fields = {f["field_id"]: f for f in await db.daily_fields.find(
        {"business_id": business_id, "is_archived": {"$ne": True}}, {"_id": 0}).to_list(500)}

    stored, written = {}, []
    for fid, v in body.values.items():
        field = fields.get(fid)
        if not field:
            continue
        amount, qty, unit_cents, is_blank = _amount_for(field, v)
        stored[fid] = {k: val for k, val in {
            "value": v.value, "qty": v.qty, "unit_cost": v.unit_cost, "text": v.text,
            "yesno": v.yesno, "note": v.note, "no_spend": v.no_spend,
        }.items() if val not in (None, "", False)}
        if is_blank or amount is None:
            # blank means "not reviewed" — remove any transaction previously generated
            await db.transactions.delete_many({
                "business_id": business_id, "daily_entry_id": entry_id, "daily_field_id": fid})
            continue
        txn_id = await _write_transaction(business_id, user, field, body.entry_date, amount,
                                         qty, unit_cents, v.note, entry_id, default_rate)
        if txn_id:
            written.append(txn_id)

    # persist values FIRST, then validate — otherwise the completeness check would
    # run against the not-yet-saved day and always report everything as missing.
    await db.daily_entries.update_one(
        {"business_id": business_id, "entry_date": body.entry_date},
        {"$set": {"entry_id": entry_id, "business_id": business_id, "entry_date": body.entry_date,
                  "fy": fy_of(body.entry_date), "month_key": month_key_of(body.entry_date),
                  "values": stored, "status": body.status, "notes": body.notes,
                  "updated_at": now_iso(), "updated_by": user["email"]},
         "$setOnInsert": {"created_at": now_iso(), "created_by": user["email"]}},
        upsert=True)

    result = await _build_entry(business_id, body.entry_date)
    if body.status == "complete" and result["missing_required"]:
        # keep the data, but the day cannot silently claim to be complete
        await db.daily_entries.update_one(
            {"business_id": business_id, "entry_date": body.entry_date},
            {"$set": {"status": "in_progress"}})
        raise HTTPException(
            400, f"Saved, but cannot mark complete — missing: {', '.join(result['missing_required'])}")

    await audit(business_id, user, "daily_entry", body.entry_date, f"save_{body.status}")
    result["transactions_written"] = len(written)
    return result


@router.delete("/entry/{entry_date}")
async def clear_entry(entry_date: str, business_id: str = Depends(get_business_id),
                      user: dict = Depends(get_current_user)):
    d = parse_date(entry_date).isoformat()
    entry_id = f"day_{business_id}_{d}"
    res = await db.transactions.delete_many({"business_id": business_id, "daily_entry_id": entry_id})
    await db.daily_entries.delete_one({"business_id": business_id, "entry_date": d})
    await audit(business_id, user, "daily_entry", d, "clear")
    return {"ok": True, "transactions_removed": res.deleted_count}


# ---------------- history & period summaries ----------------
@router.get("/history")
async def history(fy: Optional[str] = None, month_key: Optional[str] = None,
                  limit: int = Query(120, le=400), business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id, "source": "daily_entry", "is_deleted": {"$ne": True}}
    if fy:
        q["fy"] = fy
    if month_key:
        q["month_key"] = month_key
    txns = await db.transactions.find(q, {"_id": 0}).to_list(20000)
    fields = {f["field_id"]: f for f in await db.daily_fields.find(
        {"business_id": business_id}, {"_id": 0}).to_list(500)}
    entries = await db.daily_entries.find(
        {k: v for k, v in q.items() if k in ("business_id", "fy", "month_key")}, {"_id": 0}).to_list(500)
    status_by_date = {e["entry_date"]: e.get("status", "not_started") for e in entries}
    orders_by_date = {}
    for e in entries:
        for fid, v in (e.get("values") or {}).items():
            f = fields.get(fid)
            if f and f.get("role") == "orders" and v.get("value") is not None:
                orders_by_date[e["entry_date"]] = int(v["value"])

    by_date: Dict[str, dict] = {}
    for t in txns:
        row = by_date.setdefault(t["date"], {
            "date": t["date"], "sales": 0.0, "refunds": 0.0, "other_revenue": 0.0,
            "advertising": 0.0, "courier": 0.0, "cogs": 0.0, "production": 0.0,
            "packaging": 0.0, "other_expenses": 0.0})
        f = fields.get(t.get("daily_field_id")) or {}
        role, section = f.get("role", "expense"), f.get("section", "other")
        amt = to_dollars(t["amount_inc_cents"])
        if role == "sales_total":
            row["sales"] += amt
        elif role == "refunds":
            row["refunds"] += amt
        elif role == "other_revenue":
            row["other_revenue"] += amt
        elif section == "advertising":
            row["advertising"] += amt
        elif section == "courier":
            row["courier"] += amt
        elif section == "product_cogs":
            row["cogs"] += amt
        elif section == "production":
            row["production"] += amt
        elif section == "packaging":
            row["packaging"] += amt
        else:
            row["other_expenses"] += amt

    rows = []
    for d in sorted(by_date.keys(), reverse=True)[:limit]:
        r = by_date[d]
        net = round(r["sales"] - r["refunds"] + r["other_revenue"], 2)
        exp = round(r["advertising"] + r["courier"] + r["cogs"] + r["production"]
                    + r["packaging"] + r["other_expenses"], 2)
        profit = round(net - exp, 2)
        rows.append({**{k: round(v, 2) for k, v in r.items() if k != "date"},
                     "date": d, "date_label": parse_date(d).strftime("%d/%m/%Y"),
                     "orders": orders_by_date.get(d, 0), "net_sales": net,
                     "total_expenses": exp, "estimated_profit": profit,
                     "profit_margin_pct": pct(profit, net),
                     "status": status_by_date.get(d, "not_started")})
    return {"rows": rows, "count": len(rows)}


@router.get("/periods")
async def periods(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    """Today / This Week / This Month / FY roll-ups of the SAME transactions."""
    fy = fy or current_fy()
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    ranges = {
        "today": (today, today),
        "week": (week_start, today),
        "month": (month_start, today),
        "fy": None,
    }
    hist = await history(fy=fy, limit=400, business_id=business_id)
    out = {}
    for key, rng in ranges.items():
        if rng is None:
            rows = hist["rows"]
        else:
            a, b = rng[0].isoformat(), rng[1].isoformat()
            rows = [r for r in hist["rows"] if a <= r["date"] <= b]

        def t(k):
            return round(sum(r[k] for r in rows), 2)

        net = t("net_sales")
        profit = t("estimated_profit")
        out[key] = {
            "sales": t("sales"), "orders": sum(r["orders"] for r in rows), "refunds": t("refunds"),
            "net_sales": net, "cogs": t("cogs"), "advertising": t("advertising"),
            "courier": t("courier"), "production": t("production"), "packaging": t("packaging"),
            "other_expenses": t("other_expenses"), "total_expenses": t("total_expenses"),
            "estimated_profit": profit, "profit_margin_pct": pct(profit, net),
            "days_recorded": len(rows),
        }
    out["fy_label"] = fy
    out["note"] = ("Daily Entry values are stored as normal transactions, so these roll-ups and the "
                   "main Dashboard, Advertising, COGS, GST, Cash Flow and Reports pages all read the "
                   "same records — nothing is counted twice.")
    return out


@router.get("/calendar")
async def calendar(month_key: str, business_id: str = Depends(get_business_id)):
    entries = await db.daily_entries.find(
        {"business_id": business_id, "month_key": month_key}, {"_id": 0}).to_list(60)
    return {"month_key": month_key, "month_label": month_label(month_key),
            "days": [{"entry_date": e["entry_date"], "status": e.get("status", "not_started")}
                     for e in sorted(entries, key=lambda x: x["entry_date"])]}
