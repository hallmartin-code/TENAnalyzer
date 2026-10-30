"""Screening pipeline: ledger -> citation verification -> deterministic rules -> assessment -> scoring -> report."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path

from ten_screener import REPORT_TITLE, __version__
from ten_screener.analysis import prompts, research
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.config import Settings
from ten_screener.evidence import drop_unknown_ids, verify_ledger
from ten_screener.rules import (
    calculate_runway,
    evaluate_stage_gate,
    exclusion_confirmed,
    instrument_flags,
    readiness,
    sensitivity,
    summarise_capital,
)
from ten_screener.schemas import (
    AssessmentOutput,
    EvidenceStatus,
    ExtractionResult,
    LedgerOutput,
    ReportMeta,
    ScreeningReport,
    TrackAFacts,
    TrackBFacts,
)
from ten_screener.scoring import score

LOGGER = logging.getLogger(__name__)

Progress = Callable[[str], None]


def analyse(
    extraction: ExtractionResult,
    settings: Settings,
    *,
    user_context: str | None = None,
    external_research: bool = False,
    client: ClaudeClient | None = None,
    progress: Progress | None = None,
    today: date | None = None,
) -> tuple[ScreeningReport, dict]:
    """Run the full screening. Returns the report and API usage statistics."""
    say = progress or (lambda _msg: None)
    client = client or ClaudeClient(settings)
    analysis_date = (today or date.today()).isoformat()
    deck_blocks = prompts.deck_content_blocks(extraction, user_context)

    say("Stage 1 of 2: building the evidence ledger")
    ledger = client.generate_json(
        prompts.SYSTEM_PROMPT,
        [{"role": "user", "content": deck_blocks + [{"type": "text", "text": prompts.ledger_task(extraction)}]}],
        LedgerOutput,
        label="evidence ledger",
    )

    say("Verifying citations against the extracted text")
    citation_counts = verify_ledger(ledger, extraction)
    if not user_context:
        for item in ledger.evidence:
            if item.status == EvidenceStatus.USER_CONTEXT:
                item.status = EvidenceStatus.INFERENCE
                item.citation_note = "Labeled as user context, but no user context was supplied."
    _normalise_facts(ledger)

    say("Applying stage-gate, capital and readiness rules")
    gate = evaluate_stage_gate(ledger)
    capital = summarise_capital(ledger)
    runway = calculate_runway(ledger)
    flags = instrument_flags(ledger)
    ready = readiness(ledger)
    sens = sensitivity(ledger)

    external, research_notes = [], []
    if external_research:
        say("Running optional external research")
        external, research_notes = research.run_research(client, ledger, analysis_date)

    derived = {
        "stage_gate": gate.model_dump(mode="json"),
        "capital_summary": capital.model_dump(mode="json", exclude={"counted_events", "cumulative_statements"}),
        "runway": runway.model_dump(mode="json"),
        "instrument_flags": [f.model_dump(mode="json") for f in flags],
        "readiness": {"score": ready.score, "items": [i.model_dump(mode="json") for i in ready.items]},
        "exclusion_confirmed": exclusion_confirmed(ledger),
    }
    say("Stage 2 of 2: writing the investor assessment")
    assessment = client.generate_json(
        prompts.SYSTEM_PROMPT,
        [{
            "role": "user",
            "content": deck_blocks + [{
                "type": "text",
                "text": prompts.assessment_task(
                    ledger.model_dump_json(exclude_none=True),
                    json.dumps(derived),
                    json.dumps([f.model_dump(mode="json") for f in external]) if external else None,
                    extraction.visual_inspection_available,
                ),
            }],
        }],
        AssessmentOutput,
        label="assessment",
    )
    _clean_assessment_ids(assessment, ledger, {f.id for f in external})

    say("Scoring")
    scoring = score(assessment, gate, exclusion_confirmed=exclusion_confirmed(ledger))

    company_name = (ledger.company.name or "").strip() or Path(extraction.filename).stem
    report = ScreeningReport(
        meta=ReportMeta(
            title=REPORT_TITLE,
            company_name=company_name,
            website=ledger.company.website,
            source_filename=extraction.filename,
            analysis_date=analysis_date,
            model=client.model,
            app_version=__version__,
            external_research_enabled=external_research,
            visual_inspection_used=extraction.visual_inspection_available,
            page_label_kind=extraction.page_label_kind,
            page_count=extraction.page_count,
            source_file_type=extraction.file_type,
            run_id=uuid.uuid4().hex,
        ),
        extraction_issues=extraction.issues,
        pages_needing_review=extraction.pages_needing_review,
        user_context=user_context.strip() if user_context and user_context.strip() else None,
        ledger=ledger,
        external_findings=external,
        assessment=assessment,
        gate=gate,
        capital=capital,
        runway=runway,
        instrument_flags=flags,
        readiness=ready,
        scoring=scoring,
        sensitivity=sens,
        limitations=build_limitations(extraction, ledger, assessment, citation_counts, external_research, research_notes, user_context),
        citation_summary=citation_counts,
        page_labels={p.number: p.label for p in extraction.pages},
    )
    return report, client.usage.as_dict()


def _normalise_facts(ledger: LedgerOutput) -> None:
    """Drop references to evidence ids that do not exist, and ensure track facts exist for the track."""
    known = {e.id for e in ledger.evidence}
    if ledger.track.track in ("A", "undetermined") and ledger.track_a is None:
        ledger.track_a = TrackAFacts()
    if ledger.track.track in ("B", "undetermined") and ledger.track_b is None:
        ledger.track_b = TrackBFacts()
    for obj in _fact_objects(ledger):
        for name in ("evidence_ids", "paying_customers_evidence_ids", "pathway_evidence_ids"):
            if hasattr(obj, name):
                setattr(obj, name, drop_unknown_ids(getattr(obj, name), known))


def _fact_objects(ledger: LedgerOutput) -> list:
    objs: list = [ledger.company, ledger.track, ledger.current_raise, ledger.financials, ledger.exclusion]
    objs += ledger.funding_events + ledger.team + ledger.readiness
    if ledger.track_a:
        objs.append(ledger.track_a)
        objs += ledger.track_a.revenue
    if ledger.track_b:
        objs.append(ledger.track_b)
    return objs


def _clean_assessment_ids(assessment: AssessmentOutput, ledger: LedgerOutput, external_ids: set[str]) -> None:
    known = {e.id for e in ledger.evidence} | external_ids
    for cat in assessment.category_assessments:
        cat.evidence_ids = drop_unknown_ids(cat.evidence_ids, known)
    for section in (assessment.capital_history, assessment.current_raise, assessment.maturity_and_team,
                    assessment.differentiation, assessment.market_and_growth, assessment.financial_review,
                    assessment.exit_potential):
        for point in section.findings:
            point.evidence_ids = drop_unknown_ids(point.evidence_ids, known)
        for point in section.points:
            point.evidence_ids = drop_unknown_ids(point.evidence_ids, known)
    for point in assessment.company_strengths + assessment.company_concerns:
        point.evidence_ids = drop_unknown_ids(point.evidence_ids, known)
    for row in assessment.stage_gate_evidence:
        row.evidence_ids = drop_unknown_ids(row.evidence_ids, known)
    for flag in assessment.conditional_flags:
        flag.evidence_ids = drop_unknown_ids(flag.evidence_ids, known)
    # Comparable exits are never accepted from model memory: each must cite a retrieved external finding.
    assessment.exit_comparables = [c for c in assessment.exit_comparables if c.source_id in external_ids]
    highlights = [h for h in assessment.headline_highlights if h and h.lower() in assessment.value_proposition_headline.lower()]
    assessment.headline_highlights = highlights[:3]
    for item in assessment.deck_strengths:
        item.pages = [p for p in item.pages if 1 <= p <= 10_000]
    seen = set()
    unique = []
    for cat in assessment.category_assessments:  # one entry per category; first wins
        if cat.category not in seen:
            seen.add(cat.category)
            unique.append(cat)
    assessment.category_assessments = unique


def build_limitations(
    extraction: ExtractionResult,
    ledger: LedgerOutput,
    assessment: AssessmentOutput,
    citation_counts: dict[str, int],
    external_research: bool,
    research_notes: list[str],
    user_context: str | None,
) -> list[str]:
    out: list[str] = []
    for issue in extraction.issues:
        if issue.severity in ("warning", "error"):
            pages = f" ({', '.join(extraction.label_for(p) for p in issue.pages[:8])}{'...' if len(issue.pages) > 8 else ''})" if issue.pages else ""
            out.append(issue.message + pages)
    if not extraction.visual_inspection_available:
        out.append("Visual inspection was unavailable; charts and images were not read and visual design was not judged.")
    unverified = citation_counts.get("not_found", 0) + citation_counts.get("page_out_of_range", 0)
    if unverified:
        out.append(f"{unverified} cited excerpt(s) could not be located in the extracted text; affected claims were downgraded.")
    if citation_counts.get("visual_unverifiable"):
        out.append(f"{citation_counts['visual_unverifiable']} citation(s) rely on rendered images and could not be text-verified.")
    if not external_research:
        out.append("External research disabled: comparable exits, valuation benchmarks and market data were not independently checked.")
    out.extend(research_notes)
    if user_context:
        out.append("Analyst-supplied context was considered and is labeled separately from deck evidence.")
    if len(assessment.deck_strengths) < 5:
        out.append(f"Only {len(assessment.deck_strengths)} deck strength(s) are supported by the materials.")
    if len(assessment.deck_critiques) < 5:
        out.append(f"Only {len(assessment.deck_critiques)} deck critique(s) were identified with sufficient support.")
    if len(assessment.company_strengths) < 5:
        out.append(f"Only {len(assessment.company_strengths)} company strength(s) are supported by the evidence.")
    if len(assessment.company_concerns) < 5:
        out.append(f"Only {len(assessment.company_concerns)} company concern(s) were identified with sufficient support.")
    out.extend(ledger.visual_limitations[:5])
    return out
