"""Payroll reports PDF generation (Phase 4).

Uses reportlab (already in requirements). Follows the same design language
as `payroll_pdf.py`. Each report is a deterministic renderer that takes a
pre-computed dict and returns bytes.
"""
from __future__ import annotations

from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer)

BRAND = colors.HexColor("#0F291E")
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E5E7EB")
LIGHT = colors.HexColor("#F5F5F0")
WARN = colors.HexColor("#B45309")

_styles = getSampleStyleSheet()


def _money(cents):
    v = (Decimal(int(cents or 0)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{v:,.2f}"
    return f"-${s[1:]}" if v < 0 else f"${s}"


def _head(text, size=16):
    return Paragraph(
        f'<font size="{size}" color="{BRAND.hexval()}"><b>{text}</b></font>',
        _styles["Normal"])


def _muted(text, size=8):
    return Paragraph(
        f'<font size="{size}" color="{MUTED.hexval()}">{text}</font>',
        _styles["Normal"])


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 10 * mm,
        "Urban Dotted Expense Book — payroll report prepared for review by "
        "your accountant / registered tax agent. Not an ATO lodgement.")
    canvas.drawRightString(285 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _title_block(employer: dict, title: str, subtitle: str = ""):
    emp = employer or {}
    return Table([[
        Paragraph(
            f'<font size="16" color="{BRAND.hexval()}"><b>urban<i>dotted</i></b></font>'
            f'<br/><font size="7" color="{MUTED.hexval()}">'
            f'{(emp.get("legal_business_name") or "").strip()} '
            f'{("ABN " + emp.get("abn")) if emp.get("abn") else ""}</font>',
            _styles["Normal"]),
        Paragraph(
            f'<para align="right"><font size="12" color="{BRAND.hexval()}"><b>{title}</b></font>'
            + (f'<br/><font size="8" color="{MUTED.hexval()}">{subtitle}</font>'
               if subtitle else "") + "</para>",
            _styles["Normal"]),
    ]], colWidths=[130 * mm, 130 * mm])


def _table(header: list, rows: list, col_widths: list,
           right_align_from: int = 1, footer_row: bool = False):
    data = [header] + rows
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER),
        ("ALIGN", (right_align_from, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if footer_row and len(data) > 1:
        style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        style.append(("BACKGROUND", (0, -1), (-1, -1), LIGHT))
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(style))
    return t


def build_summary_pdf(data: dict, employer: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"Payroll Summary {data.get('fy','')}")
    story = []
    sub = f"FY {data['fy']}"
    if data.get("period_start") or data.get("period_end"):
        sub += f" · {data.get('period_start','')} → {data.get('period_end','')}"
    story.append(_title_block(employer, "Payroll Summary", sub))
    story.append(Spacer(1, 8))

    rows = []
    for r in data.get("rows", []):
        rows.append([r["employee_name"], str(r.get("payslip_count", 0)),
                     _money(r["gross_cents"]),
                     _money(r["pretax_ded_cents"]),
                     _money(r["taxable_cents"]),
                     _money(r["payg_cents"]),
                     _money(r["posttax_ded_cents"]),
                     _money(r["net_cents"]),
                     _money(r["super_cents"])])
    if not rows:
        story.append(_muted("No finalised payslips in this period."))
    else:
        t = data.get("totals") or {}
        rows.append(["TOTAL", str(t.get("payslip_count", 0)),
                     _money(t.get("gross_cents", 0)),
                     _money(t.get("pretax_ded_cents", 0)),
                     _money(t.get("taxable_cents", 0)),
                     _money(t.get("payg_cents", 0)),
                     _money(t.get("posttax_ded_cents", 0)),
                     _money(t.get("net_cents", 0)),
                     _money(t.get("super_cents", 0))])
        story.append(_table(
            ["Employee", "Slips", "Gross", "Pre-tax Ded.", "Taxable",
             "PAYG", "Post-tax Ded.", "Net", "Employer Super"],
            rows,
            [55 * mm, 15 * mm] + [26 * mm] * 7,
            right_align_from=1, footer_row=True,
        ))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_payment_summary_pdf(data: dict, employer: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"Payment Summary {data.get('fy','')}")
    story = []
    story.append(_title_block(employer, "Payment Summary", f"FY {data['fy']}"))
    story.append(Spacer(1, 6))
    story.append(_muted(
        "Employer-prepared summary of gross, tax and super for the FY. "
        "Not an STP finalisation; verify amounts with your accountant."))
    story.append(Spacer(1, 8))

    if not data.get("rows"):
        story.append(_muted("No finalised payslips in this financial year."))
    for r in data["rows"]:
        story.append(_head(f"{r['employee_name']}", size=11))
        story.append(_muted(r.get("address_line", "")))
        story.append(Spacer(1, 4))
        rows = [
            ["Period", f"{r.get('period_start','')} → {r.get('period_end','')}"],
            ["Payslips issued", str(r.get("payslip_count", 0))],
            ["Gross earnings", _money(r["gross_cents"])],
            ["Pre-tax deductions", _money(r["pretax_ded_cents"])],
            ["Taxable earnings", _money(r["taxable_cents"])],
            ["PAYG withheld (manual)", _money(r["payg_cents"])],
            ["Post-tax deductions", _money(r["posttax_ded_cents"])],
            ["Net pay", _money(r["net_cents"])],
            ["Employer super (liability)", _money(r["super_cents"])],
        ]
        story.append(_table(["Item", "Value"], rows,
                             [70 * mm, 80 * mm], right_align_from=1))
        story.append(Spacer(1, 8))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_super_pdf(data: dict, employer: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"Super Payable {data.get('fy','')}")
    story = []
    sub = f"FY {data['fy']}"
    if data.get("quarter"):
        sub += f" · {data['quarter']}"
    story.append(_title_block(employer, "Super Payable by Quarter", sub))
    story.append(Spacer(1, 6))
    story.append(_muted("Employer super is tracked. Payments are NOT transferred automatically."))
    story.append(Spacer(1, 6))

    if not data.get("quarters"):
        story.append(_muted("No super liabilities accrued in this period."))
    for q in data["quarters"]:
        story.append(_head(
            f"{q['quarter']} — {q['period_start']} → {q['period_end']} · Due {q['due_date']}",
            size=11))
        story.append(Spacer(1, 4))
        rows = []
        for it in q["employees"]:
            status = it["status"]
            if it["is_overdue"]:
                status = f"OVERDUE · {status}"
            rows.append([it["employee_name"], it.get("fund_name", ""),
                         _money(it["accrued_cents"]),
                         _money(it["paid_cents"]),
                         _money(it["outstanding_cents"]),
                         status])
        rows.append(["TOTAL", "",
                     _money(q["accrued_cents"]),
                     _money(q["paid_cents"]),
                     _money(q["outstanding_cents"]),
                     ""])
        story.append(_table(
            ["Employee", "Fund", "Accrued", "Paid", "Outstanding", "Status"],
            rows,
            [45 * mm, 40 * mm, 25 * mm, 25 * mm, 30 * mm, 25 * mm],
            right_align_from=2, footer_row=True,
        ))
        story.append(Spacer(1, 8))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_leave_balances_pdf(data: dict, employer: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title="Leave Balances")
    story = []
    story.append(_title_block(employer, "Leave Balances Snapshot",
                                data.get("generated_at", "")[:10]))
    story.append(Spacer(1, 8))
    if not data.get("rows"):
        story.append(_muted("No leave balances recorded."))
    for r in data["rows"]:
        story.append(_head(r["employee_name"], size=11))
        rows = []
        for t, v in sorted(r["by_type"].items()):
            rows.append([t.replace("_", " ").title(),
                         v.get("entitled_hours", "0"),
                         v.get("future_approved_hours", "0"),
                         v.get("remaining_hours", "0")])
        if rows:
            story.append(_table(
                ["Leave type", "Entitled (h)", "Future approved (h)", "Remaining (h)"],
                rows,
                [55 * mm, 35 * mm, 45 * mm, 35 * mm],
                right_align_from=1,
            ))
        else:
            story.append(_muted("No leave types configured."))
        story.append(Spacer(1, 8))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


__all__ = ["build_summary_pdf", "build_payment_summary_pdf",
           "build_super_pdf", "build_leave_balances_pdf"]
