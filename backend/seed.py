"""Default setup + demo data seeding / purging."""
import random
from datetime import date, timedelta

from core import (db, new_id, now_iso, to_cents, compute_gst, fy_of, month_key_of)

DEFAULT_CATEGORIES = {
    "Advertising": ["Meta / Facebook Ads", "Google Ads", "Snapchat Ads", "TikTok Ads",
                    "Pinterest Ads", "Influencer Marketing", "Other Advertising"],
    "Inventory": ["Stock Purchases", "Freight & Import", "Customs & Duty"],
    "Machinery & Equipment": ["Equipment Purchases", "Tools"],
    "Shipping": ["Australia Post", "Couriers", "Other Shipping"],
    "Packaging": ["Boxes & Mailers", "Labels", "Other Packaging"],
    "Software": ["Shopify Subscription", "Apps & Plugins", "Design Software", "Other Software"],
    "Electricity": [],
    "Internet": [],
    "Phone": [],
    "Office Expenses": ["Stationery", "Furniture"],
    "Professional Fees": ["Accounting", "Legal", "Consulting"],
    "Bank Fees": [],
    "Payment Processing Fees": ["Shopify Payments", "PayPal", "Afterpay", "Stripe"],
    "Refunds": [],
    "Repairs": [],
    "Subscriptions": [],
    "Other Expenses": [],
}
DEFAULT_INCOME_CATEGORIES = {
    "Product Sales": ["Online Store", "Marketplace", "Wholesale"],
    "Shipping Revenue": [],
    "Other Income": ["Interest", "Grants", "Miscellaneous"],
}
DEFAULT_ACCOUNTS = ["Business Bank Account", "Business Credit Card", "PayPal",
                    "Shopify Payments", "Afterpay", "Cash", "Other"]

MONTH_END_ITEMS = [
    ("sales_imported", "Sales imported"),
    ("refunds_recorded", "Refunds recorded"),
    ("shopify_fees", "Shopify / payment fees recorded"),
    ("facebook_ads", "Facebook Ads recorded"),
    ("google_ads", "Google Ads recorded"),
    ("other_ads", "Other advertising recorded"),
    ("inventory", "Inventory purchases recorded"),
    ("shipping", "Shipping expenses recorded"),
    ("packaging", "Packaging recorded"),
    ("electricity", "Electricity recorded"),
    ("internet_phone", "Internet / phone recorded"),
    ("software", "Software subscriptions recorded"),
    ("bank_fees", "Bank / payment fees recorded"),
    ("receipts", "Receipts uploaded"),
    ("reviewed", "Transactions reviewed"),
    ("reconciled", "Reconciliation completed"),
]


async def seed_default_setup(business_id: str):
    if await db.categories.find_one({"business_id": business_id}):
        return
    sort = 0
    for kind, tree in (("expense", DEFAULT_CATEGORIES), ("income", DEFAULT_INCOME_CATEGORIES)):
        for parent, children in tree.items():
            pid = new_id("cat")
            sort += 1
            await db.categories.insert_one({
                "category_id": pid, "business_id": business_id, "name": parent,
                "parent_id": None, "kind": kind, "is_archived": False,
                "sort": sort, "created_at": now_iso(),
            })
            for child in children:
                sort += 1
                await db.categories.insert_one({
                    "category_id": new_id("cat"), "business_id": business_id, "name": child,
                    "parent_id": pid, "kind": kind, "is_archived": False,
                    "sort": sort, "created_at": now_iso(),
                })
    for name in DEFAULT_ACCOUNTS:
        await db.payment_accounts.insert_one({
            "account_id": new_id("acct"), "business_id": business_id, "name": name,
            "type": "bank" if "Bank" in name else "other", "is_archived": False,
            "created_at": now_iso(),
        })


async def _cat(business_id, name):
    return await db.categories.find_one({"business_id": business_id, "name": name}, {"_id": 0})


async def _acct(business_id, name):
    return await db.payment_accounts.find_one({"business_id": business_id, "name": name}, {"_id": 0})


async def _mk_txn(business_id, **kw):
    treatment = kw.pop("gst_treatment", "gst_included")
    amount = kw.pop("amount")
    ex, gst, inc, review = compute_gst(amount, treatment)
    d = kw.pop("date")
    doc = {
        "txn_id": new_id("txn"), "business_id": business_id, "date": d,
        "fy": fy_of(d), "month_key": month_key_of(d),
        "amount_ex_cents": ex, "gst_cents": gst, "amount_inc_cents": inc,
        "gst_treatment": treatment, "gst_rate": "0.10" if treatment in ("gst_included", "gst_excluded") else None,
        "needs_review": review, "ask_accountant": False, "accountant_note": "",
        "reconcile_status": "unreconciled", "receipt_document_ids": [], "tags": ["demo"],
        "is_deleted": False, "is_demo": True, "created_at": now_iso(),
        "created_by": "demo-seed", "updated_at": now_iso(), "updated_by": "demo-seed",
    }
    doc.update(kw)
    await db.transactions.insert_one(doc)
    return doc


async def load_demo_data(business_id: str, user):
    """6+ months of FY2025-26 sample data, flagged is_demo=True."""
    await purge_demo_data(business_id)
    months = [(2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11), (2025, 12), (2026, 1)]

    cat_names = {}
    for n in ["Advertising", "Meta / Facebook Ads", "Google Ads", "Snapchat Ads", "Electricity",
              "Software", "Shopify Subscription", "Packaging", "Shipping", "Australia Post",
              "Payment Processing Fees", "Shopify Payments", "Product Sales", "Online Store",
              "Inventory", "Stock Purchases", "Machinery & Equipment", "Equipment Purchases",
              "Internet", "Bank Fees"]:
        c = await _cat(business_id, n)
        if c:
            cat_names[n] = c

    bank = await _acct(business_id, "Business Bank Account")
    card = await _acct(business_id, "Business Credit Card")
    shopify_acct = await _acct(business_id, "Shopify Payments")

    suppliers = {}
    for name, country in [("Meta Platforms Ireland", "Ireland"), ("Google Australia", "Australia"),
                          ("Snap Inc", "United States"), ("Shopify Inc", "Canada"),
                          ("AGL Energy", "Australia"), ("Australia Post", "Australia"),
                          ("Shenzhen Case Co", "China"), ("PackRight Supplies", "Australia"),
                          ("Telstra", "Australia")]:
        sid = new_id("sup")
        await db.suppliers.insert_one({
            "supplier_id": sid, "business_id": business_id, "name": name, "country": country,
            "abn": "" if country != "Australia" else f"{random.randint(10,99)} {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}",
            "email": "", "phone": "", "website": "", "notes": "", "is_archived": False,
            "is_demo": True, "created_at": now_iso(),
        })
        suppliers[name] = sid

    product_id = new_id("prod")
    await db.products.insert_one({
        "product_id": product_id, "business_id": business_id, "sku": "CASE-IP15",
        "name": "iPhone 15 Silicone Case", "is_archived": False, "is_demo": True,
        "created_at": now_iso(),
    })

    fb_amounts = [980, 1240, 1105, 1420, 1890, 2350, 1180]
    gg_amounts = [640, 720, 690, 810, 1150, 1420, 760]
    snap_amounts = [220, 260, 0, 310, 480, 520, 240]
    elec = [148, 152, 0, 161, 158, 172, 149]
    gross_sales = [8200, 9600, 10400, 12800, 18900, 26400, 11200]
    refunds_amt = [180, 240, 310, 420, 760, 1180, 390]
    discounts = [320, 410, 480, 640, 1290, 2100, 520]

    for idx, (y, m) in enumerate(months):
        d = date(y, m, 5).isoformat()
        mid = date(y, m, 15).isoformat()
        late = date(y, m, 25).isoformat()

        # Sales (Shopify)
        await _mk_txn(business_id, date=mid, txn_type="sale",
                      category_id=cat_names["Product Sales"]["category_id"],
                      category_name="Product Sales",
                      subcategory_id=cat_names["Online Store"]["category_id"],
                      subcategory_name="Online Store",
                      account_id=shopify_acct["account_id"], account_name="Shopify Payments",
                      description=f"Shopify sales {y}-{m:02d}", amount=gross_sales[idx],
                      gst_treatment="gst_included", reference=f"SHOP-{y}{m:02d}",
                      external_source="manual",
                      sale={"gross": gross_sales[idx], "discounts": discounts[idx],
                            "shipping_revenue": round(gross_sales[idx] * 0.04, 2),
                            "other_income": 0, "gift_cards": 0,
                            "fees": round(gross_sales[idx] * 0.019, 2)},
                      items=[{"product_id": product_id, "sku": "CASE-IP15",
                              "qty": int(gross_sales[idx] / 28)}])
        # Refunds
        await _mk_txn(business_id, date=late, txn_type="refund",
                      category_id=cat_names["Product Sales"]["category_id"],
                      category_name="Product Sales",
                      subcategory_id=cat_names["Online Store"]["category_id"],
                      subcategory_name="Online Store",
                      account_id=shopify_acct["account_id"], account_name="Shopify Payments",
                      description=f"Customer refunds {y}-{m:02d}", amount=refunds_amt[idx],
                      gst_treatment="gst_included", reference=f"RF-{y}{m:02d}",
                      refund={"reason": random.choice(["Change of mind", "Damaged in transit",
                                                       "Wrong item", "Faulty"]),
                              "original_order": f"#{1000 + idx * 37}",
                              "product_id": product_id, "sku": "CASE-IP15"})
        # Ads
        for name, amt, sup in [("Meta / Facebook Ads", fb_amounts[idx], "Meta Platforms Ireland"),
                               ("Google Ads", gg_amounts[idx], "Google Australia"),
                               ("Snapchat Ads", snap_amounts[idx], "Snap Inc")]:
            if not amt:
                continue
            await _mk_txn(business_id, date=d, txn_type="expense",
                          category_id=cat_names["Advertising"]["category_id"],
                          category_name="Advertising",
                          subcategory_id=cat_names[name]["category_id"], subcategory_name=name,
                          supplier_id=suppliers[sup], supplier_name=sup,
                          account_id=card["account_id"], account_name="Business Credit Card",
                          description=f"{name} spend", amount=amt,
                          gst_treatment="gst_free" if sup != "Google Australia" else "gst_included",
                          reference=f"AD-{y}{m:02d}",
                          ad_metrics={"revenue": round(amt * random.uniform(2.1, 4.4), 2),
                                      "orders": int(amt / random.uniform(22, 38)),
                                      "clicks": int(amt / random.uniform(0.6, 1.3)),
                                      "impressions": int(amt * random.uniform(180, 320))})
        # Electricity (August missing on purpose)
        if elec[idx]:
            await _mk_txn(business_id, date=late, txn_type="expense",
                          category_id=cat_names["Electricity"]["category_id"],
                          category_name="Electricity",
                          supplier_id=suppliers["AGL Energy"], supplier_name="AGL Energy",
                          account_id=bank["account_id"], account_name="Business Bank Account",
                          description="Electricity account", amount=elec[idx],
                          gst_treatment="gst_included", reference=f"AGL-{y}{m:02d}")
        # Shopify subscription
        await _mk_txn(business_id, date=d, txn_type="expense",
                      category_id=cat_names["Software"]["category_id"], category_name="Software",
                      subcategory_id=cat_names["Shopify Subscription"]["category_id"],
                      subcategory_name="Shopify Subscription",
                      supplier_id=suppliers["Shopify Inc"], supplier_name="Shopify Inc",
                      account_id=card["account_id"], account_name="Business Credit Card",
                      description="Shopify monthly plan", amount=79,
                      gst_treatment="gst_included", reference=f"SH-{y}{m:02d}")
        # Internet
        await _mk_txn(business_id, date=d, txn_type="expense",
                      category_id=cat_names["Internet"]["category_id"], category_name="Internet",
                      supplier_id=suppliers["Telstra"], supplier_name="Telstra",
                      account_id=bank["account_id"], account_name="Business Bank Account",
                      description="Business internet", amount=99, gst_treatment="gst_included")
        # Packaging (no receipt on purpose in Sept)
        await _mk_txn(business_id, date=mid, txn_type="expense",
                      category_id=cat_names["Packaging"]["category_id"], category_name="Packaging",
                      subcategory_name="Boxes & Mailers",
                      supplier_id=suppliers["PackRight Supplies"], supplier_name="PackRight Supplies",
                      account_id=bank["account_id"], account_name="Business Bank Account",
                      description="Mailers and labels", amount=180 + idx * 22,
                      gst_treatment="gst_included")
        # Shipping
        await _mk_txn(business_id, date=late, txn_type="expense",
                      category_id=cat_names["Shipping"]["category_id"], category_name="Shipping",
                      subcategory_id=cat_names["Australia Post"]["category_id"],
                      subcategory_name="Australia Post",
                      supplier_id=suppliers["Australia Post"], supplier_name="Australia Post",
                      account_id=bank["account_id"], account_name="Business Bank Account",
                      description="Postage", amount=round(gross_sales[idx] * 0.055, 2),
                      gst_treatment="gst_included")
        # Payment processing fees
        await _mk_txn(business_id, date=late, txn_type="expense",
                      category_id=cat_names["Payment Processing Fees"]["category_id"],
                      category_name="Payment Processing Fees",
                      subcategory_id=cat_names["Shopify Payments"]["category_id"],
                      subcategory_name="Shopify Payments",
                      supplier_id=suppliers["Shopify Inc"], supplier_name="Shopify Inc",
                      account_id=shopify_acct["account_id"], account_name="Shopify Payments",
                      description="Shopify Payments fees", amount=round(gross_sales[idx] * 0.019, 2),
                      gst_treatment="gst_included")
        # Bank fees
        await _mk_txn(business_id, date=late, txn_type="expense",
                      category_id=cat_names["Bank Fees"]["category_id"], category_name="Bank Fees",
                      account_id=bank["account_id"], account_name="Business Bank Account",
                      description="Account keeping fee", amount=12, gst_treatment="no_gst")

    # Inventory purchases with landed costs
    for i, (y, m, qty, unit) in enumerate([(2025, 7, 1000, 5.0), (2025, 10, 1500, 4.8), (2026, 1, 2000, 4.6)]):
        d = date(y, m, 8).isoformat()
        freight, customs, import_gst, other = 500, 300, 580, 100
        total = to_cents(qty * unit) + to_cents(freight) + to_cents(customs) + to_cents(import_gst) + to_cents(other)
        await db.inventory_purchases.insert_one({
            "purchase_id": new_id("inv"), "business_id": business_id, "date": d, "fy": fy_of(d),
            "month_key": month_key_of(d), "supplier_id": suppliers["Shenzhen Case Co"],
            "supplier_name": "Shenzhen Case Co", "product_id": product_id, "sku": "CASE-IP15",
            "description": "Silicone phone cases", "qty": qty, "unit_cost_cents": to_cents(unit),
            "freight_cents": to_cents(freight), "customs_cents": to_cents(customs),
            "import_gst_cents": to_cents(import_gst), "other_cents": to_cents(other),
            "total_cost_cents": total, "landed_unit_cost_cents": int(round(total / qty)),
            "qty_sold": 0, "reference": f"PO-{y}{m:02d}", "notes": "",
            "receipt_document_ids": [], "is_deleted": False, "is_demo": True,
            "created_at": now_iso(), "created_by": "demo-seed",
        })

    # Asset / machinery
    d = date(2025, 9, 12).isoformat()
    ex, gst, inc, _ = compute_gst(8800, "gst_included")
    await db.assets.insert_one({
        "asset_id": new_id("ast"), "business_id": business_id, "name": "Heat press machine",
        "date": d, "fy": fy_of(d), "month_key": month_key_of(d),
        "supplier_id": suppliers["Shenzhen Case Co"], "supplier_name": "Shenzhen Case Co",
        "invoice": "INV-88231", "price_ex_cents": ex, "gst_cents": gst, "price_inc_cents": inc,
        "gst_treatment": "gst_included", "serial": "HP-2025-0912", "category_id": None,
        "asset_category": "Machinery & Equipment", "business_use_pct": 100,
        "status": "in_use", "notes": "Please confirm asset vs expense treatment.",
        "receipt_document_ids": [], "needs_review": True, "is_deleted": False, "is_demo": True,
        "created_at": now_iso(), "created_by": "demo-seed",
    })

    # Recurring templates
    for name, cat, sub, amt, freq in [
        ("Shopify Subscription", "Software", "Shopify Subscription", 79, "monthly"),
        ("Electricity", "Electricity", None, 155, "monthly"),
        ("Business Internet", "Internet", None, 99, "monthly"),
        ("Meta / Facebook Ads", "Advertising", "Meta / Facebook Ads", None, "monthly"),
        ("Google Ads", "Advertising", "Google Ads", None, "monthly"),
    ]:
        c = cat_names.get(cat)
        s = cat_names.get(sub) if sub else None
        await db.recurring_templates.insert_one({
            "template_id": new_id("rec"), "business_id": business_id, "name": name,
            "category_id": c["category_id"] if c else None, "category_name": cat,
            "subcategory_id": s["category_id"] if s else None, "subcategory_name": sub,
            "supplier_id": None, "supplier_name": None, "account_id": None,
            "frequency": freq, "expected_amount_cents": to_cents(amt) if amt else None,
            "variable": amt is None, "gst_treatment": "gst_included", "is_active": True,
            "start_month": "2025-07", "is_demo": True, "created_at": now_iso(),
        })

    await db.businesses.update_one({"business_id": business_id},
                                  {"$set": {"has_demo_data": True}})
    return {"ok": True, "message": "Demo data loaded for FY2025-26"}


async def purge_demo_data(business_id: str):
    total = 0
    for coll in [db.transactions, db.inventory_purchases, db.assets, db.suppliers,
                 db.products, db.recurring_templates, db.reminders, db.documents,
                 db.cogs_entries]:
        res = await coll.delete_many({"business_id": business_id, "is_demo": True})
        total += res.deleted_count
    # reminders are derived data: clear them all so a re-scan cannot duplicate rows
    # that pointed at templates which have just been removed.
    await db.reminders.delete_many({"business_id": business_id})
    await db.businesses.update_one({"business_id": business_id}, {"$set": {"has_demo_data": False}})
    return {"ok": True, "deleted": total}
