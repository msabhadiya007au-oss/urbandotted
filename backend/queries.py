"""Shared query helpers for transactions."""
from typing import Optional
from fastapi import Query

from core import db, to_dollars, fy_bounds, month_label


def txn_out(d: dict) -> dict:
    return {
        "txn_id": d["txn_id"],
        "txn_type": d["txn_type"],
        "date": d["date"],
        "fy": d["fy"],
        "month_key": d["month_key"],
        "month_label": month_label(d["month_key"]),
        "category_id": d.get("category_id"),
        "category_name": d.get("category_name"),
        "subcategory_id": d.get("subcategory_id"),
        "subcategory_name": d.get("subcategory_name"),
        "supplier_id": d.get("supplier_id"),
        "supplier_name": d.get("supplier_name"),
        "account_id": d.get("account_id"),
        "account_name": d.get("account_name"),
        "description": d.get("description", ""),
        "amount_ex": to_dollars(d.get("amount_ex_cents")),
        "gst": to_dollars(d.get("gst_cents")),
        "amount_inc": to_dollars(d.get("amount_inc_cents")),
        "gst_treatment": d.get("gst_treatment"),
        "gst_rate": d.get("gst_rate"),
        "reference": d.get("reference", ""),
        "notes": d.get("notes", ""),
        "tags": d.get("tags", []),
        "payment_method": d.get("account_name"),
        "receipt_document_ids": d.get("receipt_document_ids", []),
        "has_receipt": bool(d.get("receipt_document_ids")),
        "needs_review": bool(d.get("needs_review")),
        "ask_accountant": bool(d.get("ask_accountant")),
        "accountant_note": d.get("accountant_note", ""),
        "reconcile_status": d.get("reconcile_status", "unreconciled"),
        "recurring_template_id": d.get("recurring_template_id"),
        "external_source": d.get("external_source"),
        "external_id": d.get("external_id"),
        "sale": d.get("sale") or {},
        "refund": d.get("refund") or {},
        "items": d.get("items", []),
        "ad_metrics": d.get("ad_metrics") or {},
        "is_demo": bool(d.get("is_demo")),
        "created_at": d.get("created_at"),
        "created_by": d.get("created_by"),
        "updated_at": d.get("updated_at"),
        "updated_by": d.get("updated_by"),
        # Payroll integration flags (Phase 5)
        "payroll_kind": d.get("payroll_kind"),
        "pay_run_ref": d.get("pay_run_ref"),
        "payroll_accrual": bool(d.get("payroll_accrual")),
        "amount_inc_cents": int(d.get("amount_inc_cents") or 0),
        "gst_cents": int(d.get("gst_cents") or 0),
        "is_deleted": bool(d.get("is_deleted")),
    }


class TxnFilters:
    def __init__(
        self,
        fy: Optional[str] = Query(None),
        month_key: Optional[str] = Query(None),
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        txn_type: Optional[str] = Query(None),
        category_id: Optional[str] = Query(None),
        subcategory_id: Optional[str] = Query(None),
        supplier_id: Optional[str] = Query(None),
        account_id: Optional[str] = Query(None),
        gst_treatment: Optional[str] = Query(None),
        receipt_status: Optional[str] = Query(None),
        reconcile_status: Optional[str] = Query(None),
        needs_review: Optional[bool] = Query(None),
        ask_accountant: Optional[bool] = Query(None),
        uncategorised: Optional[bool] = Query(None),
        tag: Optional[str] = Query(None),
        amount_min: Optional[float] = Query(None),
        amount_max: Optional[float] = Query(None),
        q: Optional[str] = Query(None),
    ):
        self.__dict__.update(locals())
        del self.__dict__["self"]


def build_filter(business_id: str, f: TxnFilters) -> dict:
    query: dict = {"business_id": business_id, "is_deleted": {"$ne": True}}
    if f.fy:
        query["fy"] = f.fy
    if f.month_key:
        query["month_key"] = f.month_key
    if f.date_from or f.date_to:
        rng = {}
        if f.date_from:
            rng["$gte"] = f.date_from
        if f.date_to:
            rng["$lte"] = f.date_to
        query["date"] = rng
    if f.txn_type:
        query["txn_type"] = {"$in": f.txn_type.split(",")}
    if f.category_id:
        query["category_id"] = f.category_id
    if f.subcategory_id:
        query["subcategory_id"] = f.subcategory_id
    if f.supplier_id:
        query["supplier_id"] = f.supplier_id
    if f.account_id:
        query["account_id"] = f.account_id
    if f.gst_treatment:
        query["gst_treatment"] = {"$in": f.gst_treatment.split(",")}
    if f.receipt_status == "missing":
        query["receipt_document_ids"] = {"$in": [None, []]}
    elif f.receipt_status == "attached":
        query["receipt_document_ids"] = {"$exists": True, "$ne": []}
    if f.reconcile_status:
        query["reconcile_status"] = f.reconcile_status
    if f.needs_review is not None:
        query["needs_review"] = f.needs_review
    if f.ask_accountant is not None:
        query["ask_accountant"] = f.ask_accountant
    if f.uncategorised:
        query["$or"] = [{"category_id": None}, {"category_id": ""}]
    if f.tag:
        query["tags"] = f.tag
    if f.amount_min is not None or f.amount_max is not None:
        rng = {}
        if f.amount_min is not None:
            rng["$gte"] = int(round(f.amount_min * 100))
        if f.amount_max is not None:
            rng["$lte"] = int(round(f.amount_max * 100))
        query["amount_inc_cents"] = rng
    if f.q:
        rx = {"$regex": f.q, "$options": "i"}
        query["$and"] = query.get("$and", []) + [{"$or": [
            {"description": rx}, {"supplier_name": rx}, {"reference": rx},
            {"notes": rx}, {"category_name": rx}, {"subcategory_name": rx},
        ]}]
    return query


async def sum_cents(query: dict, field: str = "amount_inc_cents") -> int:
    cur = db.transactions.aggregate([{"$match": query}, {"$group": {"_id": None, "t": {"$sum": f"${field}"}}}])
    rows = await cur.to_list(1)
    return rows[0]["t"] if rows else 0


async def group_by_month(query: dict, field: str = "amount_inc_cents") -> dict:
    cur = db.transactions.aggregate([
        {"$match": query},
        {"$group": {"_id": "$month_key", "t": {"$sum": f"${field}"}}},
    ])
    return {r["_id"]: r["t"] async for r in cur}


def fy_date_query(fy: str) -> dict:
    start, end = fy_bounds(fy)
    return {"$gte": start.isoformat(), "$lte": end.isoformat()}
