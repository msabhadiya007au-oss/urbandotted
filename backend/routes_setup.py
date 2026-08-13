"""Setup entities: business, categories, suppliers, accounts, products, demo data, backup."""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, to_dollars, current_fy, fy_options,
                  GST_LABELS, month_label)
from seed import load_demo_data, purge_demo_data, seed_default_setup

router = APIRouter(prefix="/api", tags=["setup"])


# ---------- meta ----------
@router.get("/meta")
async def meta(user: dict = Depends(get_current_user)):
    businesses = await db.businesses.find(
        {"business_id": {"$in": user.get("business_ids", [])}}, {"_id": 0}).to_list(50)
    return {
        "current_fy": current_fy(),
        "fy_options": fy_options(),
        "gst_treatments": [{"value": k, "label": v} for k, v in GST_LABELS.items()],
        "businesses": businesses,
        "phases": {
            "shopify": "Coming in Phase 4",
            "ad_platform_apis": "Coming in Phase 5",
            "bank_feeds": "Coming in Phase 5",
        },
    }


class BusinessIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    abn: str = ""
    gst_registered: bool = True
    default_gst_rate: str = "0.10"
    currency: str = "AUD"
    timezone: str = "Australia/Adelaide"


@router.get("/business")
async def get_business(business_id: str = Depends(get_business_id)):
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    return biz


@router.put("/business")
async def update_business(body: BusinessIn, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    before = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    await db.businesses.update_one({"business_id": business_id}, {"$set": body.model_dump()})
    await audit(business_id, user, "business", business_id, "update", before, body.model_dump())
    return await db.businesses.find_one({"business_id": business_id}, {"_id": 0})


@router.post("/business")
async def create_business(body: BusinessIn, user: dict = Depends(get_current_user)):
    bid = new_id("biz")
    await db.businesses.insert_one({
        "business_id": bid, "owner_user_id": user["user_id"], **body.model_dump(),
        "locale": "en-AU", "is_demo": False, "created_at": now_iso(),
    })
    await seed_default_setup(bid)
    await db.users.update_one({"user_id": user["user_id"]}, {"$push": {"business_ids": bid}})
    return await db.businesses.find_one({"business_id": bid}, {"_id": 0})


# ---------- categories ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[str] = None
    kind: str = "expense"


@router.get("/categories")
async def list_categories(include_archived: bool = False, kind: Optional[str] = None,
                          business_id: str = Depends(get_business_id)):
    q = {"business_id": business_id}
    if not include_archived:
        q["is_archived"] = False
    if kind:
        q["kind"] = kind
    cats = await db.categories.find(q, {"_id": 0}).sort("sort", 1).to_list(2000)
    by_parent = {}
    for c in cats:
        by_parent.setdefault(c.get("parent_id"), []).append(c)
    tree = []
    for parent in by_parent.get(None, []):
        tree.append({**parent, "children": by_parent.get(parent["category_id"], [])})
    return {"tree": tree, "flat": cats}


@router.post("/categories")
async def create_category(body: CategoryIn, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    if body.parent_id:
        parent = await db.categories.find_one({"business_id": business_id, "category_id": body.parent_id})
        if not parent:
            raise HTTPException(400, "Parent category not found")
    dup = await db.categories.find_one({"business_id": business_id, "name": body.name,
                                        "parent_id": body.parent_id})
    if dup:
        raise HTTPException(400, "A category with that name already exists here")
    count = await db.categories.count_documents({"business_id": business_id})
    doc = {"category_id": new_id("cat"), "business_id": business_id, "name": body.name,
           "parent_id": body.parent_id, "kind": body.kind, "is_archived": False,
           "sort": count + 1, "created_at": now_iso()}
    await db.categories.insert_one(doc)
    await audit(business_id, user, "category", doc["category_id"], "create", None, body.model_dump())
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/categories/{category_id}")
async def update_category(category_id: str, body: CategoryIn,
                          business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    before = await db.categories.find_one({"business_id": business_id, "category_id": category_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Category not found")
    await db.categories.update_one({"business_id": business_id, "category_id": category_id},
                                  {"$set": {"name": body.name, "kind": body.kind}})
    field = "subcategory_name" if before.get("parent_id") else "category_name"
    key = "subcategory_id" if before.get("parent_id") else "category_id"
    await db.transactions.update_many({"business_id": business_id, key: category_id},
                                      {"$set": {field: body.name}})
    await audit(business_id, user, "category", category_id, "update", before, body.model_dump())
    return await db.categories.find_one({"category_id": category_id}, {"_id": 0})


@router.post("/categories/{category_id}/archive")
async def archive_category(category_id: str, archived: bool = True,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    res = await db.categories.update_one({"business_id": business_id, "category_id": category_id},
                                         {"$set": {"is_archived": archived}})
    if not res.matched_count:
        raise HTTPException(404, "Category not found")
    await db.categories.update_many({"business_id": business_id, "parent_id": category_id},
                                    {"$set": {"is_archived": archived}})
    await audit(business_id, user, "category", category_id, "archive" if archived else "restore")
    return {"ok": True}


# ---------- suppliers ----------
class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    country: str = "Australia"
    abn: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    notes: str = ""


@router.get("/suppliers")
async def list_suppliers(include_archived: bool = False, q: Optional[str] = None,
                         business_id: str = Depends(get_business_id)):
    query = {"business_id": business_id}
    if not include_archived:
        query["is_archived"] = False
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    return await db.suppliers.find(query, {"_id": 0}).sort("name", 1).to_list(1000)


@router.post("/suppliers")
async def create_supplier(body: SupplierIn, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    doc = {"supplier_id": new_id("sup"), "business_id": business_id, **body.model_dump(),
           "is_archived": False, "created_at": now_iso()}
    await db.suppliers.insert_one(doc)
    await audit(business_id, user, "supplier", doc["supplier_id"], "create", None, body.model_dump())
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, body: SupplierIn,
                          business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    before = await db.suppliers.find_one({"business_id": business_id, "supplier_id": supplier_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Supplier not found")
    await db.suppliers.update_one({"business_id": business_id, "supplier_id": supplier_id},
                                 {"$set": body.model_dump()})
    await db.transactions.update_many({"business_id": business_id, "supplier_id": supplier_id},
                                      {"$set": {"supplier_name": body.name}})
    await audit(business_id, user, "supplier", supplier_id, "update", before, body.model_dump())
    return await db.suppliers.find_one({"supplier_id": supplier_id}, {"_id": 0})


@router.post("/suppliers/{supplier_id}/archive")
async def archive_supplier(supplier_id: str, archived: bool = True,
                           business_id: str = Depends(get_business_id)):
    await db.suppliers.update_one({"business_id": business_id, "supplier_id": supplier_id},
                                 {"$set": {"is_archived": archived}})
    return {"ok": True}


@router.get("/suppliers/{supplier_id}/detail")
async def supplier_detail(supplier_id: str, fy: Optional[str] = None,
                          business_id: str = Depends(get_business_id)):
    sup = await db.suppliers.find_one({"business_id": business_id, "supplier_id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(404, "Supplier not found")
    fy = fy or current_fy()
    q = {"business_id": business_id, "supplier_id": supplier_id, "fy": fy, "is_deleted": {"$ne": True}}
    txns = await db.transactions.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "supplier_id": supplier_id, "fy": fy, "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("date", -1).to_list(500)
    monthly = {}
    for t in txns:
        monthly.setdefault(t["month_key"], 0)
        monthly[t["month_key"]] += t.get("amount_inc_cents", 0)
    from queries import txn_out
    return {
        "supplier": sup,
        "fy": fy,
        "total_spent": to_dollars(sum(t.get("amount_inc_cents", 0) for t in txns)),
        "total_gst": to_dollars(sum(t.get("gst_cents", 0) for t in txns)),
        "transaction_count": len(txns),
        "invoice_count": len([t for t in txns if t.get("reference")]),
        "inventory_purchase_total": to_dollars(sum(p.get("total_cost_cents", 0) for p in purchases)),
        "inventory_purchases": [{**p, "total_cost": to_dollars(p.get("total_cost_cents"))} for p in purchases],
        "monthly": [{"month_key": k, "month_label": month_label(k), "amount": to_dollars(v)}
                    for k, v in sorted(monthly.items())],
        "transactions": [txn_out(t) for t in txns],
    }


# ---------- payment accounts ----------
class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = "other"


@router.get("/accounts")
async def list_accounts(business_id: str = Depends(get_business_id)):
    return await db.payment_accounts.find({"business_id": business_id, "is_archived": False},
                                          {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/accounts")
async def create_account(body: AccountIn, business_id: str = Depends(get_business_id)):
    doc = {"account_id": new_id("acct"), "business_id": business_id, **body.model_dump(),
           "is_archived": False, "created_at": now_iso()}
    await db.payment_accounts.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, body: AccountIn, business_id: str = Depends(get_business_id)):
    await db.payment_accounts.update_one({"business_id": business_id, "account_id": account_id},
                                         {"$set": body.model_dump()})
    await db.transactions.update_many({"business_id": business_id, "account_id": account_id},
                                      {"$set": {"account_name": body.name}})
    return await db.payment_accounts.find_one({"account_id": account_id}, {"_id": 0})


@router.post("/accounts/{account_id}/archive")
async def archive_account(account_id: str, business_id: str = Depends(get_business_id)):
    await db.payment_accounts.update_one({"business_id": business_id, "account_id": account_id},
                                         {"$set": {"is_archived": True}})
    return {"ok": True}


# ---------- products ----------
class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)


@router.get("/products")
async def list_products(business_id: str = Depends(get_business_id)):
    return await db.products.find({"business_id": business_id, "is_archived": False},
                                  {"_id": 0}).sort("sku", 1).to_list(1000)


@router.post("/products")
async def create_product(body: ProductIn, business_id: str = Depends(get_business_id)):
    if await db.products.find_one({"business_id": business_id, "sku": body.sku}):
        raise HTTPException(400, "SKU already exists")
    doc = {"product_id": new_id("prod"), "business_id": business_id, **body.model_dump(),
           "is_archived": False, "created_at": now_iso()}
    await db.products.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


# ---------- demo data ----------
@router.post("/demo/load")
async def demo_load(business_id: str = Depends(get_business_id), user: dict = Depends(get_current_user)):
    result = await load_demo_data(business_id, user)
    await audit(business_id, user, "demo", business_id, "load_demo_data")
    return result


@router.delete("/demo/purge")
async def demo_purge(business_id: str = Depends(get_business_id), user: dict = Depends(get_current_user)):
    result = await purge_demo_data(business_id)
    await audit(business_id, user, "demo", business_id, "purge_demo_data")
    return result


@router.get("/demo/status")
async def demo_status(business_id: str = Depends(get_business_id)):
    count = await db.transactions.count_documents({"business_id": business_id, "is_demo": True})
    return {"has_demo_data": count > 0, "demo_transaction_count": count}


# ---------- audit log ----------
@router.get("/audit-logs")
async def audit_logs(limit: int = Query(100, le=500), business_id: str = Depends(get_business_id)):
    return await db.audit_logs.find({"business_id": business_id}, {"_id": 0}) \
        .sort("at", -1).to_list(limit)


# ---------- integrations registry ----------
@router.get("/integrations")
async def integrations(business_id: str = Depends(get_business_id)):
    providers = [
        {"provider": "shopify", "label": "Shopify", "status": "not_connected", "phase": "Coming in Phase 4"},
        {"provider": "meta_ads", "label": "Meta Ads", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "google_ads", "label": "Google Ads", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "tiktok_ads", "label": "TikTok Ads", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "snapchat_ads", "label": "Snapchat Ads", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "bank_feeds", "label": "Bank Feeds", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "paypal", "label": "PayPal", "status": "not_connected", "phase": "Coming in Phase 5"},
        {"provider": "stripe", "label": "Stripe", "status": "not_connected", "phase": "Coming in Phase 5"},
    ]
    return {"providers": providers,
            "note": "Manual entry and CSV import always remain available."}


# ---------- backup / restore ----------
@router.get("/backup/export")
async def backup_export(business_id: str = Depends(get_business_id)):
    out = {"business_id": business_id, "exported_at": now_iso(), "collections": {}}
    for name, coll in [("businesses", db.businesses), ("categories", db.categories),
                       ("suppliers", db.suppliers), ("payment_accounts", db.payment_accounts),
                       ("products", db.products), ("transactions", db.transactions),
                       ("inventory_purchases", db.inventory_purchases), ("assets", db.assets),
                       ("cogs_entries", db.cogs_entries), ("documents", db.documents),
                       ("recurring_templates", db.recurring_templates),
                       ("reminders", db.reminders), ("month_end_checks", db.month_end_checks)]:
        out["collections"][name] = await coll.find({"business_id": business_id}, {"_id": 0}).to_list(20000)
    return out
