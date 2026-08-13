"""Documents vault (object storage), recurring templates, reminders, month/year-end checklists."""
from typing import Optional, List
from datetime import datetime, timezone, timedelta, date

from fastapi import (APIRouter, Depends, HTTPException, UploadFile, File, Form,
                     Query, Header, Response)
from pydantic import BaseModel, Field

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, to_cents, to_dollars, fy_of, month_key_of,
                  month_label, fy_month_keys, current_fy)
from storage import put_object, get_object, MIME_TYPES, ALLOWED_EXT, MAX_SIZE, APP_NAME
from seed import MONTH_END_ITEMS

router = APIRouter(prefix="/api", tags=["ops"])


# ---------------- documents ----------------
@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    linked_type: Optional[str] = Form(None),
    linked_id: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    supplier_id: Optional[str] = Form(None),
    doc_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    business_id: str = Depends(get_business_id),
    user: dict = Depends(get_current_user),
):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 10MB)")
    if not data:
        raise HTTPException(400, "Empty file")

    doc_id = new_id("doc")
    path = f"{APP_NAME}/{business_id}/receipts/{doc_id}.{ext}"
    content_type = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        raise HTTPException(502, f"Upload failed: {e}")

    d = doc_date or datetime.now(timezone.utc).date().isoformat()
    doc = {
        "document_id": doc_id, "business_id": business_id, "storage_path": result["path"],
        "filename": file.filename, "content_type": content_type, "size": result.get("size", len(data)),
        "linked_type": linked_type, "linked_id": linked_id, "category_id": category_id,
        "supplier_id": supplier_id, "date": d, "fy": fy_of(d), "month_key": month_key_of(d),
        "notes": notes or "", "is_deleted": False, "is_demo": False,
        "created_at": now_iso(), "created_by": user["email"],
    }
    await db.documents.insert_one(doc)

    if linked_type == "transaction" and linked_id:
        await db.transactions.update_one({"business_id": business_id, "txn_id": linked_id},
                                        {"$addToSet": {"receipt_document_ids": doc_id}})
    elif linked_type == "inventory_purchase" and linked_id:
        await db.inventory_purchases.update_one({"business_id": business_id, "purchase_id": linked_id},
                                              {"$addToSet": {"receipt_document_ids": doc_id}})
    elif linked_type == "asset" and linked_id:
        await db.assets.update_one({"business_id": business_id, "asset_id": linked_id},
                                  {"$addToSet": {"receipt_document_ids": doc_id}})
    await audit(business_id, user, "document", doc_id, "upload")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/documents")
async def list_documents(fy: Optional[str] = None, month_key: Optional[str] = None,
                         supplier_id: Optional[str] = None, category_id: Optional[str] = None,
                         linked_type: Optional[str] = None, q: Optional[str] = None,
                         business_id: str = Depends(get_business_id)):
    query = {"business_id": business_id, "is_deleted": False}
    if fy:
        query["fy"] = fy
    if month_key:
        query["month_key"] = month_key
    if supplier_id:
        query["supplier_id"] = supplier_id
    if category_id:
        query["category_id"] = category_id
    if linked_type:
        query["linked_type"] = linked_type
    if q:
        query["$or"] = [{"filename": {"$regex": q, "$options": "i"}},
                        {"notes": {"$regex": q, "$options": "i"}}]
    docs = await db.documents.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"items": docs, "total": len(docs)}


@router.get("/documents/{document_id}/download")
async def download_document(document_id: str, business_id: str = Depends(get_business_id)):
    rec = await db.documents.find_one({"business_id": business_id, "document_id": document_id,
                                      "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Document not found")
    try:
        data, content_type = get_object(rec["storage_path"])
    except Exception as e:
        raise HTTPException(502, f"Download failed: {e}")
    return Response(content=data, media_type=rec.get("content_type", content_type),
                    headers={"Content-Disposition": f'inline; filename="{rec["filename"]}"'})


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    await db.documents.update_one({"business_id": business_id, "document_id": document_id},
                                 {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await db.transactions.update_many({"business_id": business_id},
                                      {"$pull": {"receipt_document_ids": document_id}})
    await audit(business_id, user, "document", document_id, "soft_delete")
    return {"ok": True}


@router.get("/documents/missing-receipts")
async def missing_receipts(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    from queries import txn_out
    txns = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "txn_type": {"$in": ["expense", "refund"]},
         "receipt_document_ids": {"$in": [None, []]}, "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("date", -1).to_list(3000)
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "fy": fy, "receipt_document_ids": {"$in": [None, []]},
         "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    assets = await db.assets.find(
        {"business_id": business_id, "fy": fy, "receipt_document_ids": {"$in": [None, []]},
         "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    return {
        "fy": fy,
        "transactions": [txn_out(t) for t in txns],
        "inventory_purchases": [{"purchase_id": p["purchase_id"], "date": p["date"],
                                 "sku": p.get("sku"), "supplier_name": p.get("supplier_name"),
                                 "total_cost": to_dollars(p.get("total_cost_cents"))} for p in purchases],
        "assets": [{"asset_id": a["asset_id"], "name": a["name"], "date": a["date"],
                    "price_inc": to_dollars(a.get("price_inc_cents"))} for a in assets],
        "count": len(txns) + len(purchases) + len(assets),
        "total_amount": to_dollars(sum(t.get("amount_inc_cents", 0) for t in txns)),
    }


# ---------------- recurring templates ----------------
class RecurringIn(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    supplier_id: Optional[str] = None
    account_id: Optional[str] = None
    frequency: str = "monthly"
    expected_amount: Optional[float] = None
    variable: bool = False
    gst_treatment: str = "gst_included"
    is_active: bool = True
    start_month: Optional[str] = None
    custom_months: int = 1


def recurring_out(t: dict) -> dict:
    return {**t, "expected_amount": to_dollars(t.get("expected_amount_cents"))
            if t.get("expected_amount_cents") is not None else None}


@router.get("/recurring")
async def list_recurring(business_id: str = Depends(get_business_id)):
    docs = await db.recurring_templates.find({"business_id": business_id}, {"_id": 0}).sort("name", 1).to_list(500)
    return [recurring_out(d) for d in docs]


async def _resolve_names(business_id, body: RecurringIn):
    out = {}
    for key, coll, idf, namef in [("category_id", db.categories, "category_id", "category_name"),
                                  ("subcategory_id", db.categories, "category_id", "subcategory_name"),
                                  ("supplier_id", db.suppliers, "supplier_id", "supplier_name"),
                                  ("account_id", db.payment_accounts, "account_id", "account_name")]:
        val = getattr(body, key)
        doc = await coll.find_one({"business_id": business_id, idf: val}, {"_id": 0}) if val else None
        out[namef] = doc["name"] if doc else None
    return out


@router.post("/recurring")
async def create_recurring(body: RecurringIn, business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    doc = {
        "template_id": new_id("rec"), "business_id": business_id, **body.model_dump(exclude={"expected_amount"}),
        "expected_amount_cents": to_cents(body.expected_amount) if body.expected_amount else None,
        "start_month": body.start_month or month_key_of(datetime.now(timezone.utc).date()),
        "is_demo": False, "created_at": now_iso(), "created_by": user["email"],
    }
    doc.update(await _resolve_names(business_id, body))
    await db.recurring_templates.insert_one(doc)
    await audit(business_id, user, "recurring_template", doc["template_id"], "create")
    return recurring_out({k: v for k, v in doc.items() if k != "_id"})


@router.put("/recurring/{template_id}")
async def update_recurring(template_id: str, body: RecurringIn,
                           business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    upd = {**body.model_dump(exclude={"expected_amount"}),
           "expected_amount_cents": to_cents(body.expected_amount) if body.expected_amount else None}
    upd.update(await _resolve_names(business_id, body))
    res = await db.recurring_templates.update_one(
        {"business_id": business_id, "template_id": template_id}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Template not found")
    await audit(business_id, user, "recurring_template", template_id, "update")
    return recurring_out(await db.recurring_templates.find_one({"template_id": template_id}, {"_id": 0}))


@router.delete("/recurring/{template_id}")
async def delete_recurring(template_id: str, business_id: str = Depends(get_business_id),
                           user: dict = Depends(get_current_user)):
    await db.recurring_templates.delete_one({"business_id": business_id, "template_id": template_id})
    await audit(business_id, user, "recurring_template", template_id, "delete")
    return {"ok": True}


# ---------------- reminders engine ----------------
FREQ_STEP = {"monthly": 1, "quarterly": 3, "annually": 12}


def _expected_months(fy: str, frequency: str, start_month: Optional[str], custom_months: int = 1):
    months = fy_month_keys(fy)
    today_mk = month_key_of(datetime.now(timezone.utc).date())
    months = [m for m in months if m <= today_mk]
    if start_month:
        months = [m for m in months if m >= start_month]
    step = FREQ_STEP.get(frequency, max(1, custom_months))
    if step == 1:
        return months
    if not months:
        return []
    return [m for i, m in enumerate(months) if i % step == 0]


@router.post("/reminders/scan")
async def scan_reminders(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    created = 0
    templates = await db.recurring_templates.find(
        {"business_id": business_id, "is_active": True}, {"_id": 0}).to_list(500)

    # drop reminders whose recurring template no longer exists (e.g. demo data reloaded),
    # otherwise a re-scan would create a second reminder for the same month.
    live_keys = {f"tmpl:{t['template_id']}" for t in templates}
    await db.reminders.delete_many({
        "business_id": business_id, "kind": "missing_recurring",
        "key": {"$nin": list(live_keys)} if live_keys else {"$regex": "^tmpl:"},
    })

    for t in templates:
        for mk in _expected_months(fy, t.get("frequency", "monthly"), t.get("start_month"),
                                   t.get("custom_months", 1)):
            match = {"business_id": business_id, "month_key": mk, "is_deleted": {"$ne": True}}
            if t.get("subcategory_id"):
                match["subcategory_id"] = t["subcategory_id"]
            elif t.get("category_id"):
                match["category_id"] = t["category_id"]
            else:
                continue
            exists = await db.transactions.find_one(match)
            key = f"tmpl:{t['template_id']}"
            existing_reminder = await db.reminders.find_one(
                {"business_id": business_id, "key": key, "month_key": mk}, {"_id": 0})
            if exists:
                if existing_reminder and existing_reminder["status"] == "open":
                    await db.reminders.update_one({"reminder_id": existing_reminder["reminder_id"]},
                                                 {"$set": {"status": "completed"}})
                continue
            if existing_reminder:
                continue
            label = t["name"]
            await db.reminders.insert_one({
                "reminder_id": new_id("rem"), "business_id": business_id, "key": key,
                "template_id": t["template_id"], "category_id": t.get("category_id"),
                "subcategory_id": t.get("subcategory_id"), "fy": fy, "month_key": mk,
                "kind": "missing_recurring",
                "message": f"{label} — {month_label(mk)} entry missing",
                "expected_amount_cents": t.get("expected_amount_cents"),
                "status": "open", "snooze_until": None, "created_at": now_iso(), "is_demo": False,
            })
            created += 1

    # pattern detection: categories with >=3 months of history missing a month
    cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "txn_type": "expense",
                    "is_deleted": {"$ne": True}}},
        {"$group": {"_id": {"cat": "$category_id", "sub": "$subcategory_id",
                            "name": {"$ifNull": ["$subcategory_name", "$category_name"]}},
                    "months": {"$addToSet": "$month_key"}}},
    ])
    today_mk = month_key_of(datetime.now(timezone.utc).date())
    elapsed = [m for m in fy_month_keys(fy) if m <= today_mk]
    async for r in cur:
        seen = set(r["months"])
        if len(seen) < 3:
            continue
        first = min(seen)
        expected = [m for m in elapsed if m >= first]
        missing = [m for m in expected if m not in seen]
        for mk in missing:
            key = f"pattern:{r['_id'].get('sub') or r['_id'].get('cat')}"
            if await db.reminders.find_one({"business_id": business_id, "key": key, "month_key": mk}):
                continue
            await db.reminders.insert_one({
                "reminder_id": new_id("rem"), "business_id": business_id, "key": key,
                "template_id": None, "category_id": r["_id"].get("cat"),
                "subcategory_id": r["_id"].get("sub"), "fy": fy, "month_key": mk,
                "kind": "detected_pattern",
                "message": f"{r['_id'].get('name') or 'Expense'} normally recorded monthly — {month_label(mk)} missing",
                "expected_amount_cents": None, "status": "open", "snooze_until": None,
                "created_at": now_iso(), "is_demo": False,
            })
            created += 1
    return {"ok": True, "created": created}


@router.get("/reminders")
async def list_reminders(fy: Optional[str] = None, status: Optional[str] = None,
                         business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    q = {"business_id": business_id, "fy": fy}
    if status:
        q["status"] = status
    docs = await db.reminders.find(q, {"_id": 0}).sort("month_key", 1).to_list(1000)
    now = datetime.now(timezone.utc)
    visible = []
    for d in docs:
        if d["status"] == "snoozed" and d.get("snooze_until"):
            if datetime.fromisoformat(d["snooze_until"]) <= now:
                await db.reminders.update_one({"reminder_id": d["reminder_id"]},
                                             {"$set": {"status": "open", "snooze_until": None}})
                d["status"] = "open"
        visible.append({**d, "month_label": month_label(d["month_key"]),
                        "expected_amount": to_dollars(d.get("expected_amount_cents"))
                        if d.get("expected_amount_cents") else None})
    counts = {}
    for s in ["open", "completed", "skipped", "snoozed", "na"]:
        counts[s] = len([d for d in visible if d["status"] == s])
    return {"fy": fy, "items": visible, "counts": counts}


class ReminderActionIn(BaseModel):
    action: str  # complete | skip | snooze | na | reopen
    snooze_days: int = 7


@router.post("/reminders/{reminder_id}/action")
async def reminder_action(reminder_id: str, body: ReminderActionIn,
                          business_id: str = Depends(get_business_id),
                          user: dict = Depends(get_current_user)):
    mapping = {"complete": "completed", "skip": "skipped", "na": "na", "reopen": "open"}
    upd = {}
    if body.action == "snooze":
        upd = {"status": "snoozed",
               "snooze_until": (datetime.now(timezone.utc) + timedelta(days=body.snooze_days)).isoformat()}
    elif body.action in mapping:
        upd = {"status": mapping[body.action], "snooze_until": None}
    else:
        raise HTTPException(400, "Unknown action")
    res = await db.reminders.update_one({"business_id": business_id, "reminder_id": reminder_id},
                                       {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Reminder not found")
    await audit(business_id, user, "reminder", reminder_id, body.action)
    return {"ok": True}


# ---------------- month-end checklist ----------------
CHECK_MAP = {
    "sales_imported": ("txn_type", "sale"),
    "refunds_recorded": ("txn_type", "refund"),
}


async def _auto_state(business_id: str, month_key: str):
    async def has(match):
        return bool(await db.transactions.find_one(
            {"business_id": business_id, "month_key": month_key, "is_deleted": {"$ne": True}, **match}))

    async def has_cat(name, sub=None):
        cat = await db.categories.find_one({"business_id": business_id, "name": sub or name}, {"_id": 0})
        if not cat:
            return False
        key = "subcategory_id" if cat.get("parent_id") else "category_id"
        return await has({key: cat["category_id"]})

    state = {
        "sales_imported": await has({"txn_type": "sale"}),
        "refunds_recorded": await has({"txn_type": "refund"}),
        "shopify_fees": await has_cat("Payment Processing Fees"),
        "facebook_ads": await has_cat("Advertising", "Meta / Facebook Ads"),
        "google_ads": await has_cat("Advertising", "Google Ads"),
        "other_ads": await has_cat("Advertising"),
        "inventory": bool(await db.inventory_purchases.find_one(
            {"business_id": business_id, "month_key": month_key, "is_deleted": {"$ne": True}})),
        "shipping": await has_cat("Shipping"),
        "packaging": await has_cat("Packaging"),
        "electricity": await has_cat("Electricity"),
        "internet_phone": await has_cat("Internet"),
        "software": await has_cat("Software"),
        "bank_fees": await has_cat("Bank Fees"),
        "receipts": not bool(await db.transactions.find_one(
            {"business_id": business_id, "month_key": month_key, "txn_type": "expense",
             "receipt_document_ids": {"$in": [None, []]}, "is_deleted": {"$ne": True}})),
        "reviewed": not bool(await db.transactions.find_one(
            {"business_id": business_id, "month_key": month_key, "needs_review": True,
             "is_deleted": {"$ne": True}})),
        "reconciled": not bool(await db.transactions.find_one(
            {"business_id": business_id, "month_key": month_key, "reconcile_status": "unreconciled",
             "is_deleted": {"$ne": True}})),
    }
    return state


@router.get("/month-end/{month_key}")
async def month_end(month_key: str, business_id: str = Depends(get_business_id)):
    rec = await db.month_end_checks.find_one({"business_id": business_id, "month_key": month_key},
                                            {"_id": 0}) or {}
    manual = rec.get("manual", {})
    custom = rec.get("custom_items", [])
    auto = await _auto_state(business_id, month_key)
    items = []
    for key, label in MONTH_END_ITEMS:
        done = manual.get(key) if key in manual else auto.get(key, False)
        items.append({"key": key, "label": label, "done": bool(done),
                      "auto_detected": auto.get(key, False),
                      "manually_set": key in manual, "enabled": rec.get("disabled", {}).get(key) is not True})
    for c in custom:
        items.append({"key": c["key"], "label": c["label"], "done": bool(manual.get(c["key"])),
                      "auto_detected": False, "manually_set": c["key"] in manual, "custom": True,
                      "enabled": True})
    active = [i for i in items if i["enabled"]]
    completion = round(len([i for i in active if i["done"]]) / len(active) * 100) if active else 0
    return {"month_key": month_key, "month_label": month_label(month_key), "items": items,
            "completion_pct": completion, "closed": rec.get("closed", False)}


class MonthEndItemIn(BaseModel):
    key: str
    done: bool


@router.post("/month-end/{month_key}/item")
async def set_month_end_item(month_key: str, body: MonthEndItemIn,
                             business_id: str = Depends(get_business_id),
                             user: dict = Depends(get_current_user)):
    await db.month_end_checks.update_one(
        {"business_id": business_id, "month_key": month_key},
        {"$set": {f"manual.{body.key}": body.done, "updated_at": now_iso(),
                  "updated_by": user["email"]}}, upsert=True)
    return await month_end(month_key, business_id)


class CustomItemIn(BaseModel):
    label: str = Field(min_length=1, max_length=140)


@router.post("/month-end/{month_key}/custom-item")
async def add_custom_item(month_key: str, body: CustomItemIn,
                          business_id: str = Depends(get_business_id)):
    key = new_id("chk")
    await db.month_end_checks.update_one(
        {"business_id": business_id, "month_key": month_key},
        {"$push": {"custom_items": {"key": key, "label": body.label}}}, upsert=True)
    return await month_end(month_key, business_id)


@router.delete("/month-end/{month_key}/custom-item/{key}")
async def remove_custom_item(month_key: str, key: str, business_id: str = Depends(get_business_id)):
    await db.month_end_checks.update_one({"business_id": business_id, "month_key": month_key},
                                        {"$pull": {"custom_items": {"key": key}}})
    return await month_end(month_key, business_id)


@router.post("/month-end/{month_key}/close")
async def close_month(month_key: str, closed: bool = True,
                      business_id: str = Depends(get_business_id),
                      user: dict = Depends(get_current_user)):
    await db.month_end_checks.update_one({"business_id": business_id, "month_key": month_key},
                                        {"$set": {"closed": closed, "closed_at": now_iso(),
                                                  "closed_by": user["email"]}}, upsert=True)
    await audit(business_id, user, "month_end", month_key, "close" if closed else "reopen")
    return {"ok": True}


@router.get("/month-end")
async def month_end_overview(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    out = []
    for mk in fy_month_keys(fy):
        m = await month_end(mk, business_id)
        out.append({"month_key": mk, "month_label": m["month_label"],
                    "completion_pct": m["completion_pct"], "closed": m["closed"]})
    return {"fy": fy, "months": out}


# ---------------- year-end checklist ----------------
@router.get("/year-end")
async def year_end(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    overview = await month_end_overview(fy, business_id)
    months_reviewed = len([m for m in overview["months"] if m["completion_pct"] >= 100])
    open_reminders = await db.reminders.count_documents({"business_id": business_id, "fy": fy, "status": "open"})
    missing = await missing_receipts(fy, business_id)
    uncategorised = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
         "$or": [{"category_id": None}, {"category_id": ""}]})
    unknown_gst = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "gst_treatment": "unknown", "is_deleted": {"$ne": True}})
    unreconciled = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "reconcile_status": "unreconciled", "is_deleted": {"$ne": True}})
    assets_review = await db.assets.count_documents(
        {"business_id": business_id, "fy": fy, "needs_review": True, "is_deleted": {"$ne": True}})
    duplicates = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "possible_duplicate_of": {"$ne": None},
         "is_deleted": {"$ne": True}})
    from routes_inventory import compute_cogs
    cogs = await compute_cogs(business_id, fy)
    refunds = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "txn_type": "refund", "is_deleted": {"$ne": True}})
    overrides = (await db.year_end_overrides.find_one({"business_id": business_id, "fy": fy}, {"_id": 0})) or {}
    ov = overrides.get("reviewed", {})

    checks = [
        {"key": "months_reviewed", "label": "12 months reviewed", "mandatory": True,
         "value": f"{months_reviewed}/12", "resolved": months_reviewed >= 12},
        {"key": "missing_recurring", "label": "Missing recurring expenses", "mandatory": True,
         "value": open_reminders, "resolved": open_reminders == 0},
        {"key": "missing_receipts", "label": "Missing receipts", "mandatory": False,
         "value": missing["count"], "resolved": missing["count"] == 0},
        {"key": "uncategorised", "label": "Uncategorised transactions", "mandatory": True,
         "value": uncategorised, "resolved": uncategorised == 0},
        {"key": "unknown_gst", "label": "Unknown GST treatment", "mandatory": True,
         "value": unknown_gst, "resolved": unknown_gst == 0},
        {"key": "unreconciled", "label": "Unreconciled transactions", "mandatory": False,
         "value": unreconciled, "resolved": unreconciled == 0},
        {"key": "assets", "label": "Asset purchases needing review", "mandatory": False,
         "value": assets_review, "resolved": assets_review == 0},
        {"key": "cogs", "label": "Inventory / COGS review", "mandatory": True,
         "value": f"{cogs['unmatched_units_sold']} unmatched units",
         "resolved": cogs["unmatched_units_sold"] == 0},
        {"key": "refunds", "label": "Refund reconciliation", "mandatory": False,
         "value": f"{refunds} refunds recorded", "resolved": True},
        {"key": "duplicates", "label": "Possible duplicate transactions", "mandatory": True,
         "value": duplicates, "resolved": duplicates == 0},
    ]
    for c in checks:
        c["marked_reviewed"] = bool(ov.get(c["key"]))
        c["ok"] = c["resolved"] or c["marked_reviewed"]
    ready = all(c["ok"] for c in checks if c["mandatory"])
    return {"fy": fy, "checks": checks, "ready_for_accountant": ready,
            "completion_pct": round(len([c for c in checks if c["ok"]]) / len(checks) * 100)}


class YearEndOverrideIn(BaseModel):
    key: str
    reviewed: bool = True


@router.post("/year-end/override")
async def year_end_override(body: YearEndOverrideIn, fy: Optional[str] = None,
                            business_id: str = Depends(get_business_id),
                            user: dict = Depends(get_current_user)):
    fy = fy or current_fy()
    await db.year_end_overrides.update_one({"business_id": business_id, "fy": fy},
                                          {"$set": {f"reviewed.{body.key}": body.reviewed}}, upsert=True)
    await audit(business_id, user, "year_end", f"{fy}:{body.key}", "mark_reviewed")
    return await year_end(fy, business_id)
