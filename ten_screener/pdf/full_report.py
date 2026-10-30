"""Multi-page full analysis report: every finding, the evidence ledger and the methodology."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ten_screener import REPORT_TITLE
from ten_screener.pdf.one_page import CONFIDENTIAL_LABEL, DISCLAIMER
from ten_screener.pdf.theme import PALETTE, draw_footer, fonts
from ten_screener.rules import fmt_money
from ten_screener.schemas import READINESS_RUBRIC, ScreeningReport, SectionAnalysis
from ten_screener.scoring import SCORING_ANCHORS
from ten_screener.summary import capital_lines, snapshot_title, track_snapshot

PAGE_W, PAGE_H = LETTER
MARGIN = 0.7 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


def _styles() -> dict[str, ParagraphStyle]:
    f = fonts()
    return {
        "title": ParagraphStyle("title", fontName=f.bold, fontSize=18, leading=22, textColor=PALETTE["navy"]),
        "h1": ParagraphStyle("h1", fontName=f.bold, fontSize=13, leading=17, textColor=PALETTE["navy"], spaceBefore=10, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName=f.semibold, fontSize=10.5, leading=14, textColor=PALETTE["teal"], spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("body", fontName=f.regular, fontSize=10, leading=13.5, textColor=PALETTE["ink"], spaceAfter=3),
        "bullet": ParagraphStyle("bullet", fontName=f.regular, fontSize=10, leading=13.5, textColor=PALETTE["ink"], leftIndent=12, bulletIndent=2, spaceAfter=2),
        "small": ParagraphStyle("small", fontName=f.regular, fontSize=9, leading=11.5, textColor=PALETTE["muted"], spaceAfter=5),
        "cell": ParagraphStyle("cell", fontName=f.regular, fontSize=9, leading=11, textColor=PALETTE["ink"]),
        "cell_h": ParagraphStyle("cell_h", fontName=f.semibold, fontSize=9, leading=11, textColor=PALETTE["white"]),
    }


def _table(rows: list[list], widths: list[float], s: dict) -> Table:
    data = [[Paragraph(escape(str(c)), s["cell_h"] if i == 0 else s["cell"]) for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALETTE["navy"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALETTE["white"], PALETTE["panel"]]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, PALETTE["rule"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def render_full_report(report: ScreeningReport) -> bytes:
    s = _styles()
    r = report
    a = r.assessment
    story: list = []

    def p(text: str, style: str = "body") -> None:
        story.append(Paragraph(escape(text), s[style]))

    def bullets(items: list[str]) -> None:
        for item in items:
            story.append(Paragraph(escape(item), s["bullet"], bulletText="•"))

    def section(title: str, sec: SectionAnalysis) -> None:
        story.append(Paragraph(escape(title), s["h2"]))
        p(sec.summary)
        for f in sec.findings:
            ref = r.cite(f.evidence_ids)
            story.append(Paragraph(f"<b>{escape(f.headline)}</b> {escape(f.detail)}" + (f" <font color='#56657A'>[{escape(ref)}]</font>" if ref else ""), s["bullet"], bulletText="•"))

    story.append(Paragraph(escape(REPORT_TITLE), s["small"]))
    story.append(Paragraph(escape(r.meta.company_name), s["title"]))
    p(f"Website: {r.meta.website or 'Not disclosed'}  ·  Source: {r.meta.source_filename}  ·  Analyzed: {r.meta.analysis_date}  ·  "
      f"Model: {r.meta.model}  ·  App v{r.meta.app_version}", "small")
    if r.sensitivity.confidential:
        p(f"{CONFIDENTIAL_LABEL} ({', '.join(r.sensitivity.reasons)})", "h2")
    p(a.business_description)

    story.append(Paragraph("1. Verdict summary", s["h1"]))
    sc = r.scoring
    rows = [["Item", "Result"],
            ["Track", r.gate.track_label + f" - {r.ledger.track.rationale}"],
            ["Stage gate", f"{r.gate.status.value}: " + " ".join(r.gate.reasons)],
            ["Effective TEN fit rating", sc.effective_rating],
            ["Underlying score", sc.status_label + (f" ({sc.underlying_band})" if sc.underlying_band else " - band withheld until all categories are assessable")],
            ["Eligibility override", sc.override_applied or "None"],
            ["Capital raised to date", capital_lines(r)[0][1]],
            ["Investor Readiness", f"{r.readiness.score} / 10 - {a.readiness_justification}"]]
    story.append(_table(rows, [1.6 * inch, CONTENT_W - 1.6 * inch], s))
    story.append(Paragraph("Investor verdict", s["h2"]))
    p(a.investor_verdict)

    story.append(Paragraph("2. Scorecard", s["h1"]))
    p(f"Weighted total = sum(score / 10 x weight). Bands: 80-100 Strong Fit; 65-<80 Moderate Fit; 50-<65 Weak Fit; <50 Likely Pass "
      f"(applied before rounding). Anchors: {SCORING_ANCHORS} Not-assessable categories keep their weight unassigned; "
      f"supported points {sc.supported_points:.2f} from {sc.assessed_weight}% assessed weight; possible total {sc.possible_min:.1f}-{sc.possible_max:.1f}.", "small")
    rows = [["Category", "Weight", "Score", "Points", "Justification"]]
    for c in sc.categories:
        just = c.justification + (f" [{c.adjustment_note}]" if c.adjustment_note else "")
        ref = r.cite(c.evidence_ids)
        rows.append([c.name, f"{c.weight}%", c.score if c.score is not None else "Not assessable",
                     f"{c.points:.1f}" if c.points is not None else "-", just + (f" ({ref})" if ref else "")])
    story.append(_table(rows, [1.45 * inch, 0.55 * inch, 0.75 * inch, 0.55 * inch, CONTENT_W - 3.3 * inch], s))

    story.append(Paragraph("3. Company strengths and concerns", s["h1"]))
    for title, items in (("Company strengths", a.company_strengths), ("Company concerns", a.company_concerns)):
        story.append(Paragraph(title, s["h2"]))
        if not items:
            p("None supported by the evidence.")
        for item in items:
            ref = r.cite(item.evidence_ids)
            story.append(Paragraph(f"<b>{escape(item.headline)}</b> {escape(item.detail)}" + (f" <font color='#56657A'>[{escape(ref)}]</font>" if ref else ""), s["bullet"], bulletText="•"))
        if 0 < len(items) < 5:
            p(f"Only {len(items)} supported; not padded to five.", "small")
    story.append(Paragraph("Prioritized actions before fundraising", s["h2"]))
    for i, action in enumerate(a.fundraising_actions, start=1):
        story.append(Paragraph(escape(action), s["bullet"], bulletText=f"{i}."))

    story.append(Paragraph("4. Track, stage gate and snapshot", s["h1"]))
    story.append(Paragraph(snapshot_title(r), s["h2"]))
    bullets(track_snapshot(r))
    story.append(Paragraph("Exclusion check", s["h2"]))
    ex = r.ledger.exclusion
    p(f"{ex.category.replace('_', ' ')} - {ex.status.replace('_', ' ')}. {a.exclusion_explanation}")

    story.append(Paragraph("5. Capital history and current raise", s["h1"]))
    cap = r.capital
    rows = [["Funding event", "Amount", "Date", "Instrument", "Investors", "Source"]]
    for e in cap.counted_events:
        rows.append([e.label, fmt_money(e.amount, e.currency), e.date or "Not disclosed", e.instrument.replace("_", " "),
                     ", ".join(e.investors) or "Not disclosed", r.cite(e.evidence_ids)])
    for e in cap.cumulative_statements:
        rows.append([e.label + " (cumulative statement)", fmt_money(e.amount, e.currency), e.date or "-", "cumulative", "-", r.cite(e.evidence_ids)])
    if len(rows) > 1:
        story.append(_table(rows, [1.5 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch, 1.3 * inch, CONTENT_W - 5.3 * inch], s))
    else:
        p("No prior funding is disclosed.")
    bullets([f"{k}: {fmt_money(v, cap.currency)}" for k, v in cap.by_category.items()] + cap.notes + [f"Merged duplicate: {d}" for d in cap.duplicates_removed])
    bullets([f"{k}: {v}" for k, v in capital_lines(r)[1:]] + [f"Runway: {r.runway.basis}"])
    for flag in r.instrument_flags:
        story.append(Paragraph(f"<b>{escape(flag.flag)}:</b> {escape(flag.concern)}", s["bullet"], bulletText="!"))
    section("Capital history", a.capital_history)
    p("Capital efficiency: " + a.capital_efficiency)
    section("Current raise", a.current_raise)
    for c in a.instrument_concerns:
        story.append(Paragraph(f"<b>{escape(c.instrument)}:</b> {escape(c.concern)}", s["bullet"], bulletText="•"))

    story.append(Paragraph("6. Detailed analysis", s["h1"]))
    section("Company maturity and team", a.maturity_and_team)
    p("Valuation benchmarking: " + a.valuation_benchmarking)
    section("Differentiation and defensibility", a.differentiation)
    section("Market and growth", a.market_and_growth)
    section("Financial review", a.financial_review)
    p(f"Raise funds a value-inflection milestone: {a.raise_funds_milestone}. {a.raise_funds_milestone_explanation}")
    section("Exit potential", a.exit_potential)
    if a.ten_x_scenario:
        t = a.ten_x_scenario
        story.append(Paragraph("10x scenario (all inputs are assumptions)", s["h2"]))
        bullets([f"Entry valuation (assumption): {t.entry_valuation}", f"Ownership at entry (assumption): {t.ownership_at_entry}",
                 f"Dilution to exit (assumption): {t.dilution_assumption}", f"Exit equity value required: {t.exit_equity_value_required}",
                 f"Plausibility: {t.plausibility}", t.assumptions_note])

    story.append(Paragraph("7. Pitch deck review", s["h1"]))
    p(a.deck_narrative_assessment)
    label = lambda pages: ", ".join(r.page_labels.get(n, str(n)) for n in pages)  # noqa: E731
    story.append(Paragraph(f"Deck strengths ({len(a.deck_strengths)})", s["h2"]))
    for d in a.deck_strengths:
        story.append(Paragraph(f"<b>{escape(d.headline)}</b> {escape(d.detail)} <font color='#56657A'>[{escape(label(d.pages))}]</font>", s["bullet"], bulletText="•"))
    story.append(Paragraph(f"Deck critiques and fixes ({len(a.deck_critiques)})", s["h2"]))
    for d in a.deck_critiques:
        story.append(Paragraph(f"<b>{escape(d.issue)}</b> Fix: {escape(d.fix)} <font color='#56657A'>[{escape(label(d.pages))}]</font>", s["bullet"], bulletText="•"))
    if a.missing_slides_or_data:
        story.append(Paragraph("Missing slides or data", s["h2"]))
        bullets(a.missing_slides_or_data)
    if a.revised_slide_order:
        story.append(Paragraph("Suggested slide order", s["h2"]))
        for i, item in enumerate(a.revised_slide_order, start=1):
            story.append(Paragraph(escape(item), s["bullet"], bulletText=f"{i}."))
    story.append(Paragraph("Prioritized diligence requests", s["h2"]))
    for i, item in enumerate(a.diligence_requests, start=1):
        story.append(Paragraph(escape(item), s["bullet"], bulletText=f"{i}."))

    story.append(Paragraph("8. Investor readiness", s["h1"]))
    p(r.readiness.rubric_note, "small")
    rows = [["Rubric item", "Met", "Note"]] + [[READINESS_RUBRIC[i.key], "Yes" if i.met else "No", i.note] for i in r.readiness.items]
    story.append(_table(rows, [2.3 * inch, 0.5 * inch, CONTENT_W - 2.8 * inch], s))

    if r.external_findings:
        story.append(Paragraph("9. External research (separate from deck claims)", s["h1"]))
        rows = [["Id", "Finding", "Source", "Retrieved"]] + [[f.id, f.claim, f"{f.source_title} - {f.url}", f.retrieved_on] for f in r.external_findings]
        story.append(_table(rows, [0.4 * inch, 3.1 * inch, CONTENT_W - 4.4 * inch, 0.9 * inch], s))

    if r.user_context:
        story.append(Paragraph("Analyst-supplied context (not deck evidence)", s["h1"]))
        p(r.user_context)

    story.append(PageBreak())
    story.append(Paragraph("Evidence ledger", s["h1"]))
    p("Citations were machine-checked against the extracted text. 'verified' = excerpt found on the cited page; 'approximate' = "
      "near match; 'relocated' = found on a different page and corrected; 'not found' = could not be located (claim downgraded); "
      "'visual' = read from a rendered image, not text-verifiable. Page references use "
      + ("PDF page numbers, which may differ from printed slide numbers." if r.meta.page_label_kind == "PDF page" else "slide order in the file."), "small")
    rows = [["Id", "Claim / value", "Status", "Source", "Excerpt / notes"]]
    for e in r.ledger.evidence:
        srcs = "; ".join(f"{r.page_labels.get(x.page, x.page)}{' notes' if x.kind == 'speaker_notes' else ''} ({x.verification.replace('_', ' ')})" for x in e.sources) or "-"
        notes = " | ".join(filter(None, [f'"{x.excerpt}"' for x in e.sources if x.excerpt][:2] + [e.calculation, e.uncertainty, e.citation_note]))
        claim = e.claim + (f" = {e.value}" if e.value else "") + (f" [{e.nature.replace('_', ' ')}]" if e.nature not in ("not_applicable", "unclear") else "")
        rows.append([e.id, claim, e.status.value, srcs, notes or "-"])
    story.append(_table(rows, [0.4 * inch, 2.0 * inch, 0.95 * inch, 1.2 * inch, CONTENT_W - 4.55 * inch], s))

    story.append(Paragraph("Limitations and extraction notes", s["h1"]))
    bullets(r.limitations or ["None recorded."])
    if r.ledger.contradictions:
        story.append(Paragraph("Contradictions and anomalies", s["h2"]))
        bullets(r.ledger.contradictions)
    story.append(Spacer(1, 6))
    story.append(KeepTogether([Paragraph(escape(DISCLAIMER), s["small"])]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                            title=f"Full Investor Screening - {r.meta.company_name}", author="TEN Capital Network")
    doc_title = f"Full Investor Screening — {r.meta.company_name[:40]}"

    def on_page(canvas, d):  # noqa: ANN001, ARG001
        if r.sensitivity.confidential:
            canvas.saveState()
            canvas.setFont(fonts().semibold, 7.5)
            canvas.setFillColor(PALETTE["teal"])
            canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.45 * inch, CONFIDENTIAL_LABEL)
            canvas.restoreState()
        draw_footer(canvas, doc_title, canvas.getPageNumber(), r.meta.analysis_date, PAGE_W, y=24)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
