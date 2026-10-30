"""Multi-page Investor Screening Review, following templates/investor_screening_review_template.md.

Cover summary, sections 1-11, sources and disclaimers. Off-white page, coral section
bars and labels, Helvetica-class type, TEN logo on the cover and in the running
header, and the CLAUDE.md standard footer on every page.
"""

from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepInFrame,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ten_screener import review
from ten_screener.pdf.one_page import CONFIDENTIAL_LABEL, DISCLAIMER
from ten_screener.pdf.theme import draw_footer, footer_logo
from ten_screener.schemas import ScreeningReport, SectionAnalysis
from ten_screener.summary import clip

PAGE_W, PAGE_H = LETTER
MARGIN_X = 0.9 * inch
CONTENT_W = PAGE_W - 2 * MARGIN_X - 12  # frame padding
TOP_MARGIN = 1.05 * inch
BOTTOM_MARGIN = 0.8 * inch
COVER_H = PAGE_H - TOP_MARGIN - BOTTOM_MARGIN - 14

# Approximations of the reference document's palette (confirm against TEN brand guidance).
C = {
    "page": HexColor("#FFFCF5"),
    "coral": HexColor("#E8553F"),
    "teal": HexColor("#4BBFD6"),
    "amber": HexColor("#F5A623"),
    "ink": HexColor("#111111"),
    "body": HexColor("#4A4A4A"),
    "muted": HexColor("#8A8A8A"),
    "rule": HexColor("#C9D3DE"),
    "head_bg": HexColor("#F4F4F2"),
    "callout": HexColor("#FFF6E6"),
    "link": HexColor("#1A6FC2"),
}
HIGHLIGHT_COLOURS = ("#E8553F", "#4BBFD6", "#F5A623")

DISCLAIMER_TEN = (
    'Disclaimer: TEN is a "Funding as a Service" program. It is not a registered broker-dealer and does not offer '
    "investment advice or advise on the raising of capital through securities offerings. TEN does not recommend or "
    "otherwise suggest that any investor make an investment in a specific company, or that any company offer "
    "securities to a particular investor. TEN takes no part in the negotiation or execution of transactions for the "
    "purchase or sale of securities, and at no time has possession of funds or securities. No securities transactions "
    "are executed or negotiated on or through the TEN program. TEN receives no compensation in connection with the "
    "purchase or sale of securities."
)

TRACK_REQUIREMENT = {
    "A": "The Track A requirement applies: paying customers and actual revenue from commercial operations.",
    "B": "The Track B requirement applies: a defined regulatory pathway appropriate to the product and target market.",
    "undetermined": "Neither track requirement can be applied until the track is settled.",
}


def _styles() -> dict[str, ParagraphStyle]:
    def ps(name: str, **kw) -> ParagraphStyle:
        base = dict(fontName="Helvetica", fontSize=10.5, leading=15, textColor=C["body"])
        base.update(kw)
        return ParagraphStyle(name, **base)

    return {
        "eyebrow": ps("eyebrow", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=C["coral"]),
        "title": ps("title", fontName="Helvetica-Bold", fontSize=30, leading=35, textColor=C["ink"]),
        "subtitle": ps("subtitle", fontSize=12, leading=17, textColor=C["muted"]),
        "confidential": ps("confidential", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=C["coral"]),
        "tile_label": ps("tile_label", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=C["ink"], alignment=1),
        "tile_value": ps("tile_value", fontName="Helvetica-Bold", fontSize=24, leading=30, textColor=C["ink"], alignment=1),
        "h1": ps("h1", fontName="Helvetica-Bold", fontSize=20, leading=25, textColor=C["ink"], spaceBefore=2, spaceAfter=6),
        "lead": ps("lead", fontName="Helvetica-Bold", fontSize=11, leading=15.5, textColor=C["ink"], spaceAfter=8),
        "body": ps("body", spaceAfter=6),
        "bullet": ps("bullet", leftIndent=14, bulletIndent=3, spaceAfter=4),
        "label": ps("label", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=C["coral"], spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "cell": ps("cell", fontSize=9.5, leading=12.5),
        "cell_b": ps("cell_b", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5, textColor=C["ink"]),
        "cell_h": ps("cell_h", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5, textColor=C["ink"]),
        "note": ps("note", fontSize=8.5, leading=11.5, textColor=C["muted"]),
        "source": ps("source", fontSize=8.5, leading=12, textColor=C["body"], leftIndent=10, bulletIndent=1),
        "callout": ps("callout", fontSize=10.5, leading=15, textColor=C["body"]),
    }


class SectionBar(Flowable):
    """Short coral bar above each section heading."""

    def __init__(self, width: float = 44, height: float = 4):
        super().__init__()
        self.bar_w, self.bar_h = width, height

    def wrap(self, avail_w, avail_h):  # noqa: ANN001, ANN201
        return self.bar_w, self.bar_h + 30  # ~16 pt of air above the bar, 10 pt below

    def draw(self) -> None:
        self.canv.setFillColor(C["coral"])
        self.canv.rect(0, 10, self.bar_w, self.bar_h, stroke=0, fill=1)


def _e(text: str | None) -> str:
    return escape(text or "")


def _ref(report: ScreeningReport, ids: list[str]) -> str:
    ref = report.cite(ids)
    return f" <font color='#8A8A8A' size='8.5'>({escape(ref)})</font>" if ref else ""


def _table(rows: list[list], widths: list[float], s: dict, *, bold_first: bool = True, total_row: bool = False) -> Table:
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, value in enumerate(row):
            if isinstance(value, Paragraph):
                cells.append(value)
                continue
            style = s["cell_h"] if r == 0 else (s["cell_b"] if (c == 0 and bold_first) or (total_row and r == len(rows) - 1) else s["cell"])
            cells.append(Paragraph(_e(str(value)), style))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C["head_bg"]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, C["rule"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _headline_markup(company: str, headline: str, highlights: list[str]) -> str:
    text = escape(headline)
    for i, phrase in enumerate(highlights[:3]):
        colour = HIGHLIGHT_COLOURS[i % 3]
        text = re.sub(re.escape(escape(phrase)), lambda m, c=colour: f"<font color='{c}'>{m.group(0)}</font>", text, count=1, flags=re.IGNORECASE)
    return f"{escape(company)}: {text}" if headline else escape(company)


def _section_head(story: list, number: int, title: str, lead: str, s: dict) -> None:
    story.append(CondPageBreak(1.6 * inch))
    block = [SectionBar(), Paragraph(f"{number}. {_e(title)}", s["h1"])]
    if lead:
        block.append(Paragraph(_e(lead), s["lead"]))
    story.append(KeepTogether(block))


def _first_sentence(text: str) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", text or "")
    return match.group(1) if match else (text or "")


def _labeled_section(story: list, report: ScreeningReport, sec: SectionAnalysis, s: dict) -> None:
    if sec.points:
        for point in sec.points:
            story.append(Paragraph(f"<b>{_e(point.label.rstrip(':'))}:</b> {_e(point.text)}{_ref(report, point.evidence_ids)}",
                                   s["bullet"], bulletText="•"))
        return
    if sec.summary and sec.summary != sec.lead:
        story.append(Paragraph(_e(sec.summary), s["body"]))
    for f in sec.findings:
        story.append(Paragraph(f"<b>{_e(f.headline)}</b> {_e(f.detail)}{_ref(report, f.evidence_ids)}", s["bullet"], bulletText="•"))


def _cover(report: ScreeningReport, s: dict) -> list:
    a, meta, sc = report.assessment, report.meta, report.scoring
    story: list = [Spacer(1, 0.85 * inch), Paragraph("INVESTOR SCREENING REVIEW", s["eyebrow"]), Spacer(1, 8)]
    story.append(Paragraph(_headline_markup(meta.company_name, a.value_proposition_headline, a.headline_highlights), s["title"]))
    story.append(Spacer(1, 10))
    source = review.source_description(report) + (f" ({a.source_date})" if a.source_date else "")
    story.append(Paragraph(
        f"Screened against TEN Capital Network criteria from the {_e(source)}. "
        f"Prepared by TEN Capital Network, {_e(review.long_date(meta.analysis_date))}.", s["subtitle"]))
    if report.sensitivity.confidential:
        story.append(Spacer(1, 4))
        story.append(Paragraph(CONFIDENTIAL_LABEL.upper(), s["confidential"]))
    story.append(Spacer(1, 22))

    score_style = ParagraphStyle("score", parent=s["tile_value"], textColor=C["coral"])
    fit = sc.effective_rating
    tiles = Table(
        [[Paragraph("Investability Score", s["tile_label"]), Paragraph("TEN Fit Rating", s["tile_label"]), Paragraph("Investor Readiness", s["tile_label"])],
         [Paragraph(_e(review.score_display(report)), score_style),
          Paragraph(_e(fit), ParagraphStyle("fit", parent=s["tile_value"], fontSize=18 if len(fit) > 14 else 24)),
          Paragraph(f"{report.readiness.score} / 10", s["tile_value"])]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    tiles.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, C["rule"]),
        ("LINEAFTER", (0, 0), (1, -1), 0.6, C["rule"]),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FFFFFF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 16),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 18),
        ("TOPPADDING", (0, 1), (-1, 1), 14),
    ]))
    story += [tiles, Spacer(1, 18)]

    status, reason = review.gate_line(report)
    rows = [
        ["Item", "Finding"],
        ["Track", review.track_line(report)],
        ["Stage gate", Paragraph(f"<b>{_e(status)}.</b> {_e(reason)}", s["cell"])],
        ["Funding raised to date", review.funding_line(report)],
        ["Current raise", review.current_raise_line(report)],
        ["Exclusion categories", review.exclusion_line(report)],
        ["Recommended next step", review.next_step(report)],
    ]
    story.append(_table(rows, [1.85 * inch, CONTENT_W - 1.85 * inch], s))
    note = review.source_note(report)
    if note:
        story += [Spacer(1, 10), Paragraph(_e(note), s["note"])]
    # The cover is always exactly one page: shrink proportionally only if a long name or headline overflows.
    return [KeepInFrame(CONTENT_W, COVER_H, story, mode="shrink"), PageBreak()]


def _body(report: ScreeningReport, s: dict) -> list:
    a, sc, led = report.assessment, report.scoring, report.ledger
    story: list = []
    track = report.gate.track

    # 1 ---------------------------------------------------------------------
    letter = f"Track {track}" if track != "undetermined" else "Track Undetermined"
    _section_head(story, 1, "Track Classification & Stage Gate",
                  f"{letter} – {report.gate.status.value}. {led.track.rationale.rstrip('.')}. {TRACK_REQUIREMENT[track]}", s)
    if a.stage_gate_evidence:
        rows = [["Evidence type", f"What the {review.source_short_name(report)} states", "Counts toward stage gate?"]]
        for row in a.stage_gate_evidence:
            rows.append([row.evidence_type, Paragraph(f"{_e(row.deck_statement)}{_ref(report, row.evidence_ids)}", s["cell"]), row.counts_toward_gate])
        story.append(_table(rows, [1.45 * inch, 2.6 * inch, CONTENT_W - 4.05 * inch], s, bold_first=False))
        story.append(Spacer(1, 8))
    verdict = a.gate_verdict_paragraph or " ".join(report.gate.reasons)
    story.append(Paragraph(f"Verdict: {_e(verdict)}", s["body"]))

    # 2 ---------------------------------------------------------------------
    _section_head(story, 2, "Capital History & Current Raise",
                  a.capital_lead or a.capital_history.lead or _first_sentence(a.capital_history.summary), s)
    rows = [["Item", "Disclosed?", "Detail"]] + [list(r) for r in review.capital_disclosure_rows(report)]
    story.append(_table(rows, [2.05 * inch, 0.95 * inch, CONTENT_W - 3.0 * inch], s, bold_first=False))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Capital efficiency:</b> {_e(a.capital_efficiency)}", s["body"]))
    flags = [f"{f.flag} – {f.concern}" for f in report.instrument_flags] + [f"{c.instrument} – {c.concern}" for c in a.instrument_concerns]
    story.append(Paragraph("<b>Structure flags:</b> " + _e(" ".join(flags) if flags else
                           "None identified from the materials. Confirm whether any prior financing used uncapped notes, "
                           "uncapped or pre-money SAFEs, or KISS agreements."), s["body"]))
    for flag in a.conditional_flags:
        story.append(Paragraph(f"<b>{_e(flag.label.rstrip(':'))}:</b> {_e(flag.text)}{_ref(report, flag.evidence_ids)}", s["body"]))
    if report.capital.notes:
        story.append(Paragraph("<b>Reconciliation:</b> " + _e(" ".join(report.capital.notes)), s["body"]))
    if a.current_raise.summary:
        story.append(Paragraph(f"<b>Current raise:</b> {_e(a.current_raise.summary)}", s["body"]))

    # 3-6 -------------------------------------------------------------------
    for number, title, sec in ((3, "Company Maturity & Team", a.maturity_and_team),
                               (4, "Differentiation & Defensibility", a.differentiation),
                               (5, "Growth Potential", a.market_and_growth),
                               (6, "Financial Review", a.financial_review)):
        _section_head(story, number, title, sec.lead or _first_sentence(sec.summary), s)
        _labeled_section(story, report, sec, s)
        if number == 3 and not any(p.label.lower().startswith("stage fit") for p in sec.points):
            story.append(Paragraph(f"<b>Valuation benchmarking:</b> {_e(a.valuation_benchmarking)}", s["bullet"], bulletText="•"))
        if number == 6:
            story.append(Paragraph(f"<b>Runway (calculated):</b> {_e(report.runway.basis)}", s["bullet"], bulletText="•"))

    # 7 ---------------------------------------------------------------------
    _section_head(story, 7, "Exit Potential", a.exit_potential.lead or _first_sentence(a.exit_potential.summary), s)
    if a.exit_comparables:
        rows = [["Comparable", "Year", "Terms", "Relevance"]]
        for comp in a.exit_comparables:
            url = review.external_url(report, comp.source_id)
            name = f"<link href='{escape(url, {chr(39): '&#39;'})}' color='#1A6FC2'>{_e(comp.comparable)}</link>" if url else _e(comp.comparable)
            rows.append([Paragraph(name, s["cell"]), comp.year or "–", comp.terms, comp.relevance])
        story.append(_table(rows, [1.6 * inch, 0.5 * inch, 2.1 * inch, CONTENT_W - 4.2 * inch], s, bold_first=False))
        story.append(Spacer(1, 8))
    else:
        story.append(Paragraph(
            "Comparable exits were not researched (external research disabled); listed as a diligence item."
            if not report.meta.external_research_enabled else "No sourced comparable transactions were found.", s["note"]))
        story.append(Spacer(1, 4))
    _labeled_section(story, report, a.exit_potential, s)
    if a.ten_x_scenario and not any("10x" in p.label for p in a.exit_potential.points):
        t = a.ten_x_scenario
        story.append(Paragraph(
            f"<b>10x test (assumptions):</b> entry {_e(t.entry_valuation)}; ownership {_e(t.ownership_at_entry)}; dilution "
            f"{_e(t.dilution_assumption)}; required exit equity value {_e(t.exit_equity_value_required)}. {_e(t.plausibility)}",
            s["bullet"], bulletText="•"))

    # 8 ---------------------------------------------------------------------
    _section_head(story, 8, "Exclusion Check", "", s)
    verdict = a.exclusion_verdict or ("No exclusion triggered." if review.exclusion_line(report) == "None triggered" else review.exclusion_line(report))
    story.append(Paragraph(f"<b>{_e(verdict)}</b> {_e(a.exclusion_explanation)} {_e(a.investor_matching_note)}", s["body"]))

    # 9 ---------------------------------------------------------------------
    _section_head(story, 9, "Pitch Document Review",
                  f"{a.deck_lead or _first_sentence(a.deck_narrative_assessment)} {review.citation_convention(report)}", s)
    if a.deck_narrative_assessment and a.deck_narrative_assessment != a.deck_lead:
        story.append(Paragraph(_e(a.deck_narrative_assessment), s["body"]))
    story.append(Paragraph(f"{len(a.deck_strengths)} PROS OF THE PITCH DOCUMENT", s["label"]))
    for i, d in enumerate(a.deck_strengths, start=1):
        refs = review.page_refs(report, d.pages)
        story.append(Paragraph(f"<b>{_e(d.headline.rstrip('.'))}{' (' + _e(refs) + ')' if refs else ''}.</b> {_e(d.detail)}", s["bullet"], bulletText=f"{i}."))
    if len(a.deck_strengths) < 5:
        story.append(Paragraph(f"Only {len(a.deck_strengths)} supported by the materials.", s["note"]))
    story.append(Paragraph(f"{len(a.deck_critiques)} CRITIQUES OF THE PITCH DOCUMENT", s["label"]))
    for i, d in enumerate(a.deck_critiques, start=1):
        refs = review.page_refs(report, d.pages)
        story.append(Paragraph(f"<b>{_e(d.issue.rstrip('.'))}{' (' + _e(refs) + ')' if refs else ''}.</b> <i>Fix:</i> {_e(d.fix)}", s["bullet"], bulletText=f"{i}."))
    if a.missing_slides_or_data:
        story.append(Paragraph("MISSING DATA", s["label"]))
        story += [Paragraph(_e(m), s["bullet"], bulletText="•") for m in a.missing_slides_or_data]
    if a.revised_slide_order:
        story.append(Paragraph("SUGGESTED STRUCTURE FOR A FULL DECK", s["label"]))
        story += [Paragraph(_e(m), s["bullet"], bulletText=f"{i}.") for i, m in enumerate(a.revised_slide_order, start=1)]
    if a.diligence_requests:
        story.append(Paragraph("DILIGENCE ITEMS INVESTORS WILL REQUEST", s["label"]))
        story += [Paragraph(_e(m), s["bullet"], bulletText="•") for m in a.diligence_requests]

    # 10 --------------------------------------------------------------------
    _section_head(story, 10, "Investability Score", review.score_lead(report), s)
    rows = [["Category", "Weight", "Score", "Weighted", "Justification"]]
    for cat in sc.categories:
        rows.append([cat.name, f"{cat.weight}%", str(cat.score) if cat.score is not None else "N/A",
                     f"{cat.points:.1f}" if cat.points is not None else "–",
                     (cat.short_justification or cat.justification) + (f" [{cat.adjustment_note}]" if cat.adjustment_note else "")])
    total = f"{sc.total:.1f}" if sc.complete else f"{sc.supported_points:.1f}*"
    band = sc.underlying_band or "Band withheld"
    rows.append(["Total", "100%", "", total, band if sc.complete else f"{band} (*provisional; range {sc.possible_min:.1f}–{sc.possible_max:.1f})"])
    story.append(_table(rows, [1.8 * inch, 0.68 * inch, 0.55 * inch, 0.8 * inch, CONTENT_W - 3.83 * inch], s, bold_first=False, total_row=True))

    # 11 --------------------------------------------------------------------
    _section_head(story, 11, "Final Investor Verdict", "", s)
    callout = Table([[Paragraph(f"<b>{_e(a.verdict_headline)}</b> {_e(a.investor_verdict)}" if a.verdict_headline else _e(a.investor_verdict), s["callout"])]],
                    colWidths=[CONTENT_W])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C["callout"]),
        ("LINEBEFORE", (0, 0), (0, -1), 3, C["coral"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story += [callout, Spacer(1, 12)]
    score_text = f"{sc.total:.1f} / 100 – {sc.effective_rating}" if sc.complete else f"{sc.status_label} – {sc.effective_rating}"
    if sc.override_applied and sc.underlying_band and sc.underlying_band != sc.effective_rating:
        score_text += f" (underlying {sc.underlying_band})"
    rows = [["Item", "Result"],
            ["Track and stage gate", f"{letter} – {report.gate.status.value}"],
            ["Funding raised to date", review.funding_line(report)],
            ["Investability Score", score_text],
            ["Investor Readiness Score", f"{report.readiness.score} / 10" + (f" – {a.readiness_justification}" if a.readiness_justification else "")]]
    story.append(_table(rows, [1.85 * inch, CONTENT_W - 1.85 * inch], s))

    for title, items in ((f"TOP {len(a.company_strengths)} COMPANY STRENGTHS", a.company_strengths),
                         (f"TOP {len(a.company_concerns)} COMPANY CONCERNS", a.company_concerns)):
        story.append(Paragraph(title, s["label"]))
        if not items:
            story.append(Paragraph("None supported by the materials.", s["body"]))
        for i, item in enumerate(items, start=1):
            story.append(Paragraph(_e(item.headline.rstrip(".")) + "." + _ref(report, item.evidence_ids), s["bullet"], bulletText=f"{i}."))
        if 0 < len(items) < 5:
            story.append(Paragraph(f"Only {len(items)} supported by the materials.", s["note"]))
    story.append(Paragraph("KEY ACTIONS BEFORE FUNDRAISING", s["label"]))
    story += [Paragraph(_e(x), s["bullet"], bulletText="•") for x in a.fundraising_actions]

    story.append(Paragraph("SOURCES", s["label"]))
    for title, url in review.sources(report):
        text = f"<link href='{escape(url, {chr(39): '&#39;'})}' color='#1A6FC2'>{_e(title)}</link>" if url else _e(title)
        story.append(Paragraph(text, s["source"], bulletText="•"))
    story += [Spacer(1, 10), KeepTogether([Paragraph(_e(DISCLAIMER), s["note"]), Spacer(1, 4), Paragraph(_e(DISCLAIMER_TEN), s["note"])])]
    return story


def render_screening_review(report: ScreeningReport) -> bytes:
    s = _styles()
    meta = report.meta
    logo = footer_logo()
    header_text = f"{clip(meta.company_name, 9)} | Investor Screening Review | {review.long_date(meta.analysis_date)}"
    doc_title = f"Investor Screening Review — {clip(meta.company_name, 6)}"

    def background(canvas) -> None:  # noqa: ANN001
        canvas.setFillColor(C["page"])
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    def first_page(canvas, doc) -> None:  # noqa: ANN001, ARG001
        canvas.saveState()
        background(canvas)
        if logo:
            canvas.drawImage(logo, MARGIN_X + 6, PAGE_H - 1.25 * inch, width=1.95 * inch, height=0.72 * inch, mask="auto", preserveAspectRatio=True, anchor="w")
        draw_footer(canvas, doc_title, canvas.getPageNumber(), meta.analysis_date, PAGE_W, y=26)
        canvas.restoreState()

    def later_pages(canvas, doc) -> None:  # noqa: ANN001, ARG001
        canvas.saveState()
        background(canvas)
        top = PAGE_H - 0.55 * inch
        if logo:
            canvas.drawImage(logo, MARGIN_X + 6, top - 18, width=0.95 * inch, height=0.35 * inch, mask="auto", preserveAspectRatio=True, anchor="w")
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(C["muted"])
        canvas.drawRightString(PAGE_W - MARGIN_X - 6, top - 6, header_text)
        if report.sensitivity.confidential:
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.setFillColor(C["coral"])
            canvas.drawRightString(PAGE_W - MARGIN_X - 6, top - 17, CONFIDENTIAL_LABEL)
        canvas.setStrokeColor(C["rule"])
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_X + 6, top - 26, PAGE_W - MARGIN_X - 6, top - 26)
        draw_footer(canvas, doc_title, canvas.getPageNumber(), meta.analysis_date, PAGE_W, y=26)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        title=f"Investor Screening Review - {meta.company_name}", author="TEN Capital Network",
        subject="Investor screening review", creator="TEN Screener",
    )
    doc.build(_cover(report, s) + _body(report, s), onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()
