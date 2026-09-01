"""Server-side case report as a bank-grade PDF (ReportLab).

The DEMO-SPEC calls the report a genuine differentiator, so it is built to read
as a bank document rather than a debug dump: a titled header block, an executive
summary, the score breakdown that sums visibly to the total, the network around
the account, the transactions that triggered each rule, and the recommended
action with an audit line. Page numbers and an auto-generated footer carry the
case reference throughout.

ReportLab is chosen over WeasyPrint deliberately: it is pure Python with no
system libraries (cairo/pango) to install, so the report cannot fail to build
on a fresh machine mid-demo.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Palette from the brief, as ReportLab colours.
INK = colors.HexColor("#0B2545")
TEAL = colors.HexColor("#17A398")
ALERT = colors.HexColor("#C1121F")
MUTED = colors.HexColor("#5B6780")
LINE = colors.HexColor("#D5DCE8")
WASH = colors.HexColor("#F1F4F9")

_BAND_COLOUR = {
    "ALLOW": colors.HexColor("#8090AE"),
    "ENHANCED_MONITORING": colors.HexColor("#D9A441"),
    "STEP_UP_AUTH": colors.HexColor("#E08A1E"),
    "MANUAL_REVIEW": colors.HexColor("#D2691E"),
    "FREEZE": ALERT,
}


def case_reference(account_id: str, generated_at: str) -> str:
    """A stable case reference from the account and generation day.

    Deterministic so the same case re-reports under the same reference within a
    day -- an auditor can quote it and find the same document.
    """
    digest = hashlib.sha1(f"{account_id}:{generated_at[:10]}".encode()).hexdigest()[:6].upper()
    return f"FG-{generated_at[:10].replace('-', '')}-{digest}"


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], textColor=INK, fontSize=20, spaceAfter=2, leading=24
        ),
        "sub": ParagraphStyle("sub", parent=base["Normal"], textColor=MUTED, fontSize=9.5),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], textColor=INK, fontSize=12.5, spaceBefore=14, spaceAfter=6
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], textColor=INK, fontSize=10, leading=15
        ),
        "cell": ParagraphStyle("cell", parent=base["Normal"], textColor=INK, fontSize=8.5, leading=11),
        "cellhead": ParagraphStyle(
            "cellhead", parent=base["Normal"], textColor=colors.white, fontSize=8.5, leading=11
        ),
    }
    return styles


def _money(value: float) -> str:
    return f"Rs {value:,.0f}"


def _pdf_text(text: str) -> str:
    """Make text safe for ReportLab's base-14 fonts.

    The composer uses the rupee sign for the web UI, but Helvetica has no glyph
    for it and would render a tofu box. Swapping to "Rs" keeps the PDF clean
    without pulling in an embedded Unicode font.
    """
    return (text or "").replace("₹", "Rs ")


def build_report_pdf(case: dict[str, Any], analysis, ring: dict | None = None) -> bytes:
    """Render a case report to PDF bytes."""
    styles = _styles()
    generated_at = case.get("generated_at") or dt.datetime.now().isoformat()
    ref = case_reference(case["account_id"], generated_at)
    band_code = case.get("band_code", "ALLOW")
    band_colour = _BAND_COLOUR.get(band_code, MUTED)

    buffer = io.BytesIO()

    def _decorate(canvas, doc):
        canvas.saveState()
        # Header band.
        canvas.setFillColor(INK)
        canvas.rect(0, A4[1] - 18 * mm, A4[0], 18 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(18 * mm, A4[1] - 12 * mm, "FinGuard AI")
        canvas.setFillColor(TEAL)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(48 * mm, A4[1] - 12 * mm, "Fraud case report")
        canvas.setFillColor(colors.HexColor("#B9C6DC"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm, ref)
        # Footer.
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(
            18 * mm,
            11 * mm,
            f"Auto-generated {generated_at[:16].replace('T', ' ')}  -  case {ref}  -  "
            f"FinGuard AI. Integrations to core banking are mocked.",
        )
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=20 * mm,
        title=f"FinGuard case {ref}",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body"
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_decorate)])

    story: list = []

    # -- title block -------------------------------------------------------
    story.append(Paragraph(f"Case {ref}", styles["title"]))
    story.append(
        Paragraph(
            f"Account <b>{case['account_id']}</b> &nbsp;|&nbsp; generated "
            f"{generated_at[:16].replace('T', ' ')}",
            styles["sub"],
        )
    )
    story.append(Spacer(1, 8))

    score_tbl = Table(
        [
            [
                Paragraph(f"<b>{case['score']} / 100</b>", styles["title"]),
                Paragraph(
                    f"<b>{case['band_label']}</b><br/>"
                    f"<font color='#5B6780' size=8>Recommended action</font>",
                    styles["body"],
                ),
            ]
        ],
        colWidths=[35 * mm, None],
    )
    score_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), band_colour),
                ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
                ("BACKGROUND", (1, 0), (1, 0), WASH),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ]
        )
    )
    story.append(score_tbl)

    # -- executive summary -------------------------------------------------
    story.append(Paragraph("Executive summary", styles["h2"]))
    story.append(Paragraph(_pdf_text(case.get("summary", "")), styles["body"]))
    if case.get("evidence_note"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<i>{_pdf_text(case['evidence_note'])}</i>", styles["sub"]))

    # -- score breakdown ---------------------------------------------------
    story.append(Paragraph("Score breakdown", styles["h2"]))
    rows = [
        [
            Paragraph("<b>Rule</b>", styles["cellhead"]),
            Paragraph("<b>Condition met</b>", styles["cellhead"]),
            Paragraph("<b>Points</b>", styles["cellhead"]),
            Paragraph("<b>Fired</b>", styles["cellhead"]),
        ]
    ]
    counted_total = 0
    for row in case.get("breakdown", []):
        if row["counted"]:
            counted_total += row["points"]
        rows.append(
            [
                Paragraph(f"<b>{row['rule_id']}</b> {row['rule_name']}", styles["cell"]),
                Paragraph(row["message"], styles["cell"]),
                Paragraph(f"+{row['points']}" if row["counted"] else "0", styles["cell"]),
                Paragraph(row["timestamp"][11:16], styles["cell"]),
            ]
        )
    rows.append(
        [
            Paragraph("<b>Total</b>", styles["cell"]),
            Paragraph("", styles["cell"]),
            Paragraph(f"<b>{counted_total}</b>", styles["cell"]),
            Paragraph("", styles["cell"]),
        ]
    )
    breakdown = Table(rows, colWidths=[52 * mm, None, 16 * mm, 14 * mm])
    breakdown.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, WASH]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E7ECF4")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, INK),
                ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(breakdown)

    # -- network summary ---------------------------------------------------
    if ring:
        story.append(Paragraph("Network summary", styles["h2"]))
        story.append(
            Paragraph(
                f"{ring['count']} accounts move within a detected mule ring, with "
                f"{_money(ring['value_in_motion'])} in motion among them.",
                styles["body"],
            )
        )
        net_rows = [
            [
                Paragraph("<b>Account</b>", styles["cellhead"]),
                Paragraph("<b>Score</b>", styles["cellhead"]),
                Paragraph("<b>Band</b>", styles["cellhead"]),
            ]
        ]
        for member in ring["accounts"]:
            score = analysis.scores.get(member)
            net_rows.append(
                [
                    Paragraph(member, styles["cell"]),
                    Paragraph(str(score.score if score else 0), styles["cell"]),
                    Paragraph(score.band_label if score else "Allow", styles["cell"]),
                ]
            )
        net = Table(net_rows, colWidths=[40 * mm, 20 * mm, None])
        net.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WASH]),
                    ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(net)

    # -- transaction appendix ---------------------------------------------
    evidence = case.get("evidence", [])
    if evidence:
        story.append(Paragraph("Transaction appendix", styles["h2"]))
        ev_rows = [
            [
                Paragraph("<b>When</b>", styles["cellhead"]),
                Paragraph("<b>From</b>", styles["cellhead"]),
                Paragraph("<b>To</b>", styles["cellhead"]),
                Paragraph("<b>Amount</b>", styles["cellhead"]),
                Paragraph("<b>Rule</b>", styles["cellhead"]),
            ]
        ]
        for row in evidence:
            ev_rows.append(
                [
                    Paragraph(row["timestamp"][5:16].replace("T", " "), styles["cell"]),
                    Paragraph(row["from_account"], styles["cell"]),
                    Paragraph(row["to_account"], styles["cell"]),
                    Paragraph(_money(row["amount"]), styles["cell"]),
                    Paragraph(", ".join(row["cited_by"]), styles["cell"]),
                ]
            )
        appendix = Table(ev_rows, colWidths=[28 * mm, 30 * mm, 30 * mm, 28 * mm, None])
        appendix.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WASH]),
                    ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(appendix)

    # -- recommended action + audit trail ---------------------------------
    story.append(Paragraph("Recommended action and audit trail", styles["h2"]))
    action = case.get("recommended_action") or {}
    audit = (
        f"<b>{action.get('label', 'No action')}</b> &mdash; {action.get('detail', '')}<br/>"
        f"<font color='#5B6780' size=8>Basis: {action.get('reason', 'n/a')}</font>"
    )
    story.append(Paragraph(audit, styles["body"]))
    story.append(Spacer(1, 4))
    status = []
    if case.get("reported"):
        status.append("Case filed")
    if case.get("frozen"):
        status.append("Accounts frozen")
    story.append(
        Paragraph(
            f"<font color='#5B6780' size=8>Status: "
            f"{', '.join(status) if status else 'Recommendation issued; awaiting analyst action'}."
            f" All scoring is rule-based and every point above traces to a named rule.</font>",
            styles["sub"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
