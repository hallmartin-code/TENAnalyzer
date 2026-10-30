"""Content for the multi-page Screening Review, derived from a report.

Mirrors templates/investor_screening_review_template.md. Everything factual here is
computed from validated data (capital summary, gate, scoring, facts); the model's
prose fields are used only where the template calls for analyst writing.
"""

from __future__ import annotations

from datetime import date

from ten_screener.rules import fmt_money
from ten_screener.schemas import NOT_DISCLOSED, ScreeningReport
from ten_screener.summary import capital_lines

TRACK_NAMES = {"A": "Non-life-science", "B": "Life science", "undetermined": "Undetermined"}


def long_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso


def is_single_page(report: ScreeningReport) -> bool:
    return report.meta.page_count <= 1


def source_description(report: ScreeningReport) -> str:
    n = report.meta.page_count
    if n <= 1:
        return "single-page company document"
    if report.meta.source_file_type in ("pptx", "ppt"):
        return f"{n}-slide pitch deck"
    return f"{n}-page pitch document (PDF)"


def source_short_name(report: ScreeningReport) -> str:
    return "document" if is_single_page(report) else "deck"


def source_note(report: ScreeningReport) -> str | None:
    notes = []
    if report.meta.page_count <= 2:
        notes.append(
            "Source material is a short company document, not a full pitch deck. Many criteria cannot be assessed "
            "from it; those gaps are stated explicitly rather than assumed."
        )
    if any(i.severity == "error" for i in report.extraction_issues) or report.pages_needing_review:
        notes.append("Some pages had extraction limitations; see the evidence appendix.")
    return " ".join(notes) or None


def citation_convention(report: ScreeningReport) -> str:
    if is_single_page(report):
        return "It is a single page, so feedback cites its sections rather than page numbers."
    if report.meta.page_label_kind == "PDF page":
        return "Feedback cites PDF page numbers, which may differ from printed slide numbers."
    return "Feedback cites slide numbers."


def page_refs(report: ScreeningReport, pages: list[int]) -> str:
    if is_single_page(report) or not pages:
        return ""
    return ", ".join(report.page_labels.get(p, str(p)) for p in pages)


# --- cover summary rows -----------------------------------------------------------
def track_line(report: ScreeningReport) -> str:
    c = report.ledger.company
    letter = report.gate.track if report.gate.track != "undetermined" else "Undetermined"
    detail = "; ".join(filter(None, [c.sector, c.one_line_description]))
    name = TRACK_NAMES[report.gate.track]
    return f"{letter} – {name}" + (f" ({detail})" if detail else "") if letter != "Undetermined" else f"Track undetermined ({report.ledger.track.rationale})"


def gate_line(report: ScreeningReport) -> tuple[str, str]:
    return report.gate.label, " ".join(report.gate.reasons)


def funding_line(report: ScreeningReport) -> str:
    cap = report.capital
    raised = capital_lines(report)[0][1]
    parts = [f"{raised}"]
    if cap.by_category:
        parts.append("; ".join(f"{k}: {fmt_money(v, cap.currency)}" for k, v in cap.by_category.items()))
    if cap.total_raised is None and not cap.counted_events:
        return "Not disclosed"
    return " · ".join(parts)


def current_raise_line(report: ScreeningReport) -> str:
    r = report.ledger.current_raise
    pieces = []
    if r.target_amount is not None:
        pieces.append(f"{fmt_money(r.target_amount, r.currency)} target")
    if r.instrument:
        pieces.append(r.instrument)
    elif r.valuation_or_cap is not None:
        pieces.append(f"valuation/cap {fmt_money(r.valuation_or_cap, r.currency)}")
    if r.committed_amount is not None:
        pieces.append(f"{fmt_money(r.committed_amount, r.currency)} committed")
    if r.target_amount is not None or r.instrument:
        pieces.append(f"lead: {r.lead_investor or 'none named'}")
    if not pieces:
        return "Not disclosed: no amount, instrument, valuation, lead or use of funds"
    missing = [n for n, v in (("use of funds", r.use_of_funds), ("valuation or cap", r.valuation_or_cap)) if not v]
    return " · ".join(pieces) + (f" (not disclosed: {', '.join(missing)})" if missing else "")


def exclusion_line(report: ScreeningReport) -> str:
    ex = report.ledger.exclusion
    if ex.status == "not_excluded" or ex.category == "none":
        return "None triggered"
    label = ex.category.replace("_", " ")
    return f"{'Confirmed' if ex.status == 'confirmed' else 'Possible'}: {label}. {ex.rationale}".strip()


def next_step(report: ScreeningReport) -> str:
    a = report.assessment
    if a.recommended_next_step:
        return a.recommended_next_step
    if a.diligence_requests:
        return "Request: " + "; ".join(a.diligence_requests[:3])
    return "Review the concerns and diligence items below before an investor-matching decision."


# --- capital table ---------------------------------------------------------------
def _yes(value) -> bool:  # noqa: ANN001
    return value not in (None, "", [])


def capital_disclosure_rows(report: ScreeningReport) -> list[tuple[str, str, str]]:
    led = report.ledger
    cap = report.capital
    events = cap.counted_events
    rows: list[tuple[str, str, str]] = []

    def group(label: str, instruments: tuple[str, ...]) -> None:
        matched = [e for e in events if e.instrument in instruments]
        if not matched:
            rows.append((label, "No", f"{NOT_DISCLOSED} – diligence item"))
            return
        with_amount = [e for e in matched if e.amount is not None]
        status = "Yes" if len(with_amount) == len(matched) else "Partly"
        detail = "; ".join(
            f"{e.label}: {fmt_money(e.amount, e.currency)}{' (' + e.date + ')' if e.date else ''}" for e in matched
        )
        rows.append((label, status, detail))

    group("Equity raised to date", ("equity",))
    group("Convertible instruments (SAFE / note / KISS)", ("safe", "convertible_note", "kiss"))
    group("Debt", ("debt",))
    group("Non-dilutive / grant funding", ("grant", "non_dilutive_other"))
    unknown = [e for e in events if e.instrument == "unknown"]
    if unknown:
        rows.append(("Funding, instrument not stated", "Partly", "; ".join(f"{e.label}: {fmt_money(e.amount, e.currency)}" for e in unknown)))
    for statement in cap.cumulative_statements:
        rows.append(("Stated total raised to date", "Yes", f"{fmt_money(statement.amount, statement.currency)} (company statement; not added to itemized rounds)"))

    investors = sorted({i for e in events for i in e.investors})
    rows.append(("Named investors", "Yes" if investors else "No", ", ".join(investors) or NOT_DISCLOSED))
    r = led.current_raise
    rows.append(("Current raise amount", "Yes" if _yes(r.target_amount) else "No", fmt_money(r.target_amount, r.currency)))
    terms_known = [_yes(r.instrument), _yes(r.valuation_or_cap)]
    terms = r.instrument or NOT_DISCLOSED
    if r.valuation_or_cap is not None and fmt_money(r.valuation_or_cap, r.currency) not in terms:
        terms += f"; {fmt_money(r.valuation_or_cap, r.currency)} ({r.valuation_basis.replace('_', '-')})"
    rows.append(("Instrument / valuation or cap", "Yes" if all(terms_known) else "Partly" if any(terms_known) else "No", terms))
    lead_known = [_yes(r.committed_amount), _yes(r.lead_investor)]
    rows.append((
        "Amount committed / lead",
        "Yes" if all(lead_known) else "Partly" if any(lead_known) else "No",
        f"{fmt_money(r.committed_amount, r.currency)} / {r.lead_investor or 'no lead named'}",
    ))
    rows.append(("Use of funds", "Yes" if r.use_of_funds else "No", "; ".join(r.use_of_funds) or NOT_DISCLOSED))
    rows.append(("Milestone financed", "Yes" if r.milestone_financed else "No", r.milestone_financed or NOT_DISCLOSED))
    return rows


# --- score and sources -----------------------------------------------------------
def score_lead(report: ScreeningReport) -> str:
    sc = report.scoring
    if sc.complete:
        head = f"{sc.total:.1f} / 100 – {sc.underlying_band}."
    else:
        head = (f"Provisional: {sc.supported_points:.1f} points from {sc.assessed_weight}% assessed weight "
                f"(possible {sc.possible_min:.1f}–{sc.possible_max:.1f}); band withheld.")
    override = sc.override_applied or "No eligibility cap applies."
    if sc.effective_rating != sc.underlying_band and sc.override_applied:
        override += f" Effective rating: {sc.effective_rating}."
    note = report.assessment.score_nondisclosure_note
    return " ".join(filter(None, [head, override, note]))


def score_display(report: ScreeningReport) -> str:
    sc = report.scoring
    return f"{sc.total:.1f}" if sc.complete else "Provisional"


def sources(report: ScreeningReport) -> list[tuple[str, str | None]]:
    a = report.assessment
    first = report.meta.source_filename + (f" ({a.source_date})" if a.source_date else "")
    out: list[tuple[str, str | None]] = [(first, None)]
    seen = set()
    for f in report.external_findings:
        if f.url in seen:
            continue
        seen.add(f.url)
        out.append((f"{f.source_title or f.url} (retrieved {f.retrieved_on})", f.url))
    return out


def external_url(report: ScreeningReport, source_id: str) -> str | None:
    return next((f.url for f in report.external_findings if f.id == source_id), None)
