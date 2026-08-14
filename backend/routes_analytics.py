"""Analytics: dashboard, P&L, GST center, cash flow, advertising, drill-downs, search."""
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_business_id
from core import (db, to_dollars, pct, change_pct, fy_month_keys, month_label, current_fy,
                  fy_bounds, quarter_of, month_key_of)
from queries import txn_out
from routes_inventory import compute_cogs

router = APIRouter(prefix="/api", tags=["analytics"])

ADVERTISING_NAME = "Advertising"


async def _agg_by_month(business_id, fy, match_extra):
    q = {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}, **match_extra}
    cur = db.transactions.aggregate([
        {"$match": q},
        {"$group": {"_id": "$month_key", "inc": {"$sum": "$amount_inc_cents"},
                    "ex": {"$sum": "$amount_ex_cents"}, "gst": {"$sum": "$gst_cents"},
                    "n": {"$sum": 1}}},
    ])
    return {r["_id"]: r async for r in cur}


async def _sale_component_by_month(business_id, fy, field):
    cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "txn_type": "sale",
                    "is_deleted": {"$ne": True}}},
        {"$group": {"_id": "$month_key", "t": {"$sum": {"$ifNull": [f"$sale.{field}", 0]}}}},
    ])
    return {r["_id"]: float(r["t"] or 0) async for r in cur}


async def _operating_expense_match(business_id):
    """Operating expenses exclude Inventory/COGS categories (COGS handled separately)."""
    excluded = await db.categories.find(
        {"business_id": business_id, "parent_id": None, "name": {"$in": ["Inventory"]}},
        {"_id": 0, "category_id": 1}).to_list(20)
    ids = [c["category_id"] for c in excluded]
    match = {"txn_type": "expense"}
    if ids:
        match["category_id"] = {"$nin": ids}
    return match


async def build_pnl(business_id: str, fy: str):
    months = fy_month_keys(fy)
    sales = await _agg_by_month(business_id, fy, {"txn_type": "sale"})
    refunds = await _agg_by_month(business_id, fy, {"txn_type": "refund"})
    other_income = await _agg_by_month(business_id, fy, {"txn_type": "other_income"})
    op_match = await _operating_expense_match(business_id)
    expenses = await _agg_by_month(business_id, fy, op_match)
    discounts = await _sale_component_by_month(business_id, fy, "discounts")
    shipping_rev = await _sale_component_by_month(business_id, fy, "shipping_revenue")
    cogs = await compute_cogs(business_id, fy)
    cogs_by_month = {m["month_key"]: m["cogs"] for m in cogs["months"]}

    rows = []
    for mk in months:
        gross = to_dollars(sales.get(mk, {}).get("inc", 0))
        disc = round(discounts.get(mk, 0.0), 2)
        ref = to_dollars(refunds.get(mk, {}).get("inc", 0))
        oth = to_dollars(other_income.get(mk, {}).get("inc", 0))
        net = round(gross - disc - ref, 2)
        cg = cogs_by_month.get(mk, 0.0)
        gp = round(net - cg, 2)
        opex = to_dollars(expenses.get(mk, {}).get("inc", 0))
        op = round(gp - opex, 2)
        rows.append({
            "month_key": mk, "month_label": month_label(mk), "quarter": quarter_of(mk),
            "gross_sales": gross, "discounts": disc, "refunds": ref, "net_sales": net,
            "other_income": oth, "shipping_revenue": round(shipping_rev.get(mk, 0.0), 2),
            "cogs": cg, "gross_profit": gp, "operating_expenses": opex, "operating_profit": op,
            "gross_margin_pct": pct(gp, net), "operating_margin_pct": pct(op, net),
            "refund_rate_pct": pct(ref, gross),
            "gst_collected": to_dollars(sales.get(mk, {}).get("gst", 0)),
            "gst_paid": to_dollars(expenses.get(mk, {}).get("gst", 0)),
        })

    def tot(k):
        return round(sum(r[k] for r in rows), 2)

    totals = {k: tot(k) for k in ["gross_sales", "discounts", "refunds", "net_sales",
                                 "other_income", "shipping_revenue", "cogs", "gross_profit",
                                 "operating_expenses", "operating_profit", "gst_collected",
                                 "gst_paid"]}
    totals["gross_margin_pct"] = pct(totals["gross_profit"], totals["net_sales"])
    totals["operating_margin_pct"] = pct(totals["operating_profit"], totals["net_sales"])
    totals["refund_rate_pct"] = pct(totals["refunds"], totals["gross_sales"])
    return {"fy": fy, "months": rows, "totals": totals,
            "cogs_methodology": cogs["methodology"],
            "formula": [
                "Gross Sales - Discounts - Refunds = Net Sales",
                "Net Sales - COGS = Gross Profit",
                "Gross Profit - Operating Expenses = Operating Profit",
            ]}


@router.get("/pnl")
async def pnl(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    """Structured P&L (months + totals). The spreadsheet-style version used by the
    Reports screen and exports lives at /api/reports/pnl in routes_reports.py."""
    return await build_pnl(business_id, fy or current_fy())


@router.get("/dashboard")
async def dashboard(fy: Optional[str] = None, period: str = "fy",
                    month_key: Optional[str] = None,
                    date_from: Optional[str] = None, date_to: Optional[str] = None,
                    business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    pl = await build_pnl(business_id, fy)
    rows = pl["months"]

    if period == "month" and month_key:
        scope = [r for r in rows if r["month_key"] == month_key]
    elif period == "quarter" and month_key:
        qz = quarter_of(month_key)
        scope = [r for r in rows if r["quarter"] == qz]
    elif period == "custom" and date_from and date_to:
        mk_from, mk_to = date_from[:7], date_to[:7]
        scope = [r for r in rows if mk_from <= r["month_key"] <= mk_to]
    else:
        scope = rows

    def s(k):
        return round(sum(r[k] for r in scope), 2)

    gross, disc, ref = s("gross_sales"), s("discounts"), s("refunds")
    net, cogs_v, gp = s("net_sales"), s("cogs"), s("gross_profit")
    opex, opp = s("operating_expenses"), s("operating_profit")
    gst_col, gst_paid = s("gst_collected"), s("gst_paid")

    # cash flow (money movement)
    cash_in = round(gross + s("other_income") , 2)
    cash_out = round(opex + cogs_v, 2)

    # advertising
    adv = await advertising_summary(fy=fy, business_id=business_id)
    refund_count = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "txn_type": "refund", "is_deleted": {"$ne": True}})

    # attention items
    missing_receipts = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "txn_type": "expense",
         "receipt_document_ids": {"$in": [None, []]}, "is_deleted": {"$ne": True}})
    uncategorised = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
         "$or": [{"category_id": None}, {"category_id": ""}]})
    needs_review = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}, "needs_review": True})
    unreconciled = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
         "reconcile_status": "unreconciled"})
    ask_accountant = await db.transactions.count_documents(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}, "ask_accountant": True})
    open_reminders = await db.reminders.count_documents(
        {"business_id": business_id, "fy": fy, "status": "open"})

    import_gst_cur = db.inventory_purchases.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}},
        {"$group": {"_id": None, "t": {"$sum": "$import_gst_cents"}}}])
    import_gst_rows = await import_gst_cur.to_list(1)
    import_gst = to_dollars(import_gst_rows[0]["t"] if import_gst_rows else 0)

    # top expense categories
    cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "txn_type": "expense",
                    "is_deleted": {"$ne": True}}},
        {"$group": {"_id": {"id": "$category_id", "name": "$category_name"},
                    "t": {"$sum": "$amount_inc_cents"}}},
        {"$sort": {"t": -1}}, {"$limit": 10}])
    top_categories = [{"category_id": r["_id"]["id"], "name": r["_id"]["name"] or "Uncategorised",
                       "amount": to_dollars(r["t"])} async for r in cur]

    return {
        "fy": fy, "period": period, "month_key": month_key,
        "kpis": {
            "gross_sales": gross, "net_sales": net, "refunds": ref, "discounts": disc,
            "cogs": cogs_v, "gross_profit": gp, "operating_expenses": opex,
            "operating_profit": opp, "gst_collected": gst_col, "gst_paid": gst_paid,
            "import_gst": import_gst,
            "estimated_gst_position": round(gst_col - gst_paid, 2),
            "cash_inflow": cash_in, "cash_outflow": cash_out,
            "net_cash_flow": round(cash_in - cash_out, 2),
            "gross_margin_pct": pct(gp, net), "operating_margin_pct": pct(opp, net),
            "refund_rate_pct": pct(ref, gross), "refund_count": refund_count,
            "advertising": adv["totals"]["spend"],
            "advertising_pct_of_net_sales": pct(adv["totals"]["spend"], net),
        },
        "months": rows,
        "top_expense_categories": top_categories,
        "advertising_by_channel": adv["channels"],
        "attention": {
            "missing_receipts": missing_receipts, "uncategorised": uncategorised,
            "needs_review": needs_review, "unreconciled": unreconciled,
            "ask_accountant": ask_accountant, "open_reminders": open_reminders,
        },
        "disclaimer": ("GST and BAS figures shown are bookkeeping estimates for accountant review. "
                       "They are not lodged tax returns."),
    }


@router.get("/summary/month/{month_key}")
async def month_summary(month_key: str, business_id: str = Depends(get_business_id)):
    from core import fy_of
    from datetime import date as _date
    y, m = month_key.split("-")
    fy = fy_of(_date(int(y), int(m), 1))
    pl = await build_pnl(business_id, fy)
    rows = pl["months"]
    idx = next((i for i, r in enumerate(rows) if r["month_key"] == month_key), None)
    if idx is None:
        raise HTTPException(404, "Month not in financial year")
    row = rows[idx]
    prev = rows[idx - 1] if idx > 0 else None

    cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "month_key": month_key, "txn_type": "expense",
                    "is_deleted": {"$ne": True}}},
        {"$group": {"_id": {"id": "$category_id", "name": "$category_name"},
                    "t": {"$sum": "$amount_inc_cents"}}}, {"$sort": {"t": -1}}])
    breakdown = [{"category_id": r["_id"]["id"], "name": r["_id"]["name"] or "Uncategorised",
                  "amount": to_dollars(r["t"])} async for r in cur]
    return {
        "month_key": month_key, "month_label": month_label(month_key), "fy": fy,
        "summary": row, "expense_breakdown": breakdown,
        "vs_previous_month": {k: change_pct(row[k], prev[k]) for k in
                              ["gross_sales", "net_sales", "refunds", "cogs", "gross_profit",
                               "operating_expenses", "operating_profit"]} if prev else None,
        "previous_month": prev,
    }


@router.get("/categories/{category_id}/detail")
async def category_detail(category_id: str, fy: Optional[str] = None,
                          business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    cat = await db.categories.find_one({"business_id": business_id, "category_id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(404, "Category not found")
    key = "subcategory_id" if cat.get("parent_id") else "category_id"
    q = {"business_id": business_id, "fy": fy, key: category_id, "is_deleted": {"$ne": True}}
    txns = await db.transactions.find(q, {"_id": 0}).sort("date", -1).to_list(3000)

    by_month = {mk: {"inc": 0, "gst": 0, "n": 0} for mk in fy_month_keys(fy)}
    for t in txns:
        if t["month_key"] in by_month:
            by_month[t["month_key"]]["inc"] += t.get("amount_inc_cents", 0)
            by_month[t["month_key"]]["gst"] += t.get("gst_cents", 0)
            by_month[t["month_key"]]["n"] += 1

    months, prev_amt = [], None
    for mk in fy_month_keys(fy):
        v = by_month[mk]
        amt = to_dollars(v["inc"])
        months.append({"month_key": mk, "month_label": month_label(mk), "amount": amt,
                       "gst": to_dollars(v["gst"]), "count": v["n"],
                       "change_pct": change_pct(amt, prev_amt)})
        prev_amt = amt

    active = [m for m in months if m["count"] > 0]
    total = round(sum(m["amount"] for m in months), 2)
    subs = []
    if not cat.get("parent_id"):
        children = await db.categories.find({"business_id": business_id, "parent_id": category_id},
                                            {"_id": 0}).to_list(200)
        for c in children:
            cur = db.transactions.aggregate([
                {"$match": {"business_id": business_id, "fy": fy, "subcategory_id": c["category_id"],
                            "is_deleted": {"$ne": True}}},
                {"$group": {"_id": None, "t": {"$sum": "$amount_inc_cents"}}}])
            rowz = await cur.to_list(1)
            subs.append({"category_id": c["category_id"], "name": c["name"],
                         "amount": to_dollars(rowz[0]["t"] if rowz else 0)})
        subs.sort(key=lambda x: -x["amount"])

    docs = await db.documents.find(
        {"business_id": business_id, "category_id": category_id, "is_deleted": False},
        {"_id": 0}).to_list(500)
    return {
        "category": cat, "fy": fy, "months": months, "subcategories": subs,
        "total": total, "total_gst": round(sum(m["gst"] for m in months), 2),
        "transaction_count": len(txns),
        "average_monthly": round(total / len(active), 2) if active else 0,
        "months_with_activity": len(active),
        "transactions": [txn_out(t) for t in txns],
        "receipts": docs,
        "notes": [t["notes"] for t in txns if t.get("notes")],
    }


@router.get("/advertising")
async def advertising_summary(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    adv = await db.categories.find_one({"business_id": business_id, "parent_id": None,
                                        "name": ADVERTISING_NAME}, {"_id": 0})
    if not adv:
        return {"fy": fy, "channels": [], "months": [], "totals": {"spend": 0.0}}
    children = await db.categories.find({"business_id": business_id, "parent_id": adv["category_id"]},
                                        {"_id": 0}).to_list(200)
    q = {"business_id": business_id, "fy": fy, "category_id": adv["category_id"],
         "is_deleted": {"$ne": True}}
    txns = await db.transactions.find(q, {"_id": 0}).to_list(5000)
    total_cents = sum(t.get("amount_inc_cents", 0) for t in txns)

    channels = []
    for c in children + [{"category_id": None, "name": "Unassigned Advertising"}]:
        rows = [t for t in txns if t.get("subcategory_id") == c["category_id"]]
        if not rows and c["category_id"] is None:
            continue
        spend_cents = sum(t.get("amount_inc_cents", 0) for t in rows)
        by_month = {}
        rev = orders = clicks = impressions = 0
        has_rev = has_orders = has_clicks = has_impr = False
        for t in rows:
            by_month[t["month_key"]] = by_month.get(t["month_key"], 0) + t.get("amount_inc_cents", 0)
            m = t.get("ad_metrics") or {}
            if m.get("revenue") is not None:
                rev += float(m["revenue"]); has_rev = True
            if m.get("orders") is not None:
                orders += int(m["orders"]); has_orders = True
            if m.get("clicks") is not None:
                clicks += int(m["clicks"]); has_clicks = True
            if m.get("impressions") is not None:
                impressions += int(m["impressions"]); has_impr = True
        spend = to_dollars(spend_cents)
        channels.append({
            "category_id": c["category_id"], "name": c["name"], "spend": spend,
            "pct_of_total_ad_spend": pct(spend_cents, total_cents),
            "months": [{"month_key": mk, "month_label": month_label(mk),
                        "amount": to_dollars(by_month.get(mk, 0))} for mk in fy_month_keys(fy)],
            "metrics": {
                "revenue_attributed": round(rev, 2) if has_rev else None,
                "orders": orders if has_orders else None,
                "clicks": clicks if has_clicks else None,
                "impressions": impressions if has_impr else None,
                "roas": round(rev / spend, 2) if has_rev and spend else None,
                "cpa": round(spend / orders, 2) if has_orders and orders else None,
                "cpc": round(spend / clicks, 2) if has_clicks and clicks else None,
                "ctr": round(clicks / impressions * 100, 2) if has_clicks and has_impr and impressions else None,
            },
        })
    channels.sort(key=lambda x: -x["spend"])
    months = []
    for mk in fy_month_keys(fy):
        months.append({"month_key": mk, "month_label": month_label(mk),
                       "amount": to_dollars(sum(t.get("amount_inc_cents", 0) for t in txns
                                                if t["month_key"] == mk))})
    return {"fy": fy, "channels": channels, "months": months,
            "totals": {"spend": to_dollars(total_cents)},
            "note": "ROAS / CPA / CPC / CTR are only calculated where you have entered the required inputs."}


@router.get("/refunds/analytics")
async def refunds_analytics(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    refunds = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "txn_type": "refund", "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("date", -1).to_list(5000)
    sales_cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "txn_type": "sale", "is_deleted": {"$ne": True}}},
        {"$group": {"_id": None, "t": {"$sum": "$amount_inc_cents"}}}])
    srows = await sales_cur.to_list(1)
    gross_cents = srows[0]["t"] if srows else 0
    total_cents = sum(r.get("amount_inc_cents", 0) for r in refunds)

    by_month = {mk: 0 for mk in fy_month_keys(fy)}
    by_reason, by_product = {}, {}
    for r in refunds:
        if r["month_key"] in by_month:
            by_month[r["month_key"]] += r.get("amount_inc_cents", 0)
        reason = (r.get("refund") or {}).get("reason") or "Not specified"
        by_reason[reason] = by_reason.get(reason, 0) + r.get("amount_inc_cents", 0)
        sku = (r.get("refund") or {}).get("sku") or "Not specified"
        by_product[sku] = by_product.get(sku, 0) + r.get("amount_inc_cents", 0)
    return {
        "fy": fy,
        "totals": {"refunds": to_dollars(total_cents), "count": len(refunds),
                   "gross_sales": to_dollars(gross_cents),
                   "refund_rate_pct": pct(total_cents, gross_cents),
                   "gst_on_refunds": to_dollars(sum(r.get("gst_cents", 0) for r in refunds))},
        "months": [{"month_key": mk, "month_label": month_label(mk), "amount": to_dollars(v)}
                   for mk, v in by_month.items()],
        "by_reason": sorted([{"reason": k, "amount": to_dollars(v)} for k, v in by_reason.items()],
                            key=lambda x: -x["amount"]),
        "by_product": sorted([{"sku": k, "amount": to_dollars(v)} for k, v in by_product.items()],
                             key=lambda x: -x["amount"]),
        "transactions": [txn_out(r) for r in refunds],
    }


@router.get("/sales/summary")
async def sales_summary(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    sales = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "txn_type": "sale", "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("date", -1).to_list(5000)
    other = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "txn_type": "other_income", "is_deleted": {"$ne": True}},
        {"_id": 0}).to_list(2000)
    refund_cur = db.transactions.aggregate([
        {"$match": {"business_id": business_id, "fy": fy, "txn_type": "refund", "is_deleted": {"$ne": True}}},
        {"$group": {"_id": "$month_key", "t": {"$sum": "$amount_inc_cents"}}}])
    refunds_by_month = {r["_id"]: r["t"] async for r in refund_cur}

    def comp(field):
        return round(sum(float((s.get("sale") or {}).get(field) or 0) for s in sales), 2)

    gross = to_dollars(sum(s.get("amount_inc_cents", 0) for s in sales))
    discounts = comp("discounts")
    refunds_total = to_dollars(sum(refunds_by_month.values()))
    months = []
    for mk in fy_month_keys(fy):
        ms = [s for s in sales if s["month_key"] == mk]
        g = to_dollars(sum(s.get("amount_inc_cents", 0) for s in ms))
        d = round(sum(float((s.get("sale") or {}).get("discounts") or 0) for s in ms), 2)
        r = to_dollars(refunds_by_month.get(mk, 0))
        months.append({"month_key": mk, "month_label": month_label(mk), "gross_sales": g,
                       "discounts": d, "refunds": r, "net_sales": round(g - d - r, 2),
                       "shipping_revenue": round(sum(float((s.get("sale") or {}).get("shipping_revenue") or 0) for s in ms), 2),
                       "fees": round(sum(float((s.get("sale") or {}).get("fees") or 0) for s in ms), 2)})
    return {
        "fy": fy,
        "totals": {
            "gross_sales": gross, "discounts": discounts, "refunds": refunds_total,
            "net_sales": round(gross - discounts - refunds_total, 2),
            "shipping_revenue": comp("shipping_revenue"), "gift_cards": comp("gift_cards"),
            "payment_gateway_fees": comp("fees"),
            "taxes_collected": to_dollars(sum(s.get("gst_cents", 0) for s in sales)),
            "other_income": to_dollars(sum(o.get("amount_inc_cents", 0) for o in other)),
            "order_count": len(sales),
        },
        "months": months,
        "transactions": [txn_out(s) for s in sales],
        "shopify_status": "Coming in Phase 4 — manual entry and CSV import available now.",
    }


@router.get("/gst")
async def gst_center(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    base = {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}
    txns = await db.transactions.find(base, {"_id": 0}).to_list(20000)
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)

    collected = sum(t.get("gst_cents", 0) for t in txns if t["txn_type"] in ("sale", "other_income"))
    refunded = sum(t.get("gst_cents", 0) for t in txns if t["txn_type"] == "refund")
    paid = sum(t.get("gst_cents", 0) for t in txns if t["txn_type"] == "expense")
    import_gst = sum(p.get("import_gst_cents", 0) for p in purchases)

    treatments = {}
    for t in txns:
        k = t.get("gst_treatment", "unknown")
        treatments.setdefault(k, {"count": 0, "amount_cents": 0, "gst_cents": 0})
        treatments[k]["count"] += 1
        treatments[k]["amount_cents"] += t.get("amount_inc_cents", 0)
        treatments[k]["gst_cents"] += t.get("gst_cents", 0)

    quarters = {}
    for t in txns:
        qk = quarter_of(t["month_key"])
        quarters.setdefault(qk, {"quarter": qk, "gst_collected": 0, "gst_paid": 0,
                                 "sales_inc": 0, "purchases_inc": 0})
        if t["txn_type"] in ("sale", "other_income"):
            quarters[qk]["gst_collected"] += t.get("gst_cents", 0)
            quarters[qk]["sales_inc"] += t.get("amount_inc_cents", 0)
        elif t["txn_type"] == "refund":
            quarters[qk]["gst_collected"] -= t.get("gst_cents", 0)
            quarters[qk]["sales_inc"] -= t.get("amount_inc_cents", 0)
        else:
            quarters[qk]["gst_paid"] += t.get("gst_cents", 0)
            quarters[qk]["purchases_inc"] += t.get("amount_inc_cents", 0)

    months = []
    for mk in fy_month_keys(fy):
        mt = [t for t in txns if t["month_key"] == mk]
        c = sum(t.get("gst_cents", 0) for t in mt if t["txn_type"] in ("sale", "other_income"))
        c -= sum(t.get("gst_cents", 0) for t in mt if t["txn_type"] == "refund")
        p = sum(t.get("gst_cents", 0) for t in mt if t["txn_type"] == "expense")
        months.append({"month_key": mk, "month_label": month_label(mk),
                       "gst_collected": to_dollars(c), "gst_paid": to_dollars(p),
                       "net": to_dollars(c - p)})

    order = ["Q1 (Jul-Sep)", "Q2 (Oct-Dec)", "Q3 (Jan-Mar)", "Q4 (Apr-Jun)"]
    return {
        "fy": fy,
        "totals": {
            "gst_collected_on_sales": to_dollars(collected),
            "gst_on_refunds": to_dollars(refunded),
            "net_gst_collected": to_dollars(collected - refunded),
            "gst_recorded_on_purchases": to_dollars(paid),
            "import_gst": to_dollars(import_gst),
            "estimated_gst_position": to_dollars(collected - refunded - paid),
        },
        "by_treatment": [{"treatment": k, "count": v["count"],
                          "amount": to_dollars(v["amount_cents"]), "gst": to_dollars(v["gst_cents"])}
                         for k, v in treatments.items()],
        "needs_review_count": len([t for t in txns if t.get("gst_treatment") == "unknown" or t.get("needs_review")]),
        "months": months,
        "quarters": [{**quarters[q], "gst_collected": to_dollars(quarters[q]["gst_collected"]),
                      "gst_paid": to_dollars(quarters[q]["gst_paid"]),
                      "sales_inc": to_dollars(quarters[q]["sales_inc"]),
                      "purchases_inc": to_dollars(quarters[q]["purchases_inc"]),
                      "net": to_dollars(quarters[q]["gst_collected"] - quarters[q]["gst_paid"])}
                     for q in order if q in quarters],
        "disclaimer": ("These are bookkeeping estimates prepared for accountant review. "
                       "This application does not lodge a BAS or any return with the ATO."),
    }


@router.get("/cashflow")
async def cashflow(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    # NOTE: `payroll_accrual: true` transactions are recognised at pay-run finalisation
    # to reduce operating profit at the right time, but they are NOT cash movements.
    # Cash outflows for payroll come from the wages_payables / payg_liabilities /
    # super_liabilities payment ledgers below.
    txns = await db.transactions.find(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
         "payroll_accrual": {"$ne": True}}, {"_id": 0}).to_list(20000)
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)
    assets = await db.assets.find(
        {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(1000)

    # Actual payroll cash movements
    def _payments_by_month(rows: list, amount_field: str = "amount_cents") -> dict:
        out: dict = {}
        for r in rows or []:
            if r.get("status") == "voided":
                continue
            for p in r.get("payments") or []:
                mk = (p.get("payment_date") or "")[:7]
                out[mk] = out.get(mk, 0) + int(p.get(amount_field, 0) or 0)
        return out
    wp = await db.wages_payables.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}).to_list(2000)
    payg = await db.payg_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}).to_list(2000)
    sup = await db.super_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}).to_list(2000)
    wp_pay = _payments_by_month(wp)
    payg_pay = _payments_by_month(payg)
    sup_pay = _payments_by_month(sup)

    months = []
    for mk in fy_month_keys(fy):
        cin = sum(t.get("amount_inc_cents", 0) for t in txns
                  if t["month_key"] == mk and t["txn_type"] in ("sale", "other_income"))
        cout = sum(t.get("amount_inc_cents", 0) for t in txns
                   if t["month_key"] == mk and t["txn_type"] in ("expense", "refund"))
        cout += sum(p.get("total_cost_cents", 0) for p in purchases if p["month_key"] == mk)
        cout += sum(a.get("price_inc_cents", 0) for a in assets if a["month_key"] == mk)
        payroll_cash = wp_pay.get(mk, 0) + payg_pay.get(mk, 0) + sup_pay.get(mk, 0)
        cout += payroll_cash
        months.append({"month_key": mk, "month_label": month_label(mk),
                       "cash_in": to_dollars(cin), "cash_out": to_dollars(cout),
                       "payroll_cash_out": to_dollars(payroll_cash),
                       "net_cash_flow": to_dollars(cin - cout)})
    return {
        "fy": fy, "months": months,
        "totals": {"cash_in": round(sum(m["cash_in"] for m in months), 2),
                   "cash_out": round(sum(m["cash_out"] for m in months), 2),
                   "payroll_cash_out": round(sum(m["payroll_cash_out"] for m in months), 2),
                   "net_cash_flow": round(sum(m["net_cash_flow"] for m in months), 2)},
        "note": ("Cash flow tracks actual money movement (GST-inclusive). "
                 "Payroll expenses appear in P&L at pay-run finalisation, "
                 "but only enter cash flow when wages / PAYG / super are marked paid."),
    }


@router.get("/compare")
async def compare(fy: Optional[str] = None, month_key: Optional[str] = None,
                  business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    start_year = int(fy.replace("FY", "").split("-")[0])
    prev_fy = f"FY{start_year - 1}-{str(start_year)[2:]}"
    cur_pl = await build_pnl(business_id, fy)
    prev_pl = await build_pnl(business_id, prev_fy)
    keys = ["gross_sales", "net_sales", "refunds", "cogs", "gross_profit",
            "operating_expenses", "operating_profit"]
    out = {"fy": fy, "previous_fy": prev_fy,
           "fy_vs_previous_fy": {k: {"current": cur_pl["totals"][k], "previous": prev_pl["totals"][k],
                                     "change_pct": change_pct(cur_pl["totals"][k], prev_pl["totals"][k])}
                                 for k in keys}}
    if month_key:
        rows = cur_pl["months"]
        idx = next((i for i, r in enumerate(rows) if r["month_key"] == month_key), None)
        if idx is not None:
            this_m = rows[idx]
            last_m = rows[idx - 1] if idx > 0 else None
            y, m = month_key.split("-")
            same_last_year = f"{int(y) - 1}-{m}"
            prev_row = next((r for r in prev_pl["months"] if r["month_key"] == same_last_year), None)
            out["month_vs_last_month"] = {k: {"current": this_m[k], "previous": last_m[k] if last_m else None,
                                              "change_pct": change_pct(this_m[k], last_m[k]) if last_m else None}
                                          for k in keys}
            out["month_vs_same_month_last_year"] = {
                k: {"current": this_m[k], "previous": prev_row[k] if prev_row else None,
                    "change_pct": change_pct(this_m[k], prev_row[k]) if prev_row else None}
                for k in keys}
    return out


@router.get("/search")
async def global_search(q: str = Query(min_length=1), business_id: str = Depends(get_business_id)):
    rx = {"$regex": q, "$options": "i"}
    results = {"query": q}

    amount_filter = None
    cleaned = q.replace("$", "").replace(",", "").strip()
    try:
        amount_filter = int(round(float(cleaned) * 100))
    except ValueError:
        pass

    txn_q = {"business_id": business_id, "is_deleted": {"$ne": True}, "$or": [
        {"description": rx}, {"supplier_name": rx}, {"category_name": rx},
        {"subcategory_name": rx}, {"reference": rx}, {"notes": rx}, {"month_key": rx}]}
    if amount_filter:
        txn_q["$or"].append({"amount_inc_cents": amount_filter})
    # month name search e.g. "January 2027"
    from core import MONTH_NAMES
    parts = q.split()
    if parts and parts[0].capitalize() in MONTH_NAMES:
        mi = MONTH_NAMES.index(parts[0].capitalize()) + 1
        if len(parts) > 1 and parts[1].isdigit():
            txn_q["$or"].append({"month_key": f"{parts[1]}-{mi:02d}"})

    txns = await db.transactions.find(txn_q, {"_id": 0}).sort("date", -1).limit(30).to_list(30)
    results["transactions"] = [txn_out(t) for t in txns]
    results["suppliers"] = await db.suppliers.find(
        {"business_id": business_id, "name": rx}, {"_id": 0}).limit(15).to_list(15)
    results["categories"] = await db.categories.find(
        {"business_id": business_id, "name": rx}, {"_id": 0}).limit(15).to_list(15)
    results["products"] = await db.products.find(
        {"business_id": business_id, "$or": [{"sku": rx}, {"name": rx}]}, {"_id": 0}).limit(15).to_list(15)
    assets = await db.assets.find(
        {"business_id": business_id, "is_deleted": {"$ne": True},
         "$or": [{"name": rx}, {"serial": rx}, {"invoice": rx}]}, {"_id": 0}).limit(15).to_list(15)
    from routes_inventory import asset_out, purchase_out
    results["assets"] = [asset_out(a) for a in assets]
    purchases = await db.inventory_purchases.find(
        {"business_id": business_id, "is_deleted": {"$ne": True},
         "$or": [{"sku": rx}, {"description": rx}, {"supplier_name": rx}, {"reference": rx}]},
        {"_id": 0}).limit(15).to_list(15)
    results["inventory_purchases"] = [purchase_out(p) for p in purchases]
    results["documents"] = await db.documents.find(
        {"business_id": business_id, "is_deleted": False, "filename": rx}, {"_id": 0}).limit(15).to_list(15)
    results["total_results"] = sum(len(v) for v in results.values() if isinstance(v, list))
    return results
