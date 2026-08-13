"""Transactions: expenses, sales, refunds, other income. CRUD + bulk + reconciliation."""
from decimal import Decimal
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, compute_gst, to_cents, to_dollars,
                  fy_of, month_key_of, parse_date, month_label, GST_TREATMENTS)
from queries import TxnFilters, build_filter, txn_out

router = APIRouter(prefix="/api", tags=["transactions"])
TXN_TYPES = ["expense", "sale", "refund", "other_income"]


class SaleFields(BaseModel):
    gross: float = 0
    discounts: float = 0
    shipping_revenue: float = 0
    other_income: float = 0
    gift_cards: float = 0
    fees: float = 0


class RefundFields(BaseModel):
    reason: str = ""
    original_order: str = ""
    product_id: Optional[str] = None
    sku: str = ""


class AdMetrics(BaseModel):
    revenue: Optional[float] = None
    orders: Optional[int] = None
    clicks: Optional[int] = None
    impressions: Optional[int] = None


class LineItem(BaseModel):
    product_id: Optional[str] = None
    sku: str = ""
    qty: int = 0


class TxnIn(BaseModel):
    txn_type: str = "expense"
    date: str
    amount: float
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    supplier_id: Optional[str] = None
    account_id: Optional[str] = None
    description: str = ""
    gst_treatment: str = "gst_included"
    gst_rate: Optional[str] = None
    custom_inclusive: bool = True
    reference: str = ""
    notes: str = ""
    tags: List[str] = []
    recurring_template_id: Optional[str] = None
    receipt_document_ids: List[str] = []
    ask_accountant: bool = False
    accountant_note: str = ""
    reconcile_status: str = "unreconciled"
    sale: Optional[SaleFields] = None
    refund: Optional[RefundFields] = None
    ad_metrics: Optional[AdMetrics] = None
    items: List[LineItem] = []
    external_source: Optional[str] = None
    external_id: Optional[str] = None

    @field_validator("txn_type")
    @classmethod
    def _t(cls, v):
        if v not in TXN_TYPES:
            raise ValueError(f"txn_type must be one of {TXN_TYPES}")
        return v

    @field_validator("gst_treatment")
    @classmethod
    def _g(cls, v):
        if v not in GST_TREATMENTS:
            raise ValueError(f"gst_treatment must be one of {GST_TREATMENTS}")
        return v

    @field_validator("amount")
    @classmethod
    def _a(cls, v):
        if v is None or v <= 0:
            raise ValueError("Amount must be greater than 0")
        if v > 100_000_000:
            raise ValueError("Amount is unrealistically large")
        return v

    @field_validator("date")
    @classmethod
    def _d(cls, v):
        try:
            d = parse_date(v)
        except Exception:
            raise ValueError("Invalid date")
        if d.year < 2000 or d.year > 2100:
            raise ValueError("Date is out of a sensible range")
        return d.isoformat()

    @field_validator("gst_rate")
    @classmethod
    def _r(cls, v):
        """Rate is a decimal fraction ('0.10' = 10%). Accept a percentage and normalise it."""
        if v in (None, ""):
            return None
        try:
            rate = Decimal(str(v))
        except Exception:
            raise ValueError("gst_rate must be a number, e.g. 0.10 for 10%")
        if rate < 0:
            raise ValueError("gst_rate cannot be negative")
        if rate > 1:
            if rate > 100:
                raise ValueError("gst_rate is too large — use 0.10 for 10%")
            rate = rate / Decimal(100)
        return str(rate)


async def _names(business_id: str, body: TxnIn) -> Dict[str, Any]:
    out = {}
    for key, coll, id_field, name_field in [
        ("category_id", db.categories, "category_id", "category_name"),
        ("subcategory_id", db.categories, "category_id", "subcategory_name"),
        ("supplier_id", db.suppliers, "supplier_id", "supplier_name"),
        ("account_id", db.payment_accounts, "account_id", "account_name"),
    ]:
        val = getattr(body, key)
        if val:
            doc = await coll.find_one({"business_id": business_id, id_field: val}, {"_id": 0})
            if not doc:
                raise HTTPException(400, f"Invalid {key}")
            out[name_field] = doc["name"]
        else:
            out[name_field] = None
    return out


async def _default_rate(business_id: str) -> str:
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    return (biz or {}).get("default_gst_rate", "0.10")


async def _build_doc(business_id: str, body: TxnIn, user: dict) -> dict:
    rate = body.gst_rate or await _default_rate(business_id)
    ex, gst, inc, review = compute_gst(body.amount, body.gst_treatment, body.gst_rate,
                                       body.custom_inclusive, await _default_rate(business_id))
    d = body.date
    doc = {
        "business_id": business_id, "txn_type": body.txn_type, "date": d,
        "fy": fy_of(d), "month_key": month_key_of(d),
        "category_id": body.category_id, "subcategory_id": body.subcategory_id,
        "supplier_id": body.supplier_id, "account_id": body.account_id,
        "description": body.description, "amount_ex_cents": ex, "gst_cents": gst,
        "amount_inc_cents": inc, "gst_treatment": body.gst_treatment,
        "gst_rate": rate if body.gst_treatment in ("gst_included", "gst_excluded", "custom") else None,
        "reference": body.reference, "notes": body.notes, "tags": body.tags,
        "recurring_template_id": body.recurring_template_id,
        "receipt_document_ids": body.receipt_document_ids,
        "needs_review": review, "ask_accountant": body.ask_accountant,
        "accountant_note": body.accountant_note, "reconcile_status": body.reconcile_status,
        "sale": body.sale.model_dump() if body.sale else None,
        "refund": body.refund.model_dump() if body.refund else None,
        "ad_metrics": body.ad_metrics.model_dump() if body.ad_metrics else None,
        "items": [i.model_dump() for i in body.items],
        "external_source": body.external_source, "external_id": body.external_id,
        "is_deleted": False, "is_demo": False,
    }
    doc.update(await _names(business_id, body))
    return doc


@router.get("/transactions")
async def list_transactions(f: TxnFilters = Depends(), limit: int = Query(200, le=2000),
                            skip: int = 0, sort: str = "date",
                            direction: int = -1, business_id: str = Depends(get_business_id)):
    q = build_filter(business_id, f)
    total = await db.transactions.count_documents(q)
    docs = await db.transactions.find(q, {"_id": 0}).sort(sort, direction).skip(skip).limit(limit).to_list(limit)
    agg = await db.transactions.aggregate([{"$match": q}, {"$group": {
        "_id": None, "inc": {"$sum": "$amount_inc_cents"}, "ex": {"$sum": "$amount_ex_cents"},
        "gst": {"$sum": "$gst_cents"}}}]).to_list(1)
    totals = agg[0] if agg else {"inc": 0, "ex": 0, "gst": 0}
    return {
        "total": total, "skip": skip, "limit": limit,
        "items": [txn_out(d) for d in docs],
        "totals": {"amount_inc": to_dollars(totals["inc"]), "amount_ex": to_dollars(totals["ex"]),
                   "gst": to_dollars(totals["gst"])},
    }


@router.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str, business_id: str = Depends(get_business_id)):
    doc = await db.transactions.find_one({"business_id": business_id, "txn_id": txn_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Transaction not found")
    return txn_out(doc)


@router.post("/transactions")
async def create_transaction(body: TxnIn, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    if body.external_source and body.external_id:
        dup = await db.transactions.find_one({"business_id": business_id,
                                             "external_source": body.external_source,
                                             "external_id": body.external_id})
        if dup:
            raise HTTPException(409, "Duplicate: this external transaction was already imported")
    doc = await _build_doc(business_id, body, user)
    # near-duplicate guard
    near = await db.transactions.find_one({
        "business_id": business_id, "date": doc["date"], "txn_type": doc["txn_type"],
        "amount_inc_cents": doc["amount_inc_cents"], "category_id": doc["category_id"],
        "subcategory_id": doc["subcategory_id"], "is_deleted": {"$ne": True}})
    doc.update({"txn_id": new_id("txn"), "created_at": now_iso(),
                "created_by": user["email"], "updated_at": now_iso(), "updated_by": user["email"],
                "possible_duplicate_of": near["txn_id"] if near else None})
    await db.transactions.insert_one(doc)
    await audit(business_id, user, "transaction", doc["txn_id"], "create", None, txn_out(doc))
    return txn_out(doc)


@router.put("/transactions/{txn_id}")
async def update_transaction(txn_id: str, body: TxnIn, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    before = await db.transactions.find_one({"business_id": business_id, "txn_id": txn_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Transaction not found")
    doc = await _build_doc(business_id, body, user)
    doc.update({"updated_at": now_iso(), "updated_by": user["email"],
                "manually_reviewed": True})
    await db.transactions.update_one({"business_id": business_id, "txn_id": txn_id}, {"$set": doc})
    after = await db.transactions.find_one({"business_id": business_id, "txn_id": txn_id}, {"_id": 0})
    await audit(business_id, user, "transaction", txn_id, "update", txn_out(before), txn_out(after))
    return txn_out(after)


@router.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: str, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    before = await db.transactions.find_one({"business_id": business_id, "txn_id": txn_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Transaction not found")
    await db.transactions.update_one({"business_id": business_id, "txn_id": txn_id},
                                     {"$set": {"is_deleted": True, "deleted_at": now_iso(),
                                               "deleted_by": user["email"]}})
    await audit(business_id, user, "transaction", txn_id, "soft_delete", txn_out(before), None)
    return {"ok": True, "message": "Archived (soft-deleted). Financial records are never destroyed."}


@router.post("/transactions/{txn_id}/restore")
async def restore_transaction(txn_id: str, business_id: str = Depends(get_business_id),
                              user: dict = Depends(get_current_user)):
    await db.transactions.update_one({"business_id": business_id, "txn_id": txn_id},
                                     {"$set": {"is_deleted": False}})
    await audit(business_id, user, "transaction", txn_id, "restore")
    return {"ok": True}


class BulkIn(BaseModel):
    txn_ids: List[str]
    action: str
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    gst_treatment: Optional[str] = None
    gst_rate: Optional[str] = None
    tag: Optional[str] = None
    reconcile_status: Optional[str] = None


@router.post("/transactions/bulk")
async def bulk_action(body: BulkIn, business_id: str = Depends(get_business_id),
                      user: dict = Depends(get_current_user)):
    q = {"business_id": business_id, "txn_id": {"$in": body.txn_ids}}
    n = 0
    if body.action == "change_category":
        cat = await db.categories.find_one({"business_id": business_id, "category_id": body.category_id}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category")
        sub = None
        if body.subcategory_id:
            sub = await db.categories.find_one({"business_id": business_id, "category_id": body.subcategory_id}, {"_id": 0})
        upd = {"category_id": cat["category_id"], "category_name": cat["name"],
               "subcategory_id": sub["category_id"] if sub else None,
               "subcategory_name": sub["name"] if sub else None}
        n = (await db.transactions.update_many(q, {"$set": upd})).modified_count
    elif body.action == "change_gst":
        default_rate = await _default_rate(business_id)
        docs = await db.transactions.find(q, {"_id": 0}).to_list(2000)
        for d in docs:
            ex, gst, inc, review = compute_gst(to_dollars(d["amount_inc_cents"]),
                                               body.gst_treatment, body.gst_rate, True, default_rate)
            await db.transactions.update_one({"txn_id": d["txn_id"]}, {"$set": {
                "amount_ex_cents": ex, "gst_cents": gst, "amount_inc_cents": inc,
                "gst_treatment": body.gst_treatment, "needs_review": review,
                "updated_at": now_iso(), "updated_by": user["email"]}})
            n += 1
    elif body.action == "add_tag":
        n = (await db.transactions.update_many(q, {"$addToSet": {"tags": body.tag}})).modified_count
    elif body.action == "mark_reviewed":
        n = (await db.transactions.update_many(q, {"$set": {"needs_review": False, "manually_reviewed": True}})).modified_count
    elif body.action == "reconcile":
        n = (await db.transactions.update_many(q, {"$set": {"reconcile_status": body.reconcile_status or "reconciled"}})).modified_count
    elif body.action == "delete":
        n = (await db.transactions.update_many(q, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})).modified_count
    else:
        raise HTTPException(400, "Unknown bulk action")
    await audit(business_id, user, "transaction", ",".join(body.txn_ids[:20]), f"bulk_{body.action}")
    return {"ok": True, "affected": n}


class AskAccountantIn(BaseModel):
    ask_accountant: bool = True
    accountant_note: str = ""


@router.post("/transactions/{txn_id}/ask-accountant")
async def ask_accountant(txn_id: str, body: AskAccountantIn,
                         business_id: str = Depends(get_business_id),
                         user: dict = Depends(get_current_user)):
    res = await db.transactions.update_one(
        {"business_id": business_id, "txn_id": txn_id},
        {"$set": {"ask_accountant": body.ask_accountant, "accountant_note": body.accountant_note}})
    if not res.matched_count:
        raise HTTPException(404, "Transaction not found")
    await audit(business_id, user, "transaction", txn_id, "ask_accountant", None, body.model_dump())
    return {"ok": True}


@router.get("/reconciliation/summary")
async def reconciliation_summary(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    from core import current_fy
    fy = fy or current_fy()
    q = {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}
    out = {}
    for status in ["unreconciled", "matched", "reconciled", "needs_review"]:
        out[status] = await db.transactions.count_documents({**q, "reconcile_status": status})
    return {"fy": fy, "counts": out,
            "note": "Automatic bank feeds are Coming in Phase 5. Reconcile manually for now."}
