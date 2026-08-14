"""Reports, CSV/PDF/ZIP export, accountant export wizard, CSV import with mapping."""
import csv
import io
import json
import zipfile
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form, Query
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak)

from auth import get_current_user, get_business_id
from core import (db, new_id, now_iso, audit, to_cents, to_dollars, compute_gst, fy_of,
                  month_key_of, month_label, current_fy, parse_date, GST_LABELS)
from queries import txn_out
from routes_analytics import (build_pnl, advertising_summary, refunds_analytics, gst_center,
                              cashflow, sales_summary)
from routes_inventory import compute_cogs, purchase_out, asset_out
from routes_ops import missing_receipts
from storage import get_object

router = APIRouter(prefix="/api", tags=["reports"])

REPORTS = [
    ("pnl", "Profit & Loss"),
    ("revenue", "Revenue Summary"),
    ("expenses", "Expense Summary"),
    ("expense_by_category", "Expense by Category"),
    ("advertising", "Advertising Summary"),
    ("refunds", "Refund Report"),
    ("gst", "GST Summary"),
    ("inventory", "Inventory Purchases"),
    ("cogs", "COGS Report"),
    ("assets", "Asset Register"),
    ("suppliers", "Supplier Spend"),
    ("cashflow", "Cash Flow"),
    ("missing_receipts", "Missing Receipts"),
    ("uncategorised", "Uncategorised Transactions"),
    ("accountant_questions", "Accountant Questions"),
    ("ledger", "Transaction Ledger"),
]
DISCLAIMER = ("Prepared as bookkeeping records for accountant / tax agent review. GST and BAS "
              "figures are estimates only and are not a lodged BAS or tax return. This software "
              "does not determine tax deductibility or depreciation treatment.")


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _au_date(iso: str) -> str:
    try:
        d = parse_date(iso)
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except Exception:
        return iso or ""


# ---------------- report builders ----------------
async def build_report(business_id: str, key: str, fy: str) -> Dict[str, Any]:
    if key == "pnl":
        pl = await build_pnl(business_id, fy)
        rows = [[m["month_label"], m["gross_sales"], m["discounts"], m["refunds"], m["net_sales"],
                 m["cogs"], m["gross_profit"], m["operating_expenses"], m["operating_profit"]]
                for m in pl["months"]]
        t = pl["totals"]
        rows.append(["FY TOTAL", t["gross_sales"], t["discounts"], t["refunds"], t["net_sales"],
                     t["cogs"], t["gross_profit"], t["operating_expenses"], t["operating_profit"]])
        return {"title": "Profit & Loss", "columns": ["Month", "Gross Sales", "Discounts", "Refunds",
                "Net Sales", "COGS", "Gross Profit", "Operating Expenses", "Operating Profit"],
                "rows": rows, "notes": pl["formula"]}

    if key == "revenue":
        s = await sales_summary(fy, business_id)
        rows = [[m["month_label"], m["gross_sales"], m["discounts"], m["refunds"], m["net_sales"],
                 m["shipping_revenue"], m["fees"]] for m in s["months"]]
        t = s["totals"]
        rows.append(["FY TOTAL", t["gross_sales"], t["discounts"], t["refunds"], t["net_sales"],
                     t["shipping_revenue"], t["payment_gateway_fees"]])
        return {"title": "Revenue Summary", "columns": ["Month", "Gross Sales", "Discounts",
                "Refunds", "Net Sales", "Shipping Revenue", "Gateway Fees"], "rows": rows,
                "notes": [f"Taxes collected: {t['taxes_collected']}",
                          f"Other income: {t['other_income']}", f"Gift cards: {t['gift_cards']}"]}

    if key == "expenses":
        pl = await build_pnl(business_id, fy)
        rows = [[m["month_label"], m["operating_expenses"], m["gst_paid"]] for m in pl["months"]]
        rows.append(["FY TOTAL", pl["totals"]["operating_expenses"], pl["totals"]["gst_paid"]])
        return {"title": "Expense Summary", "columns": ["Month", "Operating Expenses (inc GST)",
                "GST Recorded"], "rows": rows, "notes": []}

    if key == "expense_by_category":
        cur = db.transactions.aggregate([
            {"$match": {"business_id": business_id, "fy": fy, "txn_type": "expense",
                        "is_deleted": {"$ne": True}}},
            {"$group": {"_id": {"c": "$category_name", "s": "$subcategory_name"},
                        "inc": {"$sum": "$amount_inc_cents"}, "ex": {"$sum": "$amount_ex_cents"},
                        "gst": {"$sum": "$gst_cents"}, "n": {"$sum": 1}}},
            {"$sort": {"inc": -1}}])
        rows = [[r["_id"].get("c") or "Uncategorised", r["_id"].get("s") or "—", r["n"],
                 to_dollars(r["ex"]), to_dollars(r["gst"]), to_dollars(r["inc"])] async for r in cur]
        return {"title": "Expense by Category", "columns": ["Category", "Subcategory", "Count",
                "Amount Ex GST", "GST", "Amount Inc GST"], "rows": rows, "notes": []}

    if key == "advertising":
        a = await advertising_summary(fy, business_id)
        rows = [[c["name"], c["spend"], c["pct_of_total_ad_spend"],
                 _fmt(c["metrics"]["roas"]), _fmt(c["metrics"]["cpa"]),
                 _fmt(c["metrics"]["cpc"]), _fmt(c["metrics"]["ctr"])] for c in a["channels"]]
        rows.append(["FY TOTAL", a["totals"]["spend"], 100.0, "—", "—", "—", "—"])
        return {"title": "Advertising Summary", "columns": ["Channel", "FY Spend", "% of Ad Spend",
                "ROAS", "CPA", "CPC", "CTR %"], "rows": rows, "notes": [a["note"]]}

    if key == "refunds":
        r = await refunds_analytics(fy, business_id)
        rows = [[m["month_label"], m["amount"]] for m in r["months"]]
        rows.append(["FY TOTAL", r["totals"]["refunds"]])
        return {"title": "Refund Report", "columns": ["Month", "Refunds"], "rows": rows,
                "notes": [f"Refund count: {r['totals']['count']}",
                          f"Refund rate: {_fmt(r['totals']['refund_rate_pct'])}%"] +
                         [f"Reason — {x['reason']}: {x['amount']}" for x in r["by_reason"]]}

    if key == "gst":
        g = await gst_center(fy, business_id)
        rows = [[m["month_label"], m["gst_collected"], m["gst_paid"], m["net"]] for m in g["months"]]
        t = g["totals"]
        rows.append(["FY TOTAL", t["net_gst_collected"], t["gst_recorded_on_purchases"],
                     t["estimated_gst_position"]])
        return {"title": "GST Summary", "columns": ["Month", "GST Collected", "GST on Purchases",
                "Net GST Position"], "rows": rows,
                "notes": [f"Import GST recorded: {t['import_gst']}",
                          f"Transactions needing review: {g['needs_review_count']}", g["disclaimer"]]}

    if key == "inventory":
        docs = await db.inventory_purchases.find(
            {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}},
            {"_id": 0}).sort("date", 1).to_list(3000)
        rows = [[_au_date(p["date"]), p.get("supplier_name") or "—", p.get("sku") or "—", p.get("qty", 0),
                 to_dollars(p.get("unit_cost_cents")), to_dollars(p.get("freight_cents")),
                 to_dollars(p.get("customs_cents")), to_dollars(p.get("import_gst_cents")),
                 to_dollars(p.get("other_cents")), to_dollars(p.get("total_cost_cents")),
                 to_dollars(p.get("landed_unit_cost_cents"))] for p in docs]
        return {"title": "Inventory Purchases", "columns": ["Date", "Supplier", "SKU", "Qty",
                "Unit Cost", "Freight", "Customs", "Import GST", "Other Landed", "Total Cost",
                "Landed Unit Cost"], "rows": rows, "notes": []}

    if key == "cogs":
        c = await compute_cogs(business_id, fy)
        rows = [[m["month_label"], m["units"], m["cogs"]] for m in c["months"]]
        rows.append(["FY TOTAL", c["total_units"], c["total_cogs"]])
        return {"title": "COGS Report", "columns": ["Month", "Units Sold", "COGS"], "rows": rows,
                "notes": [c["methodology"], f"Inventory on hand value: {c['inventory_on_hand_value']}",
                          f"Units on hand: {c['units_on_hand']}",
                          f"Units sold without matching inventory: {c['unmatched_units_sold']}"]}

    if key == "assets":
        docs = await db.assets.find({"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True}},
                                   {"_id": 0}).sort("date", 1).to_list(1000)
        rows = [[_au_date(a["date"]), a["name"], a.get("supplier_name") or "—", a.get("invoice") or "—",
                 to_dollars(a.get("price_ex_cents")), to_dollars(a.get("gst_cents")),
                 to_dollars(a.get("price_inc_cents")), a.get("serial") or "—",
                 a.get("business_use_pct"), a.get("status"),
                 "Yes" if a.get("needs_review") else "No"] for a in docs]
        return {"title": "Asset Register", "columns": ["Date", "Asset", "Supplier", "Invoice",
                "Price Ex GST", "GST", "Price Inc GST", "Serial", "Business Use %", "Status",
                "Needs Review"], "rows": rows,
                "notes": ["Depreciation and deductibility are not determined by this application."]}

    if key == "suppliers":
        cur = db.transactions.aggregate([
            {"$match": {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
                        "supplier_id": {"$ne": None}}},
            {"$group": {"_id": {"id": "$supplier_id", "n": "$supplier_name"},
                        "inc": {"$sum": "$amount_inc_cents"}, "gst": {"$sum": "$gst_cents"},
                        "c": {"$sum": 1}}},
            {"$sort": {"inc": -1}}])
        rows = [[r["_id"]["n"], r["c"], to_dollars(r["gst"]), to_dollars(r["inc"])] async for r in cur]
        return {"title": "Supplier Spend", "columns": ["Supplier", "Transactions", "GST",
                "Total Spent (inc GST)"], "rows": rows, "notes": []}

    if key == "cashflow":
        cf = await cashflow(fy, business_id)
        rows = [[m["month_label"], m["cash_in"], m["cash_out"], m["net_cash_flow"]] for m in cf["months"]]
        rows.append(["FY TOTAL", cf["totals"]["cash_in"], cf["totals"]["cash_out"],
                     cf["totals"]["net_cash_flow"]])
        return {"title": "Cash Flow", "columns": ["Month", "Cash In", "Cash Out", "Net Cash Flow"],
                "rows": rows, "notes": [cf["note"]]}

    if key == "missing_receipts":
        m = await missing_receipts(fy, business_id)
        rows = [[_au_date(t["date"]), t["category_name"] or "Uncategorised", t["supplier_name"] or "—",
                 t["description"], t["amount_inc"]] for t in m["transactions"]]
        return {"title": "Missing Receipts", "columns": ["Date", "Category", "Supplier",
                "Description", "Amount Inc GST"], "rows": rows,
                "notes": [f"Total items missing receipts: {m['count']}"]}

    if key == "uncategorised":
        docs = await db.transactions.find(
            {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
             "$or": [{"category_id": None}, {"category_id": ""}]}, {"_id": 0}).to_list(3000)
        rows = [[_au_date(d["date"]), d["txn_type"], d.get("description", ""),
                 to_dollars(d.get("amount_inc_cents"))] for d in docs]
        return {"title": "Uncategorised Transactions", "columns": ["Date", "Type", "Description",
                "Amount Inc GST"], "rows": rows, "notes": []}

    if key == "accountant_questions":
        docs = await db.transactions.find(
            {"business_id": business_id, "fy": fy, "is_deleted": {"$ne": True},
             "$or": [{"ask_accountant": True}, {"gst_treatment": "unknown"}]}, {"_id": 0}).to_list(3000)
        assets = await db.assets.find({"business_id": business_id, "fy": fy, "needs_review": True,
                                      "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
        rows = [[_au_date(d["date"]), "Transaction", d.get("description", ""),
                 to_dollars(d.get("amount_inc_cents")),
                 GST_LABELS.get(d.get("gst_treatment"), ""),
                 d.get("accountant_note") or ("GST treatment unknown" if d.get("gst_treatment") == "unknown" else "")]
                for d in docs]
        rows += [[_au_date(a["date"]), "Asset", a["name"], to_dollars(a.get("price_inc_cents")),
                  GST_LABELS.get(a.get("gst_treatment"), ""), a.get("notes") or "Please review asset treatment"]
                 for a in assets]
        return {"title": "Accountant Questions", "columns": ["Date", "Record", "Description",
                "Amount Inc GST", "GST Treatment", "Question / Note"], "rows": rows, "notes": []}

    if key == "ledger":
        docs = await db.transactions.find({"business_id": business_id, "fy": fy,
                                         "is_deleted": {"$ne": True}}, {"_id": 0}).sort("date", 1).to_list(20000)
        rows = [[_au_date(d["date"]), d["fy"], month_label(d["month_key"]), d["txn_type"],
                 d.get("category_name") or "Uncategorised", d.get("subcategory_name") or "",
                 d.get("supplier_name") or "", d.get("description", ""),
                 to_dollars(d.get("amount_ex_cents")), to_dollars(d.get("gst_cents")),
                 to_dollars(d.get("amount_inc_cents")), d.get("account_name") or "",
                 d.get("reference", ""), "Attached" if d.get("receipt_document_ids") else "Missing",
                 d.get("notes", "")] for d in docs]
        return {"title": "Transaction Ledger", "columns": ["Date", "FY", "Month", "Transaction Type",
                "Category", "Subcategory", "Supplier", "Description", "Amount Ex GST", "GST",
                "Amount Inc GST", "Payment Method", "Reference", "Receipt Status", "Notes"],
                "rows": rows, "notes": []}

    raise HTTPException(400, f"Unknown report: {key}")


@router.get("/reports")
async def list_reports():
    return {"reports": [{"key": k, "label": l} for k, l in REPORTS], "disclaimer": DISCLAIMER}


@router.get("/reports/{key}")
async def get_report(key: str, fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    r = await build_report(business_id, key, fy)
    return {**r, "fy": fy, "disclaimer": DISCLAIMER}


# ---------------- CSV ----------------
def _csv_bytes(report: Dict[str, Any], fy: str, business_name: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([business_name, report["title"], f"Financial Year {fy.replace('FY', '')}"])
    w.writerow([DISCLAIMER])
    w.writerow([])
    w.writerow(report["columns"])
    for row in report["rows"]:
        w.writerow(row)
    if report.get("notes"):
        w.writerow([])
        w.writerow(["Notes"])
        for n in report["notes"]:
            w.writerow([n])
    return buf.getvalue().encode("utf-8-sig")


@router.get("/reports/{key}/csv")
async def report_csv(key: str, fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    report = await build_report(business_id, key, fy)
    data = _csv_bytes(report, fy, (biz or {}).get("name", "Business"))
    fname = f"{key}_{fy}.csv"
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------- PDF ----------------
def _pdf_bytes(reports: List[Dict[str, Any]], fy: str, business_name: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"{business_name} — FY{fy}")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1x", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#0F291E"))
    h2 = ParagraphStyle("h2x", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#0F291E"))
    small = ParagraphStyle("smallx", parent=styles["BodyText"], fontSize=7.5,
                           textColor=colors.HexColor("#64748B"))
    body = ParagraphStyle("bodyx", parent=styles["BodyText"], fontSize=8)

    story = [Paragraph(business_name, h1),
             Paragraph(f"Financial Year {fy.replace('FY', '')} &nbsp;·&nbsp; 1 July – 30 June &nbsp;·&nbsp; AUD", body),
             Paragraph(DISCLAIMER, small), Spacer(1, 6 * mm)]

    for i, report in enumerate(reports):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(report["title"], h2))
        story.append(Spacer(1, 3 * mm))
        table_data = [report["columns"]] + [[_fmt(c) for c in row] for row in report["rows"]]
        if len(table_data) == 1:
            story.append(Paragraph("No records for this financial year.", body))
        else:
            t = Table(table_data, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F291E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E2DC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FDFCF8")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
        for n in report.get("notes", []):
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(str(n), small))
    doc.build(story)
    return buf.getvalue()


@router.get("/reports/{key}/pdf")
async def report_pdf(key: str, fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    report = await build_report(business_id, key, fy)
    data = _pdf_bytes([report], fy, (biz or {}).get("name", "Business"))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{key}_{fy}.pdf"'})


# ---------------- accountant export wizard ----------------
async def _payroll_accountant_pack(business_id: str, fy: str) -> dict:
    """Build a set of payroll CSVs to bundle in the accountant ZIP.

    Sensitive fields (TFN, BSB, account number, PAYROLL_ENC_KEY) are NEVER
    included. Only aggregated + masked/publicly-safe data.
    """
    # Do we have any finalised runs?  If not, skip.
    n = await db.pay_runs.count_documents(
        {"business_id": business_id, "fy": fy, "status": "finalised"}
    )
    if n == 0:
        return {}
    from routes_payroll_phase4 import (
        report_summary as _rep_summary,
        payment_summary as _payment_summary,
        super_quarter_report as _super_q,
        leave_balances_report as _leave_bal,
    )
    out: dict = {}
    # Payroll Summary
    d = await _rep_summary(fy=fy, period_start=None, period_end=None, business_id=business_id)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Employee", "Slips", "Gross", "Pre-tax Ded", "Taxable", "PAYG",
                "Post-tax Ded", "Net", "Employer Super"])
    for r in d["rows"]:
        w.writerow([r["employee_name"], r["payslip_count"],
                    r["gross_cents"] / 100, r["pretax_ded_cents"] / 100,
                    r["taxable_cents"] / 100, r["payg_cents"] / 100,
                    r["posttax_ded_cents"] / 100, r["net_cents"] / 100,
                    r["super_cents"] / 100])
    out[f"payroll_summary_{fy}.csv"] = buf.getvalue().encode("utf-8-sig")

    # Payment summary per employee (STP-style)
    d = await _payment_summary(fy=fy, employee_id=None, business_id=business_id)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Employee", "Period Start", "Period End", "Slips", "Gross",
                "Taxable", "PAYG", "Net", "Employer Super"])
    for r in d["rows"]:
        w.writerow([r["employee_name"], r["period_start"] or "", r["period_end"] or "",
                    r["payslip_count"], r["gross_cents"] / 100, r["taxable_cents"] / 100,
                    r["payg_cents"] / 100, r["net_cents"] / 100, r["super_cents"] / 100])
    out[f"employee_payment_summary_{fy}.csv"] = buf.getvalue().encode("utf-8-sig")

    # Super by quarter
    d = await _super_q(fy=fy, quarter=None, business_id=business_id)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Quarter", "Employee", "Fund", "Due", "Accrued", "Paid",
                "Outstanding", "Status"])
    for q in d.get("quarters", []):
        for it in q["employees"]:
            w.writerow([q["quarter"], it["employee_name"], it.get("fund_name", ""),
                        q["due_date"], it["accrued_cents"] / 100,
                        it["paid_cents"] / 100, it["outstanding_cents"] / 100,
                        it["status"]])
    out[f"super_by_quarter_{fy}.csv"] = buf.getvalue().encode("utf-8-sig")

    # Leave balances (hours only, no sensitive data)
    d = await _leave_bal(business_id=business_id)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Employee", "Leave Type", "Entitled (h)", "Future Approved (h)", "Remaining (h)"])
    for r in d["rows"]:
        for t, v in r["by_type"].items():
            w.writerow([r["employee_name"], t, v["entitled_hours"],
                        v["future_approved_hours"], v["remaining_hours"]])
    out["leave_balances.csv"] = buf.getvalue().encode("utf-8-sig")

    # PAYG + wages payables outstanding
    payg = await db.payg_liabilities.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}
    ).to_list(2000)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Pay Run", "Period Start", "Period End", "Payment Date",
                "PAYG Cents", "Paid Cents", "Outstanding", "Status"])
    for p in payg:
        out_c = max(0, int(p["payg_cents"]) - int(p.get("paid_cents", 0)))
        w.writerow([p["pay_run_ref"], p["period_start"], p["period_end"],
                    p["payment_date"], p["payg_cents"] / 100,
                    p.get("paid_cents", 0) / 100, out_c / 100, p["status"]])
    out[f"payg_liabilities_{fy}.csv"] = buf.getvalue().encode("utf-8-sig")

    wp = await db.wages_payables.find(
        {"business_id": business_id, "fy": fy}, {"_id": 0}
    ).to_list(2000)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Pay Run", "Payment Date", "Net Cents", "Paid Cents",
                "Outstanding", "Status"])
    for p in wp:
        out_c = max(0, int(p["net_cents"]) - int(p.get("paid_cents", 0)))
        w.writerow([p["pay_run_ref"], p["payment_date"], p["net_cents"] / 100,
                    p.get("paid_cents", 0) / 100, out_c / 100, p["status"]])
    out[f"wages_payables_{fy}.csv"] = buf.getvalue().encode("utf-8-sig")

    out["README.txt"] = (
        "Payroll accountant pack\n\n"
        "Contains employer-facing payroll summaries for the FY. Verified by\n"
        "the employer, not lodged. TFN, BSB and account numbers are NEVER\n"
        "included. Super and PAYG payments listed here are internal records —\n"
        "not evidence of ATO lodgement or super-fund transfer.\n"
    ).encode()
    return out


class ExportIn(BaseModel):
    fy: str
    reports: List[str]
    format: str = "zip"  # pdf | csv | zip
    include_receipts: bool = True


@router.post("/export/accountant")
async def accountant_export(body: ExportIn, business_id: str = Depends(get_business_id),
                            user: dict = Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    name = (biz or {}).get("name", "Business")
    keys = [k for k in body.reports if k in dict(REPORTS)]
    if not keys:
        raise HTTPException(400, "Select at least one report")
    built = [await build_report(business_id, k, body.fy) for k in keys]
    await audit(business_id, user, "export", body.fy, f"accountant_export_{body.format}")
    safe = name.replace(" ", "_")

    if body.format == "pdf":
        data = _pdf_bytes(built, body.fy, name)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{safe}_{body.fy}_accountant_pack.pdf"'})

    if body.format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        for key, report in zip(keys, built):
            w.writerow([name, report["title"], f"Financial Year {body.fy.replace('FY', '')}"])
            w.writerow(report["columns"])
            for row in report["rows"]:
                w.writerow(row)
            w.writerow([])
        return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{safe}_{body.fy}_accountant_pack.csv"'})

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{safe}_{body.fy}_summary.pdf", _pdf_bytes(built, body.fy, name))
        for key, report in zip(keys, built):
            z.writestr(f"csv/{key}_{body.fy}.csv", _csv_bytes(report, body.fy, name))
        z.writestr("README.txt",
                   f"{name} — Financial Year {body.fy.replace('FY', '')}\n\n{DISCLAIMER}\n\n"
                   f"Reports included: {', '.join(dict(REPORTS)[k] for k in keys)}\n"
                   f"Generated: {now_iso()}\nCurrency: AUD  Timezone: Australia/Adelaide\n")
        if body.include_receipts:
            docs = await db.documents.find({"business_id": business_id, "fy": body.fy,
                                           "is_deleted": False}, {"_id": 0}).to_list(2000)
            manifest = []
            for d in docs:
                try:
                    data, _ = get_object(d["storage_path"])
                    zname = f"receipts/{d['document_id']}_{d['filename']}"
                    z.writestr(zname, data)
                    manifest.append({"file": zname, "date": d.get("date"),
                                     "linked_type": d.get("linked_type"),
                                     "linked_id": d.get("linked_id")})
                except Exception:
                    continue
            z.writestr("receipts/manifest.json", json.dumps(manifest, indent=2))
        # ----- Payroll pack (Phase 5) — included on ZIP if payroll has any finalised runs.
        # Never includes TFN, BSB or account numbers. Only aggregate + masked data.
        try:
            payroll_pack = await _payroll_accountant_pack(business_id, body.fy)
            if payroll_pack:
                for fname, data in payroll_pack.items():
                    z.writestr(f"payroll/{fname}", data)
        except Exception as e:
            z.writestr("payroll/README.txt",
                        f"Payroll pack could not be generated: {e}\n")
    return Response(content=mem.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}_{body.fy}_accountant_pack.zip"'})


# ---------------- transaction CSV export ----------------
@router.get("/export/transactions")
async def export_transactions(fy: Optional[str] = None, business_id: str = Depends(get_business_id)):
    fy = fy or current_fy()
    report = await build_report(business_id, "ledger", fy)
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    data = _csv_bytes(report, fy, (biz or {}).get("name", "Business"))
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="transactions_{fy}.csv"'})


# ---------------- CSV import ----------------
SYSTEM_FIELDS = [
    {"key": "date", "label": "Date", "required": True},
    {"key": "description", "label": "Description", "required": False},
    {"key": "amount", "label": "Amount", "required": True},
    {"key": "supplier", "label": "Supplier", "required": False},
    {"key": "category", "label": "Category", "required": False},
    {"key": "subcategory", "label": "Subcategory", "required": False},
    {"key": "reference", "label": "Reference / Invoice No", "required": False},
    {"key": "payment_method", "label": "Payment Method / Account", "required": False},
    {"key": "notes", "label": "Notes", "required": False},
    {"key": "external_id", "label": "External ID (for duplicate protection)", "required": False},
]


@router.get("/import/fields")
async def import_fields():
    return {"system_fields": SYSTEM_FIELDS,
            "presets": ["Shopify export", "Bank transaction CSV", "Advertising CSV", "Custom CSV"]}


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), business_id: str = Depends(get_business_id)):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(raw))
    rows = list(reader)[:2000]
    if not rows:
        raise HTTPException(400, "CSV is empty")
    return {"filename": file.filename, "headers": rows[0], "sample_rows": rows[1:6],
            "row_count": len(rows) - 1, "raw": raw[:400000]}


class ImportIn(BaseModel):
    filename: str = ""
    raw: str
    mapping: Dict[str, str]  # system_field -> csv header
    txn_type: str = "expense"
    gst_treatment: str = "gst_included"
    default_category_id: Optional[str] = None
    source: str = "csv"


def _parse_amount(value: str) -> Optional[float]:
    if value is None:
        return None
    s = str(value).replace("$", "").replace(",", "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return abs(v) if not neg else abs(v)


def _parse_date_flexible(value: str) -> Optional[str]:
    s = (value or "").strip()[:10]
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y"]:
        try:
            from datetime import datetime as _dt
            return _dt.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


@router.post("/import/commit")
async def import_commit(body: ImportIn, business_id: str = Depends(get_business_id),
                        user: dict = Depends(get_current_user)):
    reader = csv.DictReader(io.StringIO(body.raw))
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    default_rate = (biz or {}).get("default_gst_rate", "0.10")
    cats = await db.categories.find({"business_id": business_id}, {"_id": 0}).to_list(3000)
    cat_by_name = {c["name"].lower(): c for c in cats}
    suppliers = await db.suppliers.find({"business_id": business_id}, {"_id": 0}).to_list(2000)
    sup_by_name = {s["name"].lower(): s for s in suppliers}
    accounts = await db.payment_accounts.find({"business_id": business_id}, {"_id": 0}).to_list(200)
    acct_by_name = {a["name"].lower(): a for a in accounts}

    imported = duplicates = skipped = 0
    errors: List[str] = []
    m = body.mapping

    for i, row in enumerate(reader, start=2):
        def val(field):
            col = m.get(field)
            return (row.get(col) or "").strip() if col else ""

        d = _parse_date_flexible(val("date"))
        amount = _parse_amount(val("amount"))
        if not d or not amount:
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {i}: missing or invalid date/amount")
            continue

        ext_id = val("external_id") or None
        if ext_id:
            if await db.transactions.find_one({"business_id": business_id,
                                              "external_source": body.source,
                                              "external_id": ext_id}):
                duplicates += 1
                continue

        cat = cat_by_name.get(val("category").lower()) if val("category") else None
        if not cat and body.default_category_id:
            cat = next((c for c in cats if c["category_id"] == body.default_category_id), None)
        sub = cat_by_name.get(val("subcategory").lower()) if val("subcategory") else None
        sup = sup_by_name.get(val("supplier").lower()) if val("supplier") else None
        if val("supplier") and not sup:
            sup = {"supplier_id": new_id("sup"), "name": val("supplier")}
            await db.suppliers.insert_one({**sup, "business_id": business_id, "country": "Australia",
                                          "abn": "", "email": "", "phone": "", "website": "",
                                          "notes": "Created by CSV import", "is_archived": False,
                                          "is_demo": False, "created_at": now_iso()})
            sup_by_name[sup["name"].lower()] = sup
        acct = acct_by_name.get(val("payment_method").lower()) if val("payment_method") else None

        ex, gst, inc, review = compute_gst(amount, body.gst_treatment, None, True, default_rate)
        near = await db.transactions.find_one({
            "business_id": business_id, "date": d, "amount_inc_cents": inc,
            "txn_type": body.txn_type, "description": val("description"),
            "is_deleted": {"$ne": True}})
        if near:
            duplicates += 1
            continue

        await db.transactions.insert_one({
            "txn_id": new_id("txn"), "business_id": business_id, "txn_type": body.txn_type,
            "date": d, "fy": fy_of(d), "month_key": month_key_of(d),
            "category_id": cat["category_id"] if cat else None,
            "category_name": cat["name"] if cat else None,
            "subcategory_id": sub["category_id"] if sub else None,
            "subcategory_name": sub["name"] if sub else None,
            "supplier_id": sup["supplier_id"] if sup else None,
            "supplier_name": sup["name"] if sup else None,
            "account_id": acct["account_id"] if acct else None,
            "account_name": acct["name"] if acct else None,
            "description": val("description"), "amount_ex_cents": ex, "gst_cents": gst,
            "amount_inc_cents": inc, "gst_treatment": body.gst_treatment,
            "gst_rate": default_rate, "reference": val("reference"), "notes": val("notes"),
            "tags": ["imported"], "receipt_document_ids": [], "needs_review": review,
            "ask_accountant": False, "accountant_note": "", "reconcile_status": "unreconciled",
            "external_source": body.source, "external_id": ext_id,
            "is_deleted": False, "is_demo": False, "created_at": now_iso(),
            "created_by": user["email"], "updated_at": now_iso(), "updated_by": user["email"],
        })
        imported += 1

    job = {"job_id": new_id("job"), "business_id": business_id, "filename": body.filename,
           "mapping": m, "rows_imported": imported, "duplicates": duplicates, "skipped": skipped,
           "errors": errors, "created_at": now_iso(), "created_by": user["email"]}
    await db.import_jobs.insert_one(job)
    await audit(business_id, user, "import_job", job["job_id"], "csv_import")
    return {k: v for k, v in job.items() if k != "_id"}


@router.get("/import/jobs")
async def import_jobs(business_id: str = Depends(get_business_id)):
    return await db.import_jobs.find({"business_id": business_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
