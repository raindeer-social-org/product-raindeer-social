"""Renders a Brand's `brand_report` JSONB column to a formatted PDF.

The report is produced by the onboarding agent (packages/agents/onboarding)
as a flat JSON object of string-keyed sections — see
packages/agents/onboarding/prompts.py's REQUIRED_REPORT_KEYS for the
authoritative, always-present section list. Any additional keys present on
the dict (future report sections not yet in REQUIRED_REPORT_KEYS) are
rendered too, so this doesn't need to change every time the agent's schema
grows.
"""

import io
import json
from datetime import datetime, timezone

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from packages.agents.onboarding.prompts import REQUIRED_REPORT_KEYS


def _section_title(key: str) -> str:
    """"voice_and_tone" -> "Voice And Tone" """
    return key.replace("_", " ").title()


def _section_body(value: object) -> str:
    # Sections are documented as short strings, but render defensively for
    # any list/dict/number a future report shape might add instead of
    # blowing up the export.
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2)


def _ordered_sections(brand_report: dict) -> list[tuple[str, object]]:
    """Required sections first, in their canonical order, then any extra
    keys (alphabetically) so a growing report shape still renders in full
    without needing this module to be updated in lockstep."""
    ordered_keys = list(REQUIRED_REPORT_KEYS) + sorted(
        k for k in brand_report if k not in REQUIRED_REPORT_KEYS
    )
    return [(key, brand_report[key]) for key in ordered_keys if key in brand_report]


def render_brand_report_pdf(brand_name: str, brand_report: dict) -> bytes:
    """Renders `brand_report` into a PDF and returns the raw bytes.

    Raises ValueError if brand_report is empty/None or is missing any of
    the required sections — an incomplete report shouldn't silently
    produce a half-empty "final" PDF.
    """
    if not brand_report:
        raise ValueError("brand_report is empty — nothing to render")

    missing = [key for key in REQUIRED_REPORT_KEYS if key not in brand_report]
    if missing:
        raise ValueError(f"brand_report is missing required sections: {missing}")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title=f"{brand_name} — Brand Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BrandReportTitle", parent=styles["Title"], spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        "BrandReportSubtitle",
        parent=styles["Normal"],
        textColor="#666666",
        spaceAfter=24,
    )
    heading_style = ParagraphStyle(
        "BrandReportHeading",
        parent=styles["Heading2"],
        spaceBefore=18,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BrandReportBody", parent=styles["BodyText"], spaceAfter=6
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story = [
        Paragraph(f"{brand_name} — Brand Report", title_style),
        Paragraph(f"Generated {generated_at}", subtitle_style),
    ]

    for key, value in _ordered_sections(brand_report):
        story.append(Paragraph(_section_title(key), heading_style))
        # Paragraph text is XML-ish — escape so report content with
        # "&"/"<"/">" (brand names, competitor URLs, etc.) doesn't break
        # rendering or get silently dropped.
        body_text = (
            _section_body(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        story.append(Paragraph(body_text, body_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buffer.getvalue()
