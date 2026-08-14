"""Payslip PDF generation (Phase 3) using reportlab (already in requirements).
Original UrbanDotted layout — no branding copied from any reference payslip.
Renders from an immutable snapshot; NEVER recalculates.
"""
from __future__ import annotations
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak)

BRAND = colors.HexColor("#0F291E")   # UrbanDotted deep green
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E5E7EB")
LIGHT = colors.HexColor("#F5F5F0")

_styles = getSampleStyleSheet()


def _d(cents: int) -> str:
    from decimal import Decimal, ROUND_HALF_UP
    v = (Decimal(int(cents or 0)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    n = f"{v:,.2f}"
    return f"-${n[1:]}" if v < 0 else f"${n}"


def _title(txt, size=18, color=BRAND):
    return Paragraph(f'<font size="{size}" color="{color.hexval()}"><b>{txt}</b></font>', _styles["Normal"])


def _small(txt, color=MUTED, size=8):
    return Paragraph(f'<font size="{size}" color="{color.hexval()}">{txt}</font>', _styles["Normal"])


def _kv_table(rows, widths=(45 * mm, 55 * mm)):
    t = Table(rows, colWidths=list(widths))
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 10 * mm,
        "Urban Dotted Expense Book — bookkeeping software. Payslip figures are prepared for your accountant/registered tax agent."
        " PAYG is entered manually; not verified against ATO tax tables. Super amounts shown are employer liabilities, not confirmed transfers.")
    canvas.drawRightString(200 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_payslip_pdf(snap: dict) -> bytes:
    """`snap` is the immutable payslip snapshot dict. Deterministic renderer."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=18 * mm,
                            title=f"Payslip {snap.get('payslip_ref')}")

    story = []
    voided = snap.get("status") == "voided"

    # Header row: brand + payslip ref
    emp = snap.get("employer") or {}
    e = snap.get("employee") or {}
    header = Table([[
        Paragraph(f'<font size="16" color="{BRAND.hexval()}"><b>urban<i>dotted</i></b></font>'
                  f'<br/><font size="7" color="{MUTED.hexval()}">Expense Book &middot; Payslip</font>',
                  _styles["Normal"]),
        Paragraph(
            f'<para align="right"><font size="9" color="{MUTED.hexval()}">Payslip ref</font><br/>'
            f'<font size="12"><b>{snap.get("payslip_ref", "")}</b></font><br/>'
            f'<font size="8" color="{MUTED.hexval()}">Pay run {snap.get("pay_run_ref", "")}</font></para>',
            _styles["Normal"]),
    ]], colWidths=[110 * mm, 70 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)

    if voided:
        story.append(Spacer(1, 4))
        story.append(Table([[Paragraph(
            f'<font size="10" color="#B45309"><b>VOIDED &middot; {snap.get("void_reason","")}</b>'
            f'<br/><font size="7">This payslip has been voided and is preserved for audit only.</font></font>',
            _styles["Normal"])]], colWidths=[180 * mm], style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B45309")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])))

    story.append(Spacer(1, 6))

    # Two-column identity block
    ident = Table([[
        _kv_table([
            [_small("EMPLOYEE"), ""],
            ["Name", f"{e.get('first_name','')} {e.get('last_name','')}".strip()],
            ["Employee ID", e.get("employee_id", "")],
            ["Address", e.get("address_line", "")],
        ]),
        _kv_table([
            [_small("EMPLOYER"), ""],
            ["Legal name", emp.get("legal_business_name", "")],
            ["Trading name", emp.get("trading_name", "")],
            ["ABN", emp.get("abn", "")],
        ]),
    ]], colWidths=[90 * mm, 90 * mm])
    story.append(ident)
    story.append(Spacer(1, 6))

    # Pay information
    story.append(_kv_table([
        [_small("PAY PERIOD"), f"{snap.get('period_start','')} → {snap.get('period_end','')}"],
        [_small("PAYMENT DATE"), snap.get("payment_date", "")],
        [_small("PAY FREQUENCY"), (snap.get("pay_frequency", "") or "").title()],
        [_small("STANDARD HOURS"), snap.get("standard_hours", "—")],
    ], widths=(45 * mm, 135 * mm)))
    story.append(Spacer(1, 8))

    # Pay details table
    lines = snap.get("earning_lines", [])
    data = [["Description", "Hours / Units", "Rate", "Amount"]]
    for L in lines:
        rate = _d(L.get("rate_cents", 0)) if L.get("calc_type") != "fixed" else "—"
        data.append([L.get("label", ""), str(L.get("hours_or_units", "")), rate, _d(L.get("amount_cents", 0))])
    if len(data) == 1:
        data.append(["Ordinary earnings", "", "", _d(snap.get("gross_cents", 0))])
    t = Table(data, colWidths=[80 * mm, 30 * mm, 30 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # Summary
    def row(label, val, bold=False):
        style = ("Helvetica-Bold", 9) if bold else ("Helvetica", 9)
        return [Paragraph(f'<font name="{style[0]}" size="{style[1]}">{label}</font>', _styles["Normal"]),
                Paragraph(f'<para align="right"><font name="{style[0]}" size="{style[1]}">{val}</font></para>', _styles["Normal"])]

    summary_rows = [
        row("Total Gross", _d(snap.get("gross_cents", 0))),
        row("Before-tax Deductions", "-" + _d(snap.get("pretax_ded_cents", 0)) if snap.get("pretax_ded_cents") else _d(0)),
        row("Taxable Gross", _d(snap.get("taxable_cents", 0))),
        row("PAYG Withholding (manual)", "-" + _d(snap.get("payg_cents", 0)) if snap.get("payg_cents") else _d(0)),
        row("After-tax Deductions", "-" + _d(snap.get("posttax_ded_cents", 0)) if snap.get("posttax_ded_cents") else _d(0)),
        row("NET PAY", _d(snap.get("net_cents", 0)), bold=True),
    ]
    s = Table(summary_rows, colWidths=[130 * mm, 50 * mm])
    s.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.75, BRAND),
                           ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(s)
    story.append(Spacer(1, 8))

    # Super + leave + YTD
    sup = snap.get("super") or {}
    story.append(Table([[
        _kv_table([
            [_small("EMPLOYER SUPER"), ""],
            ["Fund", sup.get("fund_name", "—")],
            ["Rate", f"{sup.get('sg_rate','')}"],
            ["Amount (liability)", _d(snap.get("super_cents", 0))],
        ]),
        _kv_table([
            [_small("LEAVE BALANCES"), ""],
            *(([lb.get("leave_type", ""), f"{lb.get('remaining_hours','0')} h"]
              for lb in (snap.get("leave_balances") or []))
              or [["—", ""]]),
        ]),
    ]], colWidths=[90 * mm, 90 * mm]))
    story.append(Spacer(1, 6))

    ytd = snap.get("ytd") or {}
    ytd_rows = [["", "This Pay", "YTD"]]
    for label, key_this, key_ytd in [
        ("Gross", "gross_cents", "gross_cents"),
        ("Pre-tax Deductions", "pretax_ded_cents", "pretax_ded_cents"),
        ("Taxable Gross", "taxable_cents", "taxable_cents"),
        ("PAYG Withholding", "payg_cents", "payg_cents"),
        ("After-tax Deductions", "posttax_ded_cents", "posttax_ded_cents"),
        ("Net Pay", "net_cents", "net_cents"),
        ("Employer Super", "super_cents", "super_cents"),
    ]:
        ytd_rows.append([label, _d(snap.get(key_this, 0)), _d(ytd.get(key_ytd, 0))])
    y = Table(ytd_rows, colWidths=[90 * mm, 45 * mm, 45 * mm])
    y.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(y)

    # Optional employee message
    if snap.get("employee_message"):
        story.append(Spacer(1, 8))
        story.append(_small(f"<b>Message:</b> {snap['employee_message']}", color=colors.black, size=8))

    # Page 2 (day-by-day) if we have dated lines
    dated = [L for L in lines if L.get("date")]
    if dated:
        story.append(PageBreak())
        story.append(_title("Payroll Details", size=13))
        story.append(Spacer(1, 6))
        d = [["Date", "Pay Item", "Hours / Units", "Rate", "Amount"]]
        for L in sorted(dated, key=lambda x: x.get("date", "")):
            rate = _d(L.get("rate_cents", 0)) if L.get("calc_type") != "fixed" else "—"
            d.append([L.get("date", ""), L.get("label", ""), str(L.get("hours_or_units", "")), rate, _d(L.get("amount_cents", 0))])
        pd = Table(d, colWidths=[25 * mm, 75 * mm, 30 * mm, 25 * mm, 25 * mm])
        pd.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(pd)

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()
