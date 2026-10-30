"""Exactly-one-page US Letter screening summary.

Fitting strategy, in order: at 10 pt body, step through progressively tighter
wording levels; only when the tightest wording still overflows, drop to 9.5 pt,
then 9 pt. Body text never goes below 9 pt. Each candidate is actually built and
measured (page count and extracted word count) - nothing is estimated.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ten_screener.errors import RenderError
from ten_screener.pdf.theme import FIT_COLOURS, PALETTE, draw_footer, fonts, image_reader
from ten_screener.schemas import ScreeningReport
from ten_screener.summary import SHORT_CATEGORY_NAMES, capital_lines, clip, key_evidence, snapshot_title, track_snapshot

DISCLAIMER = (
    "Initial screening based on supplied materials; not independent verification. For informational purposes only. "
    "Does not constitute an offer to sell securities."
)
CONFIDENTIAL_LABEL = "Confidential — Internal Screening"
PUBLIC_LABEL = "Public Summary — sensitive deal details removed"

PAGE_W, PAGE_H = LETTER
MARGIN_X = 0.55 * inch
HEADER_H = 46
TOP = HEADER_H + 14
BOTTOM = 62
# SimpleDocTemplate's frame keeps 6 pt padding on each side; flowables must fit inside it.
CONTENT_W = PAGE_W - 2 * MARGIN_X - 12
MAX_WORDS = 720  # "roughly 550-700 words"; a hard ceiling with a little tolerance

BODY_SIZES = (10.0, 9.5, 9.0)


@dataclass(frozen=True)
class Level:
    description: int
    snapshot_lines: int
    snapshot_words: int
    justification: int
    point: int
    action: int
    verdict: int
    evidence: int


LEVELS = (
    Level(description=45, snapshot_lines=5, snapshot_words=16, justification=12, point=15, action=20, verdict=70, evidence=6),
    Level(description=38, snapshot_lines=4, snapshot_words=14, justification=10, point=13, action=17, verdict=55, evidence=5),
    Level(description=30, snapshot_lines=4, snapshot_words=12, justification=8, point=11, action=14, verdict=45, evidence=4),
    Level(description=24, snapshot_lines=3, snapshot_words=10, justification=6, point=9, action=12, verdict=34, evidence=3),
    Level(description=18, snapshot_lines=3, snapshot_words=8, justification=5, point=8, action=10, verdict=26, evidence=2),
)


@dataclass
class OnePageResult:
    pdf: bytes
    pages: int
    words: int
    body_size: float
    level: int


def _styles(body: float) -> dict[str, ParagraphStyle]:
    f = fonts()
    lead = body * 1.24
    return {
        "name": ParagraphStyle("name", fontName=f.bold, fontSize=body + 6, leading=body + 8.5, textColor=PALETTE["navy"]),
        "meta": ParagraphStyle("meta", fontName=f.regular, fontSize=max(9.0, body - 1), leading=max(9.0, body - 1) * 1.25, textColor=PALETTE["muted"]),
        "body": ParagraphStyle("body", fontName=f.regular, fontSize=body, leading=lead, textColor=PALETTE["ink"], alignment=TA_LEFT),
        "body_b": ParagraphStyle("body_b", fontName=f.semibold, fontSize=body, leading=lead, textColor=PALETTE["ink"]),
        "h": ParagraphStyle("h", fontName=f.bold, fontSize=body, leading=body * 1.3, textColor=PALETTE["teal"], spaceAfter=1),
        "label": ParagraphStyle("label", fontName=f.semibold, fontSize=7.5, leading=9, textColor=PALETTE["teal"]),
        "value": ParagraphStyle("value", fontName=f.bold, fontSize=body, leading=body * 1.2, textColor=PALETTE["navy"]),
        "small": ParagraphStyle("small", fontName=f.regular, fontSize=9.0, leading=10.6, textColor=PALETTE["muted"]),
        "cell": ParagraphStyle("cell", fontName=f.regular, fontSize=9.0, leading=10.8, textColor=PALETTE["ink"]),
        "cell_b": ParagraphStyle("cell_b", fontName=f.semibold, fontSize=9.0, leading=10.8, textColor=PALETTE["ink"]),
        "cell_h": ParagraphStyle("cell_h", fontName=f.semibold, fontSize=9.0, leading=10.8, textColor=PALETTE["white"]),
        "verdict": ParagraphStyle("verdict", fontName=f.regular, fontSize=body, leading=lead, textColor=PALETTE["navy"]),
        "override": ParagraphStyle("override", fontName=f.italic, fontSize=max(9.0, body - 0.5), leading=max(9.0, body - 0.5) * 1.25, textColor=PALETTE["navy_soft"]),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


def _story(report: ScreeningReport, level: Level, s: dict[str, ParagraphStyle], public: bool) -> list:
    meta = report.meta
    a = report.assessment
    sc = report.scoring
    story: list = []

    story.append(_p(clip(meta.company_name, 16), s["name"]))
    meta_bits = [
        f"Website: {meta.website or 'Not disclosed'}",
        f"Source: {clip(meta.source_filename, 8)}",
        f"Analyzed: {meta.analysis_date}",
        f"{meta.page_count} {'PDF pages' if meta.page_label_kind == 'PDF page' else 'slides'}",
    ]
    story.append(_p("  ·  ".join(meta_bits), s["meta"]))
    story.append(Spacer(1, 3))
    story.append(_p(clip(a.business_description, level.description), s["body"]))
    story.append(Spacer(1, 5))

    # Status strip -------------------------------------------------------
    fit_colour = FIT_COLOURS.get(sc.effective_rating, PALETTE["navy"])
    fit_style = ParagraphStyle("fit", parent=s["value"], textColor=fit_colour)
    underlying = f"Underlying: {sc.underlying_band}" if sc.underlying_band else "Underlying band withheld"
    if sc.complete:
        score_main, score_sub = f"{sc.total:.1f} / 100", "All categories assessed"
    else:
        score_main = "Provisional"
        score_sub = f"{sc.supported_points:.1f} pts · {sc.assessed_weight}% assessed · range {sc.possible_min:.0f}–{sc.possible_max:.0f}"
    cells = [
        ("TRACK", report.gate.track_label.split(" - ")[0], report.gate.track_label.split(" - ")[1] if " - " in report.gate.track_label else None),
        ("STAGE GATE", report.gate.label, None),
        ("EFFECTIVE FIT", sc.effective_rating, underlying),
        ("INVESTABILITY SCORE", score_main, score_sub),
        ("INVESTOR READINESS", f"{report.readiness.score} / 10", "Preparation, not investability"),
    ]
    row = []
    for label, value, sub in cells:
        parts = [_p(label, s["label"]), Paragraph(escape(value), fit_style if label == "EFFECTIVE FIT" else s["value"])]
        if sub:
            parts.append(_p(sub, ParagraphStyle("sub", parent=s["small"], fontSize=7.5, leading=9)))
        row.append(parts)
    strip = Table([row], colWidths=[0.17 * CONTENT_W, 0.19 * CONTENT_W, 0.22 * CONTENT_W, 0.24 * CONTENT_W, 0.18 * CONTENT_W])
    strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALETTE["teal_light"]),
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, PALETTE["teal"]),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, PALETTE["teal_mid"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(strip)
    if sc.override_applied:
        story.append(Spacer(1, 3))
        story.append(_p("Eligibility override: " + clip(sc.override_applied, 30), s["override"]))
    story.append(Spacer(1, 6))

    # Snapshot + capital (left) | scorecard (right) -----------------------
    left_w, gap = 0.40 * CONTENT_W, 10
    right_w = CONTENT_W - left_w - gap
    left: list = [_p(snapshot_title(report).upper(), s["h"])]
    for line in track_snapshot(report)[: level.snapshot_lines]:
        left.append(_p("• " + clip(line, level.snapshot_words), s["body"]))
    left.append(Spacer(1, 4))
    left.append(_p("CAPITAL & RAISE", s["h"]))
    for key, value in capital_lines(report, public=public):
        left.append(Paragraph(f"<font name='{fonts().semibold}'>{escape(key)}:</font> {escape(clip(value, level.snapshot_words))}", s["body"]))

    rows = [[_p("Category", s["cell_h"]), _p("Wt", s["cell_h"]), _p("Score", s["cell_h"]), _p("Basis", s["cell_h"])]]
    for cat in sc.categories:
        score_txt = str(cat.score) if cat.score is not None else "N/A"
        basis = cat.short_justification if cat.score is not None else "Not assessable: " + (cat.short_justification or "insufficient evidence")
        rows.append([
            _p(SHORT_CATEGORY_NAMES[cat.key], s["cell_b"]),
            _p(f"{cat.weight}%", s["cell"]),
            _p(score_txt, s["cell_b"]),
            _p(clip(basis, level.justification), s["cell"]),
        ])
    card = Table(rows, colWidths=[0.30 * right_w, 0.09 * right_w, 0.10 * right_w, 0.51 * right_w], repeatRows=1)
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALETTE["navy"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALETTE["white"], PALETTE["panel"]]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, PALETTE["rule"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    two_col = Table([[left, "", [_p("SCORECARD (WEIGHTED)", s["h"]), card]]], colWidths=[left_w, gap, right_w])
    two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(two_col)
    story.append(Spacer(1, 6))

    # Strengths | concerns ------------------------------------------------
    half = (CONTENT_W - gap) / 2

    def points(title: str, items: list, empty: str) -> list:
        out = [_p(title, s["h"])]
        if not items:
            out.append(_p(empty, s["body"]))
        for i, item in enumerate(items[:5], start=1):
            out.append(_p(f"{i}. {clip(item.headline, level.point)}", s["body"]))
        if 0 < len(items) < 5:
            out.append(_p(f"Only {len(items)} supported by the evidence.", s["small"]))
        return out

    sc_table = Table(
        [[points("COMPANY STRENGTHS", a.company_strengths, "None supported by the evidence."), "",
          points("COMPANY CONCERNS", a.company_concerns, "None identified with sufficient support.")]],
        colWidths=[half, gap, half],
    )
    sc_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(sc_table)
    story.append(Spacer(1, 5))

    story.append(_p("PRIORITY ACTIONS BEFORE FUNDRAISING", s["h"]))
    actions = a.fundraising_actions[:3] or ["Provide the missing stage-gate evidence identified above."]
    for i, action in enumerate(actions, start=1):
        story.append(_p(f"{i}. {clip(action, level.action)}", s["body"]))
    story.append(Spacer(1, 5))

    verdict = Table(
        [[[_p("INVESTOR VERDICT", s["h"]), _p(clip(a.investor_verdict, level.verdict), s["verdict"])]]],
        colWidths=[CONTENT_W],
    )
    verdict.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALETTE["panel"]),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, PALETTE["navy"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(verdict)
    story.append(Spacer(1, 4))

    refs = key_evidence(report, level.evidence)
    if refs:
        story.append(_p("Key evidence: " + "; ".join(refs), s["small"]))
    review = report.pages_needing_review
    if review:
        labels = ", ".join(report.page_labels.get(p, str(p)) for p in review[:6])
        story.append(_p(f"Extraction review needed: {labels}{'…' if len(review) > 6 else ''}. See full report for limitations.", s["small"]))
    return story


def _decorations(report: ScreeningReport, public: bool, logo_bytes: bytes | None):  # noqa: ANN202
    f = fonts()
    logo = image_reader(logo_bytes)
    label = PUBLIC_LABEL if public else (CONFIDENTIAL_LABEL if report.sensitivity.confidential else None)
    doc_title = f"Investor Screening — {clip(report.meta.company_name, 8)}"

    def on_page(canvas, doc):  # noqa: ANN001, ARG001
        canvas.saveState()
        canvas.setFillColor(PALETTE["navy"])
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(PALETTE["teal"])
        canvas.rect(0, PAGE_H - HEADER_H - 3, PAGE_W, 3, stroke=0, fill=1)
        canvas.setFillColor(PALETTE["white"])
        canvas.setFont(f.bold, 14)
        canvas.drawString(MARGIN_X, PAGE_H - 27, "TEN Capital Network | Investor Screening")
        canvas.setFont(f.regular, 8)
        canvas.setFillColor(PALETTE["teal_mid"])
        canvas.drawString(MARGIN_X, PAGE_H - 39, "Initial screening memo")
        right = PAGE_W - MARGIN_X
        if label:
            canvas.setFont(f.semibold, 8)
            canvas.setFillColor(PALETTE["white"])
            width = canvas.stringWidth(label, f.semibold, 8)
            canvas.drawString(right - width, PAGE_H - 39 if logo else PAGE_H - 27, label)
        if logo:
            iw, ih = logo.getSize()
            h = 20.0
            w = min(110.0, iw * h / max(ih, 1))
            canvas.drawImage(logo, right - w, PAGE_H - 30, width=w, height=h, mask="auto", preserveAspectRatio=True)
        canvas.setFont(f.regular, 7.5)
        canvas.setFillColor(PALETTE["muted"])
        canvas.drawCentredString(PAGE_W / 2, 40, DISCLAIMER)
        canvas.setStrokeColor(PALETTE["rule"])
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, 34, PAGE_W - MARGIN_X, 34)
        draw_footer(canvas, doc_title, canvas.getPageNumber(), report.meta.analysis_date, PAGE_W, y=20)
        canvas.restoreState()

    return on_page


def _build(report: ScreeningReport, body: float, level: Level, public: bool, logo: bytes | None) -> tuple[bytes, int, int]:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP, bottomMargin=BOTTOM,
        title=f"Investor Screening - {report.meta.company_name}", author="TEN Capital Network",
        subject="Initial investor screening summary", creator="TEN Screener",
    )
    page_hook = _decorations(report, public, logo)
    doc.build(_story(report, level, _styles(body), public), onFirstPage=page_hook, onLaterPages=page_hook)
    data = buf.getvalue()
    reader = PdfReader(io.BytesIO(data))
    words = sum(len((page.extract_text() or "").split()) for page in reader.pages)
    return data, len(reader.pages), words


def render_one_page(report: ScreeningReport, *, logo: bytes | None = None, public: bool = False) -> OnePageResult:
    if public:
        from ten_screener.pdf.public import redact

        report = redact(report)
    for body in BODY_SIZES:
        for index, level in enumerate(LEVELS):
            data, pages, words = _build(report, body, level, public, logo)
            if pages == 1 and words <= MAX_WORDS:
                return OnePageResult(pdf=data, pages=pages, words=words, body_size=body, level=index)
    # Last resort: tightest settings, accept any word count as long as it is one page.
    data, pages, words = _build(report, BODY_SIZES[-1], LEVELS[-1], public, logo)
    if pages != 1:
        raise RenderError("The one-page summary could not be fitted on a single page without reducing text below 9 pt.")
    return OnePageResult(pdf=data, pages=pages, words=words, body_size=BODY_SIZES[-1], level=len(LEVELS) - 1)

