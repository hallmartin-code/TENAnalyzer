"""SYNTHETIC TEST FIXTURES - fictional companies, people, investors and figures.

Nothing here describes a real company. The deck text, the stage-1 ledger and the
stage-2 assessment are hand-written to be mutually consistent, so citation
verification and the deterministic rules can be exercised end to end without
an API call.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from ten_screener.schemas import ExtractedPage, ExtractionResult

SYNTHETIC_BANNER = "SYNTHETIC TEST FIXTURE - fictional company for software testing"

# ---------------------------------------------------------------------------
# Track A deck: text per page, used both for generated PDFs and for ExtractionResult
# ---------------------------------------------------------------------------
TRACK_A_PAGES: list[str] = [
    f"{SYNTHETIC_BANNER}\nNorthwind Ledger Analytics\nAutomated reconciliation for mid-market finance teams\nwww.northwind-ledger.example",
    "The Problem\nFinance teams at mid-market companies spend 9 days every month closing the books by hand.\n"
    "Spreadsheet reconciliation causes errors and late reporting.",
    "Traction\n$1.2M ARR as of June 2026\n34 paying customers on annual contracts\n3x year-over-year ARR growth\n"
    "Largest customer is 11% of ARR",
    "Funding to date\nWe have raised $2.6M to date.\nSeed: $2.0M SAFE (2024) led by Example Ventures\n"
    "NSF SBIR Phase I grant: $600K (2023)",
    "Team\nJane Doe, CEO - former VP Finance at Example Corp, full-time\n"
    "Raj Patel, CTO - 12 years building data platforms, full-time",
    "The Ask\nRaising $4.0M on a post-money SAFE with a $20M cap\n$1.5M committed\n"
    "Use of funds: 50% engineering, 30% sales, 20% G&A\nMilestone: $4M ARR within 18 months",
    "Financials\nCash on hand $1.1M (September 2026)\nMonthly burn $150K\nGross margin 78%\n"
    "Projection: $9M revenue in 2028",
]
TRACK_A_NOTES = {6: "Reminder: the seed round of $2.0M closed in 2024."}


def track_a_extraction(**overrides) -> ExtractionResult:
    pages = [
        ExtractedPage(number=i, label=f"PDF p. {i}", text=text, notes=TRACK_A_NOTES.get(i, ""))
        for i, text in enumerate(TRACK_A_PAGES, start=1)
    ]
    data = dict(filename="northwind_synthetic.pdf", file_type="pdf", page_label_kind="PDF page", pages=pages)
    data.update(overrides)
    return ExtractionResult(**data)


def _src(page: int, excerpt: str, kind: str = "slide_text") -> dict:
    return {"page": page, "kind": kind, "excerpt": excerpt}


TRACK_A_LEDGER: dict = {
    "evidence": [
        {"id": "E1", "topic": "company", "claim": "Company name and website", "value": "Northwind Ledger Analytics", "status": "Disclosed in deck",
         "sources": [_src(1, "Northwind Ledger Analytics"), _src(1, "www.northwind-ledger.example")]},
        {"id": "E2", "topic": "revenue", "claim": "Annual recurring revenue", "value": "$1.2M ARR", "status": "Disclosed in deck",
         "nature": "actual", "period": "June 2026", "sources": [_src(3, "$1.2M ARR as of June 2026")]},
        {"id": "E3", "topic": "customers", "claim": "Paying customers", "value": "34", "status": "Disclosed in deck",
         "nature": "signed_contract", "sources": [_src(3, "34 paying customers on annual contracts")]},
        {"id": "E4", "topic": "traction", "claim": "ARR growth", "value": "3x YoY", "status": "Disclosed in deck",
         "sources": [_src(3, "3x year-over-year ARR growth")]},
        {"id": "E5", "topic": "funding", "claim": "Cumulative capital raised", "value": "$2.6M", "status": "Disclosed in deck",
         "sources": [_src(4, "We have raised $2.6M to date.")]},
        {"id": "E6", "topic": "funding", "claim": "Seed SAFE", "value": "$2.0M (2024)", "status": "Disclosed in deck",
         "sources": [_src(4, "Seed: $2.0M SAFE (2024) led by Example Ventures"), _src(6, "the seed round of $2.0M closed in 2024", "speaker_notes")]},
        {"id": "E7", "topic": "funding", "claim": "NSF SBIR Phase I grant", "value": "$600K (2023)", "status": "Disclosed in deck",
         "sources": [_src(4, "NSF SBIR Phase I grant: $600K (2023)")]},
        {"id": "E8", "topic": "team", "claim": "CEO background", "value": "Former VP Finance", "status": "Disclosed in deck",
         "sources": [_src(5, "Jane Doe, CEO - former VP Finance at Example Corp, full-time")]},
        {"id": "E9", "topic": "current_raise", "claim": "Current raise and terms", "value": "$4.0M post-money SAFE, $20M cap", "status": "Disclosed in deck",
         "sources": [_src(6, "Raising $4.0M on a post-money SAFE with a $20M cap")]},
        {"id": "E10", "topic": "current_raise", "claim": "Committed capital", "value": "$1.5M", "status": "Disclosed in deck",
         "sources": [_src(6, "$1.5M committed")]},
        {"id": "E11", "topic": "financials", "claim": "Cash and burn", "value": "$1.1M cash; $150K/month burn", "status": "Disclosed in deck",
         "sources": [_src(7, "Cash on hand $1.1M (September 2026)"), _src(7, "Monthly burn $150K")]},
        {"id": "E12", "topic": "financials", "claim": "Revenue projection", "value": "$9M revenue in 2028", "status": "Disclosed in deck",
         "nature": "projected", "sources": [_src(7, "Projection: $9M revenue in 2028")]},
        {"id": "E13", "topic": "market", "claim": "Market size", "status": "Not disclosed", "sources": []},
        {"id": "E14", "topic": "ip", "claim": "Patents", "status": "Not disclosed", "sources": []},
        {"id": "E15", "topic": "financials", "claim": "Runway at current burn", "value": "7.3 months", "status": "Calculated from disclosed inputs",
         "calculation": "$1.1M cash / $150K monthly burn", "sources": []},
    ],
    "company": {"name": "Northwind Ledger Analytics", "website": "www.northwind-ledger.example",
                "one_line_description": "Automated reconciliation software for mid-market finance teams.",
                "sector": "B2B SaaS", "sub_sector": "Finance automation", "stated_stage": "Seed", "evidence_ids": ["E1"]},
    "track": {"track": "A", "rationale": "B2B software; no regulated health product.", "evidence_ids": ["E1"]},
    "track_a": {
        "revenue": [{"metric": "ARR", "amount": 1200000, "period": "June 2026", "nature": "actual", "evidence_ids": ["E2"]}],
        "paying_customers": 34, "paying_customers_evidence_ids": ["E3"],
        "customers_are_pilots_only": False, "commercial_sales_beyond_pilots": True, "states_pre_revenue": False,
        "revenue_growth": "3x year-over-year ARR", "customer_concentration": "Largest customer 11% of ARR", "evidence_ids": ["E2", "E3", "E4"],
    },
    "funding_events": [
        {"label": "Raised to date", "amount": 2600000, "is_cumulative_total": True, "status": "closed", "evidence_ids": ["E5"]},
        {"label": "Seed", "amount": 2000000, "date": "2024", "instrument": "safe", "investors": ["Example Ventures"], "status": "closed", "evidence_ids": ["E6"]},
        {"label": "Seed round", "amount": 2000000, "date": "2024", "instrument": "safe", "investors": [], "status": "closed", "evidence_ids": ["E6"]},
        {"label": "NSF SBIR Phase I", "amount": 600000, "date": "2023", "instrument": "grant", "status": "closed", "evidence_ids": ["E7"]},
    ],
    "current_raise": {"target_amount": 4000000, "committed_amount": 1500000, "instrument": "post-money SAFE with a $20M cap",
                      "instrument_category": "safe", "valuation_or_cap": 20000000, "valuation_basis": "cap",
                      "use_of_funds": ["50% engineering", "30% sales", "20% G&A"], "milestone_financed": "$4M ARR within 18 months",
                      "evidence_ids": ["E9", "E10"]},
    "financials": {"cash_on_hand": 1100000, "cash_as_of": "September 2026", "monthly_burn": 150000, "gross_margin_pct": 78,
                   "projections_summary": "$9M revenue in 2028", "evidence_ids": ["E11"]},
    "team": [{"name": "Jane Doe", "role": "CEO", "full_time": True, "background": "Former VP Finance", "evidence_ids": ["E8"]}],
    "exclusion": {"category": "none", "status": "not_excluded", "rationale": "Software product business."},
    "readiness": [
        {"key": "ask_and_use_of_funds", "met": True, "evidence_ids": ["E9"]},
        {"key": "instrument_terms", "met": True, "evidence_ids": ["E9"]},
        {"key": "traction_metrics", "met": True, "evidence_ids": ["E2"]},
        {"key": "financials", "met": True, "evidence_ids": ["E11"]},
        {"key": "capital_history", "met": True, "evidence_ids": ["E5"]},
        {"key": "team", "met": True, "evidence_ids": ["E8"]},
        {"key": "market_sizing", "met": False},
        {"key": "competition", "met": False},
        {"key": "milestones", "met": True, "evidence_ids": ["E9"]},
        {"key": "contact_and_materials", "met": True, "evidence_ids": ["E1"]},
    ],
    "visual_limitations": [],
    "contradictions": [],
}


def _cat(key: str, score: int | None, text: str, ids: list[str]) -> dict:
    return {"category": key, "score": score, "justification": text, "short_justification": text, "evidence_ids": ids}


def _point(headline: str, ids: list[str]) -> dict:
    return {"headline": headline, "detail": headline + " (synthetic detail).", "evidence_ids": ids}


def _section(summary: str, ids: list[str]) -> dict:
    return {"summary": summary, "findings": [_point(summary, ids)]}


TRACK_A_ASSESSMENT: dict = {
    "business_description": "Northwind sells reconciliation software to finance teams at mid-market companies on annual contracts.",
    "capital_history": _section("Seed SAFE plus a non-dilutive SBIR grant; $2.6M stated raised to date.", ["E5", "E6", "E7"]),
    "capital_efficiency": "$1.2M ARR on $2.6M raised is efficient for seed stage.",
    "current_raise": _section("$4.0M post-money SAFE at a $20M cap with $1.5M committed; no lead named.", ["E9", "E10"]),
    "instrument_concerns": [],
    "maturity_and_team": _section("Two full-time founders with domain and technical depth.", ["E8"]),
    "valuation_benchmarking": "Valuation benchmarking is pending diligence; external research disabled.",
    "differentiation": _section("Differentiation is asserted but competitors are not named.", []),
    "market_and_growth": _section("Market size is not disclosed.", ["E13"]),
    "financial_review": _section("Runway of 7.3 months at current burn; projections are aggressive.", ["E11", "E12"]),
    "raise_funds_milestone": "yes",
    "raise_funds_milestone_explanation": "The raise targets $4M ARR within 18 months.",
    "exit_potential": _section("Strategic buyers in finance software are plausible; comparable exits not researched.", []),
    "ten_x_scenario": None,
    "exclusion_explanation": "Software product business; not in an excluded category.",
    "deck_narrative_assessment": "Clear and concise narrative; visual inspection was unavailable.",
    "deck_strengths": [{"headline": "Traction slide leads with ARR and customers", "pages": [3]},
                       {"headline": "Specific ask with use of funds", "pages": [6]}],
    "deck_critiques": [{"issue": "No market sizing", "fix": "Add a sourced bottoms-up SAM slide", "pages": [2]},
                       {"issue": "No competition slide", "fix": "Add a competitive matrix naming alternatives", "pages": []}],
    "missing_slides_or_data": ["Market sizing", "Competition", "Cap table summary"],
    "revised_slide_order": [],
    "diligence_requests": ["ARR by customer and cohort", "Cap table", "SAFE documents"],
    "category_assessments": [
        _cat("stage_gate_fit", 9, "Actual ARR with 34 paying customers.", ["E2", "E3"]),
        _cat("team", 7, "Relevant finance and technical founders.", ["E8"]),
        _cat("market_growth", 6, "Growth strong; market size not disclosed.", ["E4"]),
        _cat("differentiation", 5, "Differentiation asserted, not evidenced.", []),
        _cat("financials", 7, "High gross margin; 7.3-month runway.", ["E11"]),
        _cat("deal_terms", 7, "Standard post-money SAFE, $20M cap.", ["E9"]),
        _cat("exit_potential", 6, "Plausible strategic buyers; no comparables.", []),
        _cat("pitch_deck", 6, "Clear but missing market and competition.", []),
    ],
    "company_strengths": [_point("$1.2M ARR with 3x year-over-year growth", ["E2", "E4"]),
                          _point("34 paying customers on annual contracts", ["E3"]),
                          _point("78% gross margin", ["E11"])],
    "company_concerns": [_point("Runway of 7.3 months before the new raise", ["E11"]),
                         _point("No lead investor named for the current round", ["E10"]),
                         _point("Market size and competitors not disclosed", ["E13"])],
    "fundraising_actions": ["Add sourced market sizing", "Add a competition slide", "Secure a lead investor"],
    "investor_verdict": "Northwind meets the Track A stage gate with $1.2M ARR and 34 paying customers. Advance to a partner call subject to market and competition diligence.",
    "readiness_justification": "Eight of ten readiness items are evidenced.",
}


def _lp(label: str, text: str, ids: list[str] | None = None) -> dict:
    return {"label": label, "text": text, "evidence_ids": ids or []}


TRACK_A_ASSESSMENT.update({
    "value_proposition_headline": "automated month-end reconciliation for mid-market finance",
    "headline_highlights": ["automated", "month-end reconciliation", "mid-market"],
    "source_date": "September 2026",
    "recommended_next_step": "Request ARR by cohort, the cap table and SAFE documents before an investor-matching decision.",
    "stage_gate_evidence": [
        {"evidence_type": "Paid revenue / ARR", "deck_statement": "$1.2M ARR as of June 2026", "counts_toward_gate": "Yes - actual recurring revenue", "evidence_ids": ["E2"]},
        {"evidence_type": "Paying customers", "deck_statement": "34 paying customers on annual contracts", "counts_toward_gate": "Yes - commercial contracts, not pilots", "evidence_ids": ["E3"]},
        {"evidence_type": "Customer concentration", "deck_statement": "Largest customer is 11% of ARR", "counts_toward_gate": "Context only; concentration is moderate", "evidence_ids": []},
    ],
    "gate_verdict_paragraph": "Actual ARR and a disclosed paying-customer count satisfy the Track A gate. Confirm ARR by customer and contract.",
    "capital_lead": "Capital history is clear and modest; the current SAFE has terms but no lead investor.",
    "conditional_flags": [{"label": "Runway", "text": "About 7 months at current burn before the new round closes.", "evidence_ids": ["E11"]}],
    "exclusion_verdict": "No exclusion triggered.",
    "investor_matching_note": "",
    "deck_lead": "A concise deck with strong traction, missing market sizing and competition.",
    "score_nondisclosure_note": "Differentiation scores are limited by missing competitor information rather than weak evidence.",
    "verdict_headline": "Moderate Fit: commercial traction meets the gate; market and competition need diligence.",
})
TRACK_A_ASSESSMENT["maturity_and_team"]["lead"] = "A complete two-founder team with relevant domain depth."
TRACK_A_ASSESSMENT["maturity_and_team"]["points"] = [
    _lp("Stage fit", "Seed stage with $1.2M ARR; valuation benchmarking pending diligence.", ["E2"]),
    _lp("CEO", "Jane Doe, former VP Finance at Example Corp, full-time.", ["E8"]),
    _lp("Gaps to probe", "No named sales leader for the planned go-to-market expansion."),
    _lp("Public footprint", "External research disabled - not checked."),
]
TRACK_A_ASSESSMENT["differentiation"]["points"] = [
    _lp("Claimed edge", "Automated reconciliation replacing manual spreadsheet work."),
    _lp("Competitive field", "Competitors are not named in the deck."),
    _lp("IP", "No patents disclosed.", ["E14"]),
]
TRACK_A_ASSESSMENT["market_and_growth"]["points"] = [
    _lp("TAM/SAM/SOM", "Not provided.", ["E13"]),
    _lp("Scalability", "Annual software contracts with 78% gross margin.", ["E11"]),
]
TRACK_A_ASSESSMENT["financial_review"]["points"] = [
    _lp("Revenue and pricing", "$1.2M ARR actual; $9M 2028 revenue is a projection.", ["E2", "E12"]),
    _lp("Burn and runway", "$150K monthly burn against $1.1M cash.", ["E11"]),
]
TRACK_A_ASSESSMENT["exit_potential"]["points"] = [
    _lp("Likely acquirers", "Finance software platforms; no relationships stated."),
    _lp("10x test", "Cannot be computed without comparable multiples."),
    _lp("Timing", "Earliest interest likely after reaching the stated ARR milestone."),
]


def track_a_ledger_json() -> str:
    return json.dumps(TRACK_A_LEDGER)


def track_a_assessment_json() -> str:
    return json.dumps(TRACK_A_ASSESSMENT)


def dense_assessment() -> dict:
    """Worst-case wording: maximal lists and long text everywhere, to stress the one-page fit."""
    a = copy.deepcopy(TRACK_A_ASSESSMENT)
    long = ("This is a deliberately long synthetic sentence used to stress test the layout engine with dense findings, "
            "many qualifiers, numerous figures such as $1.2M ARR and 34 customers, and extended commentary that keeps going.")
    a["business_description"] = long + " " + long
    a["company_strengths"] = [_point(f"Strength {i}: " + long, ["E2"]) for i in range(1, 6)]
    a["company_concerns"] = [_point(f"Concern {i}: " + long, ["E11"]) for i in range(1, 6)]
    a["fundraising_actions"] = [f"Action {i}: " + long for i in range(1, 6)]
    a["investor_verdict"] = long * 3
    for cat in a["category_assessments"]:
        cat["short_justification"] = long
        cat["justification"] = long
    a["deck_strengths"] = [{"headline": f"Deck strength {i}", "detail": long, "pages": [i]} for i in range(1, 6)]
    a["deck_critiques"] = [{"issue": f"Critique {i}", "fix": long, "pages": [i]} for i in range(1, 6)]
    return a


def dense_ledger() -> dict:
    ledger = copy.deepcopy(TRACK_A_LEDGER)
    ledger["company"]["name"] = (
        "The Extraordinarily Long Synthetic Company Name International Holdings and Partners Limited Liability Company of North America"
    )
    ledger["company"]["website"] = "www.an-unusually-long-synthetic-domain-name-for-layout-testing.example"
    return ledger


# ---------------------------------------------------------------------------
# Track B (life science) - regulatory pathway defined, no preclinical data
# ---------------------------------------------------------------------------
TRACK_B_PAGES = [
    f"{SYNTHETIC_BANNER}\nHelioScan Diagnostics\nPoint-of-care imaging device for wound assessment",
    "Regulatory strategy\nWe plan a 510(k) submission to the US FDA citing a cleared predicate device.\nPre-submission meeting planned for Q2 2027",
    "The Ask\nRaising $3M seed (priced equity, $9M pre-money)\nUse of funds: verification testing, 510(k) submission, quality system",
]

TRACK_B_LEDGER: dict = {
    "evidence": [
        {"id": "E1", "topic": "company", "claim": "Company name", "value": "HelioScan Diagnostics", "status": "Disclosed in deck",
         "sources": [_src(1, "HelioScan Diagnostics")]},
        {"id": "E2", "topic": "regulatory", "claim": "Proposed regulatory pathway", "value": "FDA 510(k)", "status": "Disclosed in deck",
         "sources": [_src(2, "We plan a 510(k) submission to the US FDA citing a cleared predicate device.")]},
        {"id": "E3", "topic": "preclinical", "claim": "Preclinical or bench data", "status": "Not disclosed", "sources": []},
        {"id": "E4", "topic": "current_raise", "claim": "Current raise", "value": "$3M seed, $9M pre-money", "status": "Disclosed in deck",
         "sources": [_src(3, "Raising $3M seed (priced equity, $9M pre-money)")]},
    ],
    "company": {"name": "HelioScan Diagnostics", "sector": "Medical devices", "stated_stage": "Seed", "evidence_ids": ["E1"]},
    "track": {"track": "B", "rationale": "Medical imaging device requiring FDA clearance.", "evidence_ids": ["E2"]},
    "track_b": {"product_type": "medical_device", "pathway": "510(k)", "jurisdiction": "US", "pathway_basis": "management_proposal",
                "pathway_appropriate": "appropriate", "pathway_rationale": "Predicate exists for wound imaging devices.",
                "preclinical_completed": None, "next_regulatory_milestone": "Pre-submission meeting Q2 2027",
                "pathway_evidence_ids": ["E2"], "evidence_ids": ["E2", "E3"]},
    "current_raise": {"target_amount": 3000000, "instrument": "priced equity", "instrument_category": "equity",
                      "valuation_or_cap": 9000000, "valuation_basis": "pre_money", "evidence_ids": ["E4"]},
    "readiness": [{"key": "ask_and_use_of_funds", "met": True, "evidence_ids": ["E4"]}],
}


def track_b_extraction() -> ExtractionResult:
    pages = [ExtractedPage(number=i, label=f"Slide {i}", text=t) for i, t in enumerate(TRACK_B_PAGES, start=1)]
    return ExtractionResult(filename="helioscan_synthetic.pptx", file_type="pptx", page_label_kind="Slide", pages=pages)


# ---------------------------------------------------------------------------
# Fake Anthropic SDK client (no network)
# ---------------------------------------------------------------------------
class _Stream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self._message, Exception):
            raise self._message
        return self._message


def fake_message(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class FakeAnthropic:
    """Mimics ``client.messages.stream`` and ``client.beta.messages.stream``; returns queued responses in order."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, str):
            item = fake_message(item)
        return _Stream(item)


def write_text_pdf(path: Path, pages: list[str]) -> Path:
    """A real, text-layer PDF built with ReportLab."""
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    for text in pages:
        y = 540
        for line in text.splitlines():
            c.setFont("Helvetica", 16)
            c.drawString(50, y, line)
            y -= 26
        c.showPage()
    c.save()
    return path
