"""Validated data structures for extraction, evidence, analysis, scoring and the final report.

Three groups:

* **Extraction** - what was read from the file, page by page, and what could not be.
* **LLM output** - ``LedgerOutput`` (stage 1: evidence ledger and structured facts) and
  ``AssessmentOutput`` (stage 2: narrative assessment and category scores). Claude's
  JSON is validated against these models; nothing downstream reads raw model text.
* **Derived** - stage gate, capital summary, runway, readiness and scoring, all
  computed deterministically in Python from validated facts.

Unknown values are ``None`` throughout and render as "Not disclosed". Zero is
only ever a value the deck actually states.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NOT_DISCLOSED = "Not disclosed"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
class ExtractedPage(_Model):
    number: int  # 1-based position in the file (PDF page or slide order)
    label: str  # "PDF p. 3" or "Slide 3"
    text: str = ""
    tables: list[list[list[str]]] = Field(default_factory=list)
    notes: str = ""  # speaker notes (PPTX only) - never mixed into visible text
    text_source: Literal["text_layer", "ocr", "none"] = "text_layer"
    has_images: bool = False
    hidden: bool = False
    needs_review: bool = False
    review_reason: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text.strip())


class ExtractionIssue(_Model):
    severity: Literal["info", "warning", "error"]
    message: str
    pages: list[int] = Field(default_factory=list)


class ExtractionResult(_Model):
    filename: str
    file_type: Literal["pdf", "pptx", "ppt"]
    page_label_kind: Literal["PDF page", "Slide"]
    pages: list[ExtractedPage]
    issues: list[ExtractionIssue] = Field(default_factory=list)
    ocr_available: bool = False
    visual_inspection_available: bool = False
    page_images: dict[int, bytes] = Field(default_factory=dict, exclude=True, repr=False)
    converted_from_ppt: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return sum(p.char_count for p in self.pages)

    @property
    def pages_needing_review(self) -> list[int]:
        return [p.number for p in self.pages if p.needs_review]

    def label_for(self, page: int) -> str:
        for p in self.pages:
            if p.number == page:
                return p.label
        return f"{'PDF p.' if self.file_type == 'pdf' else 'Slide'} {page}"


# ---------------------------------------------------------------------------
# Evidence ledger
# ---------------------------------------------------------------------------
class EvidenceStatus(str, Enum):
    DISCLOSED = "Disclosed in deck"
    CALCULATED = "Calculated from disclosed inputs"
    INFERENCE = "Analyst inference"
    NOT_DISCLOSED = "Not disclosed"
    CONTRADICTORY = "Contradictory"
    EXTERNAL = "Externally verified"
    USER_CONTEXT = "User-supplied context"


SourceKind = Literal["slide_text", "speaker_notes", "table", "visual"]
Verification = Literal[
    "verified",
    "approximate",
    "relocated",
    "not_found",
    "page_out_of_range",
    "visual_unverifiable",
    "pending",
]

Nature = Literal[
    "actual",
    "projected",
    "target",
    "signed_contract",
    "loi",
    "pipeline",
    "pilot",
    "paid_pilot",
    "bookings",
    "collected_cash",
    "not_applicable",
    "unclear",
]

Topic = Literal[
    "company",
    "business_model",
    "traction",
    "revenue",
    "customers",
    "regulatory",
    "clinical",
    "preclinical",
    "reimbursement",
    "funding",
    "current_raise",
    "team",
    "market",
    "competition",
    "ip",
    "financials",
    "unit_economics",
    "exit",
    "risk",
    "other",
]


class SourceRef(_Model):
    page: int
    kind: SourceKind = "slide_text"
    excerpt: str = ""
    verification: Verification = "pending"
    original_page: int | None = None  # set when a citation was relocated to the page holding the excerpt


class EvidenceItem(_Model):
    id: str
    topic: Topic = "other"
    claim: str
    value: str | None = None
    status: EvidenceStatus
    nature: Nature = "not_applicable"
    period: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    calculation: str | None = None  # inputs and method, for CALCULATED items
    uncertainty: str | None = None
    citation_note: str | None = None  # set by citation verification

    @property
    def is_supported(self) -> bool:
        """True when the item rests on at least one source that verification did not reject."""
        if self.status in (EvidenceStatus.NOT_DISCLOSED, EvidenceStatus.INFERENCE):
            return False
        if self.status in (EvidenceStatus.CALCULATED, EvidenceStatus.EXTERNAL, EvidenceStatus.USER_CONTEXT):
            return True
        return any(
            s.verification in ("verified", "approximate", "relocated", "visual_unverifiable")
            for s in self.sources
        )


# ---------------------------------------------------------------------------
# Stage 1 - structured facts (Claude proposes, Python decides)
# ---------------------------------------------------------------------------
class CompanyIdentity(_Model):
    name: str | None = None
    website: str | None = None
    one_line_description: str | None = None
    sector: str | None = None
    sub_sector: str | None = None
    stated_stage: str | None = None
    headquarters: str | None = None
    business_model: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TrackClassification(_Model):
    track: Literal["A", "B", "undetermined"]
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class RevenueFact(_Model):
    metric: str  # ARR, MRR, TTM revenue, annual revenue, GMV, bookings, ...
    amount: float | None = None
    currency: str = "USD"
    period: str | None = None
    nature: Literal["actual", "projected", "bookings", "pilot", "paid_pilot", "unclear"] = "unclear"
    evidence_ids: list[str] = Field(default_factory=list)


class TrackAFacts(_Model):
    revenue: list[RevenueFact] = Field(default_factory=list)
    paying_customers: int | None = None
    paying_customers_evidence_ids: list[str] = Field(default_factory=list)
    customers_are_pilots_only: bool | None = None
    commercial_sales_beyond_pilots: bool | None = None
    states_pre_revenue: bool = False
    revenue_growth: str | None = None
    customer_concentration: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TrackBFacts(_Model):
    product_type: Literal[
        "therapeutic",
        "medical_device",
        "diagnostic",
        "digital_health_regulated",
        "digital_health_unregulated",
        "other",
    ] = "other"
    pathway: str | None = None
    jurisdiction: str | None = None
    pathway_basis: Literal["management_proposal", "regulatory_feedback", "authorization_obtained", "unknown"] = "unknown"
    pathway_appropriate: Literal["appropriate", "questionable", "unclear"] = "unclear"
    pathway_rationale: str | None = None
    states_pathway_undetermined: bool = False
    authorization_status: str | None = None  # cleared / approved / registered / CE marked - kept distinct
    preclinical_completed: str | None = None
    clinical_completed: str | None = None
    key_readouts: str | None = None
    study_limitations: str | None = None
    regulatory_interactions: str | None = None
    next_regulatory_milestone: str | None = None
    time_to_authorization: str | None = None
    cost_to_authorization: str | None = None
    reimbursement: str | None = None
    pathway_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


InstrumentCategory = Literal[
    "equity",
    "safe",
    "convertible_note",
    "kiss",
    "debt",
    "grant",
    "non_dilutive_other",
    "unknown",
]


class FundingEvent(_Model):
    label: str
    amount: float | None = None
    currency: str = "USD"
    date: str | None = None
    instrument: InstrumentCategory = "unknown"
    investors: list[str] = Field(default_factory=list)
    is_cumulative_total: bool = False  # "raised $5M to date" style statements
    status: Literal["closed", "announced", "committed", "unclear"] = "unclear"
    evidence_ids: list[str] = Field(default_factory=list)


class CurrentRaise(_Model):
    target_amount: float | None = None
    committed_amount: float | None = None
    currency: str = "USD"
    instrument: str | None = None  # as stated, e.g. "post-money SAFE, $12M cap"
    instrument_category: InstrumentCategory = "unknown"
    valuation_or_cap: float | None = None
    valuation_basis: Literal["pre_money", "post_money", "cap", "unclear"] = "unclear"
    discount: str | None = None
    interest_rate: str | None = None
    maturity: str | None = None
    lead_investor: str | None = None
    use_of_funds: list[str] = Field(default_factory=list)
    milestone_financed: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FinancialFacts(_Model):
    cash_on_hand: float | None = None
    cash_as_of: str | None = None
    monthly_burn: float | None = None
    currency: str = "USD"
    gross_margin_pct: float | None = None
    stated_runway_months: float | None = None
    projections_summary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TeamMember(_Model):
    name: str
    role: str | None = None
    full_time: bool | None = None
    background: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ExclusionCheck(_Model):
    category: Literal["none", "real_estate_development", "consulting_services", "franchise", "lifestyle_business"] = "none"
    status: Literal["not_excluded", "possible", "confirmed"] = "not_excluded"
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


READINESS_RUBRIC: dict[str, str] = {
    "ask_and_use_of_funds": "Raise amount and itemized use of funds stated",
    "instrument_terms": "Instrument and key terms (valuation, cap, discount) stated",
    "traction_metrics": "Traction or validation metrics with dates or periods",
    "financials": "Historical financials and/or projections with assumptions",
    "capital_history": "Prior funding and cap-table summary",
    "team": "Team bios showing relevant experience",
    "market_sizing": "Market sizing with sources or methodology",
    "competition": "Competitive landscape or alternatives addressed",
    "milestones": "Milestones tied to the raise, with timeline",
    "contact_and_materials": "Contact details, website and supporting materials referenced",
}


class ReadinessItem(_Model):
    key: str
    met: bool
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class LedgerOutput(_Model):
    """Stage 1 output: evidence first, facts that point at the evidence second."""

    evidence: list[EvidenceItem]
    company: CompanyIdentity
    track: TrackClassification
    track_a: TrackAFacts | None = None
    track_b: TrackBFacts | None = None
    funding_events: list[FundingEvent] = Field(default_factory=list)
    current_raise: CurrentRaise = Field(default_factory=CurrentRaise)
    financials: FinancialFacts = Field(default_factory=FinancialFacts)
    team: list[TeamMember] = Field(default_factory=list)
    exclusion: ExclusionCheck = Field(default_factory=ExclusionCheck)
    readiness: list[ReadinessItem] = Field(default_factory=list)
    visual_limitations: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 2 - assessment
# ---------------------------------------------------------------------------
CategoryKey = Literal[
    "stage_gate_fit",
    "team",
    "market_growth",
    "differentiation",
    "financials",
    "deal_terms",
    "exit_potential",
    "pitch_deck",
]


class CategoryAssessment(_Model):
    category: CategoryKey
    score: int | None = Field(default=None, ge=1, le=10)
    justification: str
    short_justification: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class EvidencedPoint(_Model):
    headline: str  # one line, <= ~14 words, used on the one-page PDF
    detail: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class DeckStrength(_Model):
    headline: str
    detail: str = ""
    pages: list[int] = Field(default_factory=list)


class DeckCritique(_Model):
    issue: str
    fix: str
    pages: list[int] = Field(default_factory=list)


class InstrumentConcern(_Model):
    instrument: str
    concern: str


class TenXScenario(_Model):
    entry_valuation: str
    ownership_at_entry: str
    dilution_assumption: str
    exit_equity_value_required: str
    plausibility: str
    assumptions_note: str = "All inputs are labeled assumptions, not deck facts."


class LabeledPoint(_Model):
    """A labeled bullet in the Screening Review ("**Stage fit:** ...")."""

    label: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class SectionAnalysis(_Model):
    summary: str
    lead: str = ""  # bold one-sentence verdict printed under the section heading
    points: list[LabeledPoint] = Field(default_factory=list)
    findings: list[EvidencedPoint] = Field(default_factory=list)


class GateEvidenceRow(_Model):
    evidence_type: str
    deck_statement: str  # what the deck states, or "None stated"
    counts_toward_gate: str
    evidence_ids: list[str] = Field(default_factory=list)


class ConditionalFlag(_Model):
    label: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ExitComparable(_Model):
    """A comparable transaction. Must reference an external finding id (X1...), or it is dropped."""

    comparable: str
    year: str | None = None
    terms: str
    relevance: str
    source_id: str


class AssessmentOutput(_Model):
    business_description: str
    capital_history: SectionAnalysis
    capital_efficiency: str
    current_raise: SectionAnalysis
    instrument_concerns: list[InstrumentConcern] = Field(default_factory=list)
    maturity_and_team: SectionAnalysis
    valuation_benchmarking: str
    differentiation: SectionAnalysis
    market_and_growth: SectionAnalysis
    financial_review: SectionAnalysis
    raise_funds_milestone: Literal["yes", "no", "unclear"] = "unclear"
    raise_funds_milestone_explanation: str = ""
    exit_potential: SectionAnalysis
    ten_x_scenario: TenXScenario | None = None
    exclusion_explanation: str
    deck_narrative_assessment: str
    deck_strengths: list[DeckStrength] = Field(default_factory=list)
    deck_critiques: list[DeckCritique] = Field(default_factory=list)
    missing_slides_or_data: list[str] = Field(default_factory=list)
    revised_slide_order: list[str] = Field(default_factory=list)
    diligence_requests: list[str] = Field(default_factory=list)
    category_assessments: list[CategoryAssessment]
    company_strengths: list[EvidencedPoint] = Field(default_factory=list)
    company_concerns: list[EvidencedPoint] = Field(default_factory=list)
    fundraising_actions: list[str] = Field(default_factory=list)
    investor_verdict: str
    readiness_justification: str = ""

    # Screening Review document fields (templates/investor_screening_review_template.md)
    value_proposition_headline: str = ""
    headline_highlights: list[str] = Field(default_factory=list)
    source_date: str | None = None
    recommended_next_step: str = ""
    stage_gate_evidence: list[GateEvidenceRow] = Field(default_factory=list)
    gate_verdict_paragraph: str = ""
    capital_lead: str = ""
    conditional_flags: list[ConditionalFlag] = Field(default_factory=list)
    exit_comparables: list[ExitComparable] = Field(default_factory=list)
    exclusion_verdict: str = ""
    investor_matching_note: str = ""
    deck_lead: str = ""
    score_nondisclosure_note: str = ""
    verdict_headline: str = ""

    @field_validator("deck_strengths", "deck_critiques", "company_strengths", "company_concerns")
    @classmethod
    def _cap_five(cls, value: list) -> list:
        return value[:5]


# ---------------------------------------------------------------------------
# Optional external research
# ---------------------------------------------------------------------------
class ExternalFinding(_Model):
    id: str
    claim: str
    url: str
    source_title: str = ""
    cited_text: str = ""
    retrieved_on: str


# ---------------------------------------------------------------------------
# Derived (deterministic)
# ---------------------------------------------------------------------------
class GateStatus(str, Enum):
    MEETS = "Meets Stage Gate"
    PARTIAL = "Partially Meets"
    DOES_NOT_MEET = "Does Not Meet"
    CANNOT_DETERMINE = "Cannot Determine"


class StageEstimate(_Model):
    """Analyst-style estimate of stage and regulatory pathway, used when the deck alone cannot settle the gate."""

    track: Literal["A", "B"]
    estimated_stage: str  # e.g. "Seed - FDA-cleared device, pre-commercial launch"
    gate_status: Literal["Meets Stage Gate", "Partially Meets", "Does Not Meet"]
    confidence: Literal["low", "medium", "high"] = "low"
    regulatory_pathway: str | None = None  # Track B: e.g. "510(k)", "De Novo", "PMA", "510(k)-exempt Class I"
    jurisdiction: str | None = None
    authorization_status: str | None = None  # e.g. "Cleared (K123456, 2024)" / "Not found in FDA databases"
    clearance_reference: str | None = None  # 510(k)/De Novo/PMA number or product code when found
    rationale: str  # 2-3 sentences: why this stage and pathway, what is inferred vs sourced
    verification_needed: str | None = None  # the one document that would confirm the estimate
    evidence_ids: list[str] = Field(default_factory=list)  # deck evidence ids (E*) and external finding ids (S*)


class GateResult(_Model):
    track: Literal["A", "B", "undetermined"]
    track_label: str
    status: GateStatus
    reasons: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    estimated: bool = False
    estimate: StageEstimate | None = None

    @property
    def label(self) -> str:
        return f"{self.status.value} (estimated)" if self.estimated else self.status.value


class CapitalSummary(_Model):
    total_raised: float | None = None
    total_basis: Literal["stated_cumulative", "sum_of_rounds", "not_disclosed", "mixed_currency"] = "not_disclosed"
    currency: str = "USD"
    by_category: dict[str, float] = Field(default_factory=dict)
    counted_events: list[FundingEvent] = Field(default_factory=list)
    duplicates_removed: list[str] = Field(default_factory=list)
    cumulative_statements: list[FundingEvent] = Field(default_factory=list)
    undisclosed_amount_events: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RunwayResult(_Model):
    months: float | None = None
    basis: str
    below_six_months: bool | None = None


class InstrumentFlag(_Model):
    flag: str
    concern: str


class ReadinessResult(_Model):
    score: int
    items: list[ReadinessItem]
    rubric_note: str


class CategoryScore(_Model):
    key: CategoryKey
    name: str
    weight: int
    score: int | None
    points: float | None
    justification: str
    short_justification: str
    adjustment_note: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


FitBand = Literal["Strong Fit", "Moderate Fit", "Weak Fit", "Likely Pass"]


class ScoreResult(_Model):
    categories: list[CategoryScore]
    complete: bool
    total: float | None  # only when complete
    supported_points: float
    assessed_weight: int
    possible_min: float
    possible_max: float
    underlying_band: FitBand | None
    effective_rating: str
    override_applied: str | None = None
    status_label: str  # concise text for the PDF: "Final", "Provisional", ...


class SensitivityFlags(_Model):
    confidential: bool
    reasons: list[str] = Field(default_factory=list)


class ReportMeta(_Model):
    title: str
    company_name: str
    website: str | None
    source_filename: str
    analysis_date: str
    model: str
    app_version: str
    external_research_enabled: bool
    visual_inspection_used: bool
    page_label_kind: str
    page_count: int
    source_file_type: str = ""
    run_id: str = ""  # unique per analysis; used as the email idempotency key


class ScreeningReport(_Model):
    meta: ReportMeta
    extraction_issues: list[ExtractionIssue]
    pages_needing_review: list[int]
    user_context: str | None = None
    ledger: LedgerOutput
    external_findings: list[ExternalFinding] = Field(default_factory=list)
    assessment: AssessmentOutput
    gate: GateResult
    capital: CapitalSummary
    runway: RunwayResult
    instrument_flags: list[InstrumentFlag]
    readiness: ReadinessResult
    scoring: ScoreResult
    sensitivity: SensitivityFlags
    limitations: list[str]
    citation_summary: dict[str, int] = Field(default_factory=dict)
    page_labels: dict[int, str] = Field(default_factory=dict)

    def evidence_by_id(self) -> dict[str, EvidenceItem]:
        return {e.id: e for e in self.ledger.evidence}

    def cite(self, evidence_ids: list[str], limit: int = 3) -> str:
        """Human-readable page references for a set of evidence ids, e.g. 'Slide 4; Slide 9 notes'."""
        by_id = self.evidence_by_id()
        labels: list[str] = []
        for eid in evidence_ids:
            item = by_id.get(eid)
            if item is None:
                continue
            for src in item.sources:
                if src.verification in ("not_found", "page_out_of_range"):
                    continue
                label = self.page_labels.get(src.page, f"p. {src.page}")
                if src.kind == "speaker_notes":
                    label += " notes"
                elif src.kind == "visual":
                    label += " (visual)"
                if label not in labels:
                    labels.append(label)
            if item.status == EvidenceStatus.USER_CONTEXT and "user context" not in labels:
                labels.append("user context")
        return "; ".join(labels[:limit])
