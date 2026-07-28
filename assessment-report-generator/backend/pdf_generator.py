import os
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak

# Palette follows the reference notice-style certificate: near-black body/title
# text, a navy institution wordmark, and a single accent color reserved for the
# performance highlight blocks (mirrors the reference's orange bucket blocks).
BRAND_COLOR = colors.HexColor("#1a3c6e")
TEXT_DARK = colors.HexColor("#1a1a1a")
RULE_COLOR = colors.HexColor("#999999")
ACCENT_ORANGE = colors.HexColor("#e08900")
FOOTER_GRAY = colors.HexColor("#666666")

PASS_THRESHOLD = 70
PAGE_WIDTH_PT = 480  # usable width inside 20mm margins on A4, in points


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("Brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=15, textColor=BRAND_COLOR),
        "tagline": ParagraphStyle("Tagline", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, textColor=colors.HexColor("#666666"), alignment=TA_RIGHT),
        "title": ParagraphStyle("TitleStyle", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, textColor=TEXT_DARK, alignment=TA_CENTER, spaceBefore=4, spaceAfter=2),
        "subtitle": ParagraphStyle("SubtitleStyle", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, textColor=TEXT_DARK, alignment=TA_CENTER, spaceAfter=10),
        "section": ParagraphStyle("SectionHeader", parent=base["Heading3"], fontSize=11, textColor=TEXT_DARK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=TEXT_DARK),
        "bodyBold": ParagraphStyle("BodyBold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=13.5, textColor=TEXT_DARK),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontSize=9.5, leading=13, leftIndent=12, textColor=TEXT_DARK),
        "footer": ParagraphStyle("Footer", parent=base["Normal"], fontSize=7.5, leading=10, textColor=FOOTER_GRAY),
        "notice": ParagraphStyle("Notice", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#9a5b00"), backColor=colors.HexColor("#fff7ea"), borderColor=ACCENT_ORANGE, borderWidth=0.5, padding=4),
    }


def _has_scoring_basis(student):
    """False for data with no numeric scores or percentile at all (e.g. a pure
    survey/questionnaire row) — where an 'Overall Score: 0/100' would be misleading."""
    return bool(student.get("scores")) or student.get("percentile") is not None


def _overall_score(student):
    scores = student.get("scores", {}) or {}
    numeric_scores = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    if numeric_scores:
        return round(sum(numeric_scores) / len(numeric_scores), 1)
    percentile = student.get("percentile")
    if percentile is not None:
        return round(float(percentile), 1)
    return 0.0


def _result_label(score):
    return "Meets Expectations" if score >= PASS_THRESHOLD else "Needs Improvement"


def _bucket(score):
    return "meets" if score >= PASS_THRESHOLD else "needs"


def _page_header(student, styles):
    """Institution wordmark + tagline row, mirroring the reference's logo lockup."""
    institution = _xml_escape(student.get("institution", "Assessment & Reporting System"))
    row = Table(
        [[Paragraph(institution, styles["brand"]), Paragraph("student assessment reporting", styles["tagline"])]],
        colWidths=[280, 200],
    )
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [row, Spacer(1, 4), HRFlowable(width="100%", thickness=1, color=BRAND_COLOR), Spacer(1, 10)]


def _title_block(title, subtitle, styles):
    return [Paragraph(title, styles["title"]), Paragraph(subtitle, styles["subtitle"])]


def _build_notice_table(student, result_label):
    now = datetime.now()
    date_str = f"{now.month}/{now.day}/{now.year}"
    rows = [
        [f"Candidate: {student.get('name', 'N/A')}", f"Assessment Date: {date_str}"],
        [f"Candidate ID: {student.get('id', 'N/A')}", f"Class / Section: {student.get('class', 'N/A')}"],
    ]
    if _has_scoring_basis(student):
        rows.append([f"Overall Score: {_overall_score(student):.0f}/100", f"Result: {result_label}"])
    table = Table(rows, colWidths=[PAGE_WIDTH_PT / 2, PAGE_WIDTH_PT / 2])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#444444")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_DARK),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _build_breakdown_table(student):
    """Subject performance table with same-bucket rows merged into one highlight
    block per column, mirroring the reference certificate's section table."""
    scores = student.get("scores", {}) or {}
    items = []
    for subject, score in scores.items():
        try:
            items.append((subject, float(score)))
        except (TypeError, ValueError):
            continue
    if not items:
        return None

    header = ["Subject", "Score (%)", "Needs\nImprovement", "Meets\nExpectations"]
    rows = [header]
    buckets = []
    for subject, score in items:
        rows.append([subject, f"{score:.1f}", "", ""])
        buckets.append(_bucket(score))

    col_widths = [150, 70, 130, 130]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]

    col_for_bucket = {"needs": 2, "meets": 3}
    start = 0
    for i in range(1, len(buckets) + 1):
        if i == len(buckets) or buckets[i] != buckets[start]:
            row_start, row_end = start + 1, i  # +1 to skip the header row
            col = col_for_bucket[buckets[start]]
            if row_end > row_start:
                style.append(("SPAN", (col, row_start), (col, row_end)))
            style.append(("BACKGROUND", (col, row_start), (col, row_end), ACCENT_ORANGE))
            start = i

    table.setStyle(TableStyle(style))
    return table


def _render_custom_sections(sections, styles):
    """Renders the optional custom_sections the model produces when the event
    prompt box asks for specific extra content (e.g. listing survey Q&A)."""
    elements = []
    for section in sections:
        heading = _xml_escape(section.get("heading") or "Additional Details")
        elements.append(Paragraph(heading.upper(), styles["section"]))
        content = _xml_escape(section.get("content") or "").replace("\n", "<br/>")
        elements.append(Paragraph(content or "(no content provided)", styles["body"]))
        elements.append(Spacer(1, 6))
    return elements


def generate_pdf(student, narrative, output_path, fallback=False):
    """Renders a formal notice-and-breakdown PDF, styled after an official exam
    results certificate: page 1 is a results notice with a bordered candidate
    table, page 2 breaks down subject performance into a highlighted table,
    page 3 carries the AI-generated personalized insights."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    styles = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    narrative = narrative or {}
    # LLM/CSV-derived text can contain characters (&, <, >) that would break reportlab's
    # mini-XML Paragraph parser, so escape everything free-form before it's rendered.
    summary = _xml_escape(narrative.get("summary") or narrative.get("performance_summary") or "No summary available.")
    strengths = [_xml_escape(s) for s in (narrative.get("strengths") or [])]
    improvements = [_xml_escape(s) for s in (narrative.get("improvements") or [])]
    recommendations = [_xml_escape(s) for s in (narrative.get("recommendations") or [])]
    career_guidance = _xml_escape(narrative.get("career_guidance") or "No career guidance available.")
    overall_insight = _xml_escape(narrative.get("overall_insight") or "No overall insight available.")
    custom_sections = narrative.get("custom_sections") or []

    has_scores = _has_scoring_basis(student)
    overall_score = _overall_score(student) if has_scores else None
    result_label = _result_label(overall_score) if has_scores else None
    name = _xml_escape(student.get("name", "This student"))

    elements = []
    if fallback:
        elements.append(Paragraph("Fallback content used due to provider issue", styles["notice"]))
        elements.append(Spacer(1, 6))

    # ---------- Page 1: Notice of Assessment Results ----------
    elements += _page_header(student, styles)
    elements += _title_block("STUDENT ASSESSMENT REPORT", "Notice of Assessment Results", styles)
    elements.append(Spacer(1, 4))
    elements.append(_build_notice_table(student, result_label))
    elements.append(Spacer(1, 12))

    if not has_scores:
        headline = f"{name} has completed this assessment. See the personalized insights below for details."
    elif result_label == "Meets Expectations":
        headline = f"Congratulations! {name} has completed this assessment with an overall score of {overall_score:.0f}/100, meeting expectations."
    else:
        headline = f"{name} has completed this assessment with an overall score of {overall_score:.0f}/100. Targeted support is recommended before the next assessment."
    elements.append(Paragraph(headline, styles["bodyBold"]))
    elements.append(Spacer(1, 8))

    if has_scores:
        elements.append(Paragraph(
            f"This assessment is scored on a scale of 0 to 100, combining subject scores, cohort percentile, "
            f"and attendance. A score of {PASS_THRESHOLD} or above is considered as meeting expectations.",
            styles["body"],
        ))
        elements.append(Spacer(1, 8))
    elements.append(Paragraph(summary, styles["body"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "This report is intended for the student, parents/guardians, and assigned faculty only. "
        "For questions about these results, please contact the academic office.",
        styles["body"],
    ))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(career_guidance, styles["body"]))
    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Thank you,", styles["body"]))
    elements.append(Paragraph(_xml_escape(student.get("institution", "Assessment & Reporting Team")), styles["bodyBold"]))

    # ---------- Page 2: Breakdown of Assessment Results ----------
    elements.append(PageBreak())
    elements += _page_header(student, styles)
    elements += _title_block("STUDENT ASSESSMENT REPORT", "Breakdown of Assessment Results", styles)
    elements.append(Spacer(1, 4))

    breakdown_table = _build_breakdown_table(student)
    if breakdown_table is not None:
        elements.append(Paragraph(
            "The table below details performance across each subject area assessed. Since subjects may carry "
            "different difficulty and weighting, this breakdown highlights relative strengths and areas for "
            "improvement rather than being read in isolation.",
            styles["body"],
        ))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(
            f"<b>Meets Expectations:</b> performance at or above {PASS_THRESHOLD}/100, in line with what's expected "
            "of a student progressing well in this subject.",
            styles["body"],
        ))
        elements.append(Paragraph(
            f"<b>Needs Improvement:</b> performance below {PASS_THRESHOLD}/100, indicating this subject would "
            "benefit from additional focus.",
            styles["body"],
        ))
        elements.append(Spacer(1, 10))
        elements.append(breakdown_table)
        elements.append(Spacer(1, 12))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            "Disclaimer: overall results are calculated using the complete set of subject scores. Subject-level "
            "results are provided for general feedback only and are less reliable than the overall score; they "
            "should not be used alone to guide future performance decisions.",
            styles["footer"],
        ))
    else:
        elements.append(Paragraph(
            "No subject-level scores were recorded for this student — see Personalized Insights for the "
            "AI-generated analysis based on the information provided.",
            styles["body"],
        ))

    # ---------- Page 3: Personalized Insights ----------
    elements.append(PageBreak())
    elements += _page_header(student, styles)
    elements += _title_block("STUDENT ASSESSMENT REPORT", "Personalized Insights", styles)
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("KEY STRENGTHS", styles["section"]))
    for item in strengths or ["No strengths were provided."]:
        elements.append(Paragraph(f"• {item}", styles["bullet"]))

    elements.append(Paragraph("IMPROVEMENT AREAS", styles["section"]))
    for item in improvements or ["No improvement areas were provided."]:
        elements.append(Paragraph(f"• {item}", styles["bullet"]))

    elements.append(Paragraph("RECOMMENDATIONS", styles["section"]))
    for item in recommendations or ["No recommendations available."]:
        elements.append(Paragraph(f"• {item}", styles["bullet"]))

    elements.append(Paragraph("OVERALL INSIGHT", styles["section"]))
    elements.append(Paragraph(overall_insight, styles["body"]))

    # ---------- Page 4 (optional): content requested via the event prompt box ----------
    if custom_sections:
        elements.append(PageBreak())
        elements += _page_header(student, styles)
        elements += _title_block("STUDENT ASSESSMENT REPORT", "Additional Details", styles)
        elements.append(Spacer(1, 4))
        elements += _render_custom_sections(custom_sections, styles)

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("Generated by AI Assessment System", ParagraphStyle("FooterCenter", parent=styles["footer"], alignment=TA_CENTER)))

    doc.build(elements)
    return output_path
