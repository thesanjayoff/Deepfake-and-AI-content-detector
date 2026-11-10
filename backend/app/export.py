"""JSON and PDF report export. PDF uses reportlab -- no external service calls."""
from __future__ import annotations

import io
import json
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERDICT_LABELS = {
    "likely_authentic": "Likely Authentic",
    "inconclusive": "Inconclusive",
    "likely_manipulated": "Likely Manipulated or AI-Generated",
}


def to_json_bytes(record: dict[str, Any]) -> bytes:
    return json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8")


def _escape(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def to_pdf_bytes(record: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBig", parent=styles["Title"], fontSize=18)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"])
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey)

    report = record.get("report", {})
    combination = report.get("combination", {})
    verdict = VERDICT_LABELS.get(combination.get("verdict"), combination.get("verdict", "Unknown"))

    elements = []
    elements.append(Paragraph("Deepfake & AI-Content Detector -- Evidence Report", title_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "<b>This report is evidence to help a human judge content authenticity. It is NOT proof.</b>",
        body,
    ))
    elements.append(Spacer(1, 10))

    meta_rows = [
        ["File", _escape(record.get("original_name", ""))],
        ["Media type", record.get("media_type", "")],
        ["Analyzed at", record.get("created_at", "")],
        ["SHA-256", record.get("sha256", "")],
        ["Overall result", verdict],
        ["Confidence band", combination.get("confidence_band", "")],
    ]
    t = Table(meta_rows, colWidths=[1.6 * inch, 4.9 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(_escape(combination.get("explanation", "")), body))
    elements.append(Spacer(1, 12))

    if report.get("mandatory_warning"):
        elements.append(Paragraph("<b>Mandatory warning:</b> " + _escape(report["mandatory_warning"]), body))
        elements.append(Spacer(1, 10))

    elements.append(HRFlowable(width="100%", color=colors.lightgrey))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Signals", h2))
    for s in report.get("signals", []):
        if not s.get("applicable", True) and s.get("strength", 0) == 0:
            label = f"<b>{_escape(s['label'])}</b> -- not available"
        else:
            label = f"<b>{_escape(s['label'])}</b> (direction {s['direction']:.2f}, strength {s['strength']:.2f})"
        elements.append(Paragraph(label, body))
        elements.append(Paragraph(_escape(s.get("summary", "")), body))
        elements.append(Paragraph("<i>Limits: " + _escape(s.get("limits", "")) + "</i>", small))
        elements.append(Spacer(1, 6))

    elements.append(PageBreak())
    elements.append(Paragraph("Recommended Human Verification Steps", h2))
    for step in report.get("verification_steps", []):
        elements.append(Paragraph("&bull; " + _escape(step), body))
    elements.append(Spacer(1, 14))
    elements.append(Paragraph(
        "Generated locally by a personal Deepfake & AI-Content Detector. No data leaves this "
        "machine. This is not a certified forensic tool and must not be the sole basis for any "
        "accusation or decision.",
        small,
    ))

    doc.build(elements)
    return buf.getvalue()
