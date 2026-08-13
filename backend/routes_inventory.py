"""Inventory purchases, COGS engine, assets."""
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, to_cents, to_dollars, compute_gst,
                  fy_of, month_key_of, parse_date, month_label, fy_month_keys, current_fy)

router = APIRouter(prefix="/api", tags=["inventory"])


# ---------------- inventory ----------------
class PurchaseIn(BaseModel):
    date: str
    supplier_id: Optional[str] = None
    product_id: Optional[str] = None
    sku: str = ""
    description: str = ""
    qty: int = Field(gt=0)
    unit_cost: float = Field(ge=0)
    freight: float = 0
    customs: float = 0
    import_gst: float = 0
    other_landed: float = 0
    reference: str = ""
    notes: str = ""
    receipt_document_ids: List[str] = []

    @field_validator("date")
    @classmethod
    def _d(cls, v):
        return parse_date(v).isoformat()


def _purchase_totals(b: PurchaseIn):
    goods = to_cents(Decimal(str(b.unit_cost)) * Decimal(b.qty))
    total = goods + to_cents(b.freight) + to_cents(b.customs) + to_cents(b.import_gst) + to_cents(b.other_landed)
    landed_unit = int(round(total / b.qty)) if b.qty else 0
    return goods, total, landed_unit


def purchase_out(p: dict) -> dict:
    return {
        "purchase_id": p["purchase_id"], "date": p["date"], "fy": p["fy"],
        "month_key": p["month_key"], "month_label": month_label(p["month_key"]),
        "supplier_id": p.get("supplier_id"), "supplier_name": p.get("supplier_name"),
        "product_id": p.get("product_id"), "sku": p.get("sku", ""),
        "description": p.get("description", ""), "qty": p.get("qty", 0),
        "unit_cost": to_dollars(p.get("unit_cost_cents")),
        "freight": to_dollars(p.get("freight_cents")),
        "customs": to_dollars(p.get("customs_cents")),
        "import_gst": to_dollars(p.get("import_gst_cents")),
        "other_landed": to_dollars(p.get("other_cents")),
        "total_cost": to_dollars(p.get("total_cost_cents")),
        "landed_unit_cost": to_dollars(p.get("landed_unit_cost_cents")),
        "qty_sold": p.get("qty_sold", 0),
        "qty_remaining": p.get("qty", 0) - p.get("qty_sold", 0),
        "reference": p.get("reference", ""), "notes": p.get("notes", ""),
        "receipt_document_ids": p.get("receipt_document_ids", []),
        "has_receipt": bool(p.get("receipt_document_ids")),
        "is_demo": bool(p.get("is_demo")),
        "created_at": p.get("created_at"),
    }


@router.get("/inventory/purchases")
async def list_purchases(fy: Optional[str] = None, sku: Optional[str] = None,
                         supplier_id: Optional[str] = None,
                         business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id, "is_deleted": {"$ne": True}}
    if fy:
        q["fy"] = fy
    if sku:
        q["sku"] = sku
    if supplier_id:
        q["supplier_id"] = supplier_id
    docs = await db.inventory_purchases.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    return {
        "items": [purchase_out(d) for d in docs],
        "totals": {
            "purchase_total": to_dollars(sum(d.get("total_cost_cents", 0) for d in docs)),
            "import_gst": to_dollars(sum(d.get("import_gst_cents", 0) for d in docs)),
            "units_purchased": sum(d.get("qty", 0) for d in docs),
            "units_sold": sum(d.get("qty_sold", 0) for d in docs),
            "units_remaining": sum(d.get("qty", 0) - d.get("qty_sold", 0) for d in docs),
        },
    }


@router.post("/inventory/purchases")
async def create_purchase(body: PurchaseIn, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    supplier_name = None
    if body.supplier_id:
        sup = await db.suppliers.find_one({"business_id": business_id, "supplier_id": body.supplier_id}, {"_id": 0})
        if not sup:
            raise HTTPException(400, "Invalid supplier")
        supplier_name = sup["name"]
    goods, total, landed_unit = _purchase_totals(body)
    doc = {
        "purchase_id": new_id("inv"), "business_id": business_id, "date": body.date,
        "fy": fy_of(body.date), "month_key": month_key_of(body.date),
        "supplier_id": body.supplier_id, "supplier_name": supplier_name,
        "product_id": body.product_id, "sku": body.sku, "description": body.description,
        "qty": body.qty, "unit_cost_cents": to_cents(body.unit_cost),
        "freight_cents": to_cents(body.freight), "customs_cents": to_cents(body.customs),
        "import_gst_cents": to_cents(body.import_gst), "other_cents": to_cents(body.other_landed),
        "goods_cents": goods, "total_cost_cents": total, "landed_unit_cost_cents": landed_unit,
        "qty_sold": 0, "reference": body.reference, "notes": body.notes,
        "receipt_document_ids": body.receipt_document_ids, "is_deleted": False, "is_demo": False,
        "created_at": now_iso(), "created_by": user["email"], "updated_at": now_iso(),
    }
    await db.inventory_purchases.insert_one(doc)
    await audit(business_id, user, "inventory_purchase", doc["purchase_id"], "create", None, purchase_out(doc))
    return purchase_out(doc)


@router.put("/inventory/purchases/{purchase_id}")
async def update_purchase(purchase_id: str, body: PurchaseIn,
                          business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    before = await db.inventory_purchases.find_one({"business_id": business_id, "purchase_id": purchase_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Purchase not found")
    supplier_name = None
    if body.supplier_id:
        sup = await db.suppliers.find_one({"business_id": business_id, "supplier_id": body.supplier_id}, {"_id": 0})
        supplier_name = sup["name"] if sup else None
    goods, total, landed_unit = _purchase_totals(body)
    upd = {
        "date": body.date, "fy": fy_of(body.date), "month_key": month_key_of(body.date),
        "supplier_id": body.supplier_id, "supplier_name": supplier_name,
        "product_id": body.product_id, "sku": body.sku, "description": body.description,
        "qty": body.qty, "unit_cost_cents": to_cents(body.unit_cost),
        "freight_cents": to_cents(body.freight), "customs_cents": to_cents(body.customs),
        "import_gst_cents": to_cents(body.import_gst), "other_cents": to_cents(body.other_landed),
        "goods_cents": goods, "total_cost_cents": total, "landed_unit_cost_cents": landed_unit,
        "reference": body.reference, "notes": body.notes,
        "receipt_document_ids": body.receipt_document_ids,
        "updated_at": now_iso(), "updated_by": user["email"],
    }
    await db.inventory_purchases.update_one({"business_id": business_id, "purchase_id": purchase_id}, {"$set": upd})
    after = await db.inventory_purchases.find_one({"purchase_id": purchase_id}, {"_id": 0})
    await audit(business_id, user, "inventory_purchase", purchase_id, "update", purchase_out(before), purchase_out(after))
    return purchase_out(after)


@router.delete("/inventory/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    await db.inventory_purchases.update_one({"business_id": business_id, "purchase_id": purchase_id},
                                           {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(business_id, user, "inventory_purchase", purchase_id, "soft_delete")
    return {"ok": True}


# ---------------- COGS engine ----------------
async def compute_cogs(business_id: str, fy: str):
    """Weighted-average landed unit cost consumption per SKU, FIFO across purchases.

    COGS is recognised when units SELL, never when inventory is purchased.
    """
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "is_deleted": {"$ne": True}}, {"_id": 0}).sort("date", 1).to_list(5000)
    sales = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "txn_type": "sale", "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("date", 1).to_list(5000)
    manual = await db.cogs_entries.find(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)

    # available pools per SKU (FIFO)
    pools = {}
    for p in purchases:
        sku = p.get("sku") or "UNKNOWN"
        pools.setdefault(sku, []).append({
            "purchase_id": p["purchase_id"], "date": p["date"], "qty": p.get("qty", 0),
            "remaining": p.get("qty", 0), "landed": p.get("landed_unit_cost_cents", 0)})

    monthly = {k: {"month_key": k, "month_label": month_label(k), "cogs_cents": 0,
                   "units": 0, "lines": []} for k in fy_month_keys(fy)}
    unmatched_units = 0

    for s in sales:
        mk = s["month_key"]
        if mk not in monthly:
            continue
        for item in s.get("items") or []:
            sku = item.get("sku") or "UNKNOWN"
            qty = int(item.get("qty") or 0)
            if qty <= 0:
                continue
            pool = pools.get(sku, [])
            need = qty
            for lot in pool:
                if need <= 0:
                    break
                take = min(lot["remaining"], need)
                if take <= 0:
                    continue
                lot["remaining"] -= take
                need -= take
                cost = take * lot["landed"]
                monthly[mk]["cogs_cents"] += cost
                monthly[mk]["units"] += take
                monthly[mk]["lines"].append({
                    "source": "auto", "sku": sku, "qty": take,
                    "unit_cost": to_dollars(lot["landed"]), "amount": to_dollars(cost),
                    "purchase_id": lot["purchase_id"], "txn_id": s["txn_id"],
                    "description": s.get("description", "")})
            if need > 0:
                unmatched_units += need

    for m in manual:
        mk = m["month_key"]
        if mk not in monthly:
            continue
        monthly[mk]["cogs_cents"] += m.get("amount_cents", 0)
        monthly[mk]["units"] += m.get("qty", 0)
        monthly[mk]["lines"].append({
            "source": "manual", "sku": m.get("sku", ""), "qty": m.get("qty", 0),
            "unit_cost": to_dollars(m.get("unit_cost_cents")),
            "amount": to_dollars(m.get("amount_cents")),
            "description": m.get("description", ""), "cogs_id": m["cogs_id"]})

    months = []
    for k in fy_month_keys(fy):
        m = monthly[k]
        months.append({"month_key": k, "month_label": m["month_label"],
                       "cogs": to_dollars(m["cogs_cents"]), "units": m["units"],
                       "lines": m["lines"]})
    inventory_on_hand_cents = sum(l["remaining"] * l["landed"] for pool in pools.values() for l in pool)
    return {
        "fy": fy,
        "months": months,
        "total_cogs": to_dollars(sum(m["cogs_cents"] for m in monthly.values())),
        "total_units": sum(m["units"] for m in monthly.values()),
        "inventory_on_hand_value": to_dollars(inventory_on_hand_cents),
        "units_on_hand": sum(l["remaining"] for pool in pools.values() for l in pool),
        "unmatched_units_sold": unmatched_units,
        "methodology": ("COGS is recognised when units sell, consuming inventory lots in purchase "
                        "order (FIFO) at each lot's landed unit cost (goods + freight + customs + "
                        "import GST + other landed costs) / quantity. Inventory purchases are NOT "
                        "treated as the cost of goods sold in the month of purchase."),
    }


@router.get("/cogs")
async def cogs_report(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    return await compute_cogs(business_id, fy or current_fy())


class CogsIn(BaseModel):
    month_key: str
    amount: float = Field(gt=0)
    sku: str = ""
    qty: int = 0
    description: str = ""


@router.post("/cogs/manual")
async def create_manual_cogs(body: CogsIn, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    y, m = body.month_key.split("-")
    from datetime import date as _date
    d = _date(int(y), int(m), 1)
    doc = {
        "cogs_id": new_id("cogs"), "business_id": business_id, "month_key": body.month_key,
        "fy": fy_of(d), "source": "manual", "sku": body.sku, "qty": body.qty,
        "unit_cost_cents": to_cents(body.amount / body.qty) if body.qty else 0,
        "amount_cents": to_cents(body.amount), "description": body.description,
        "is_deleted": False, "is_demo": False, "created_at": now_iso(), "created_by": user["email"],
    }
    await db.cogs_entries.insert_one(doc)
    await audit(business_id, user, "cogs_entry", doc["cogs_id"], "create")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.delete("/cogs/manual/{cogs_id}")
async def delete_manual_cogs(cogs_id: str, business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    await db.cogs_entries.update_one({"business_id": business_id, "cogs_id": cogs_id},
                                    {"$set": {"is_deleted": True}})
    await audit(business_id, user, "cogs_entry", cogs_id, "soft_delete")
    return {"ok": True}


# ---------------- assets ----------------
class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    date: str
    supplier_id: Optional[str] = None
    invoice: str = ""
    price: float = Field(gt=0)
    gst_treatment: str = "gst_included"
    gst_rate: Optional[str] = None
    serial: str = ""
    asset_category: str = ""
    business_use_pct: int = Field(default=100, ge=0, le=100)
    status: str = "in_use"
    notes: str = ""
    receipt_document_ids: List[str] = []
    needs_review: bool = False

    @field_validator("date")
    @classmethod
    def _d(cls, v):
        return parse_date(v).isoformat()


def asset_out(a: dict) -> dict:
    return {
        "asset_id": a["asset_id"], "name": a["name"], "date": a["date"], "fy": a["fy"],
        "month_label": month_label(a["month_key"]),
        "supplier_id": a.get("supplier_id"), "supplier_name": a.get("supplier_name"),
        "invoice": a.get("invoice", ""),
        "price_ex": to_dollars(a.get("price_ex_cents")), "gst": to_dollars(a.get("gst_cents")),
        "price_inc": to_dollars(a.get("price_inc_cents")),
        "gst_treatment": a.get("gst_treatment"), "serial": a.get("serial", ""),
        "asset_category": a.get("asset_category", ""),
        "business_use_pct": a.get("business_use_pct", 100),
        "status": a.get("status", "in_use"), "notes": a.get("notes", ""),
        "receipt_document_ids": a.get("receipt_document_ids", []),
        "has_receipt": bool(a.get("receipt_document_ids")),
        "needs_review": bool(a.get("needs_review")), "is_demo": bool(a.get("is_demo")),
        "created_at": a.get("created_at"),
    }


@router.get("/assets")
async def list_assets(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id, "is_deleted": {"$ne": True}}
    if fy:
        q["fy"] = fy
    docs = await db.assets.find(q, {"_id": 0}).sort("date", -1).to_list(1000)
    return {
        "items": [asset_out(d) for d in docs],
        "totals": {
            "count": len(docs),
            "price_inc": to_dollars(sum(d.get("price_inc_cents", 0) for d in docs)),
            "price_ex": to_dollars(sum(d.get("price_ex_cents", 0) for d in docs)),
            "gst": to_dollars(sum(d.get("gst_cents", 0) for d in docs)),
            "needs_review": len([d for d in docs if d.get("needs_review")]),
        },
        "disclaimer": ("This is an asset register only. Depreciation, instant asset write-off and "
                       "deductibility are not determined by this application — flag items for "
                       "accountant review."),
    }


@router.post("/assets")
async def create_asset(body: AssetIn, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    supplier_name = None
    if body.supplier_id:
        sup = await db.suppliers.find_one({"business_id": business_id, "supplier_id": body.supplier_id}, {"_id": 0})
        supplier_name = sup["name"] if sup else None
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    ex, gst, inc, review = compute_gst(body.price, body.gst_treatment, body.gst_rate, True,
                                       (biz or {}).get("default_gst_rate", "0.10"))
    doc = {
        "asset_id": new_id("ast"), "business_id": business_id, "name": body.name,
        "date": body.date, "fy": fy_of(body.date), "month_key": month_key_of(body.date),
        "supplier_id": body.supplier_id, "supplier_name": supplier_name,
        "invoice": body.invoice, "price_ex_cents": ex, "gst_cents": gst, "price_inc_cents": inc,
        "gst_treatment": body.gst_treatment, "serial": body.serial,
        "asset_category": body.asset_category, "business_use_pct": body.business_use_pct,
        "status": body.status, "notes": body.notes,
        "receipt_document_ids": body.receipt_document_ids,
        "needs_review": body.needs_review or review, "is_deleted": False, "is_demo": False,
        "created_at": now_iso(), "created_by": user["email"], "updated_at": now_iso(),
    }
    await db.assets.insert_one(doc)
    await audit(business_id, user, "asset", doc["asset_id"], "create", None, asset_out(doc))
    return asset_out(doc)


@router.put("/assets/{asset_id}")
async def update_asset(asset_id: str, body: AssetIn, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    before = await db.assets.find_one({"business_id": business_id, "asset_id": asset_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Asset not found")
    supplier_name = None
    if body.supplier_id:
        sup = await db.suppliers.find_one({"business_id": business_id, "supplier_id": body.supplier_id}, {"_id": 0})
        supplier_name = sup["name"] if sup else None
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    ex, gst, inc, review = compute_gst(body.price, body.gst_treatment, body.gst_rate, True,
                                       (biz or {}).get("default_gst_rate", "0.10"))
    upd = {
        "name": body.name, "date": body.date, "fy": fy_of(body.date),
        "month_key": month_key_of(body.date), "supplier_id": body.supplier_id,
        "supplier_name": supplier_name, "invoice": body.invoice, "price_ex_cents": ex,
        "gst_cents": gst, "price_inc_cents": inc, "gst_treatment": body.gst_treatment,
        "serial": body.serial, "asset_category": body.asset_category,
        "business_use_pct": body.business_use_pct, "status": body.status, "notes": body.notes,
        "receipt_document_ids": body.receipt_document_ids,
        "needs_review": body.needs_review or review,
        "updated_at": now_iso(), "updated_by": user["email"],
    }
    await db.assets.update_one({"business_id": business_id, "asset_id": asset_id}, {"$set": upd})
    after = await db.assets.find_one({"asset_id": asset_id}, {"_id": 0})
    await audit(business_id, user, "asset", asset_id, "update", asset_out(before), asset_out(after))
    return asset_out(after)


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str, business_id: str = Depends(get_business_id),
                       user: dict = Depends(get_current_user)):
    await db.assets.update_one({"business_id": business_id, "asset_id": asset_id},
                              {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(business_id, user, "asset", asset_id, "soft_delete")
    return {"ok": True}
