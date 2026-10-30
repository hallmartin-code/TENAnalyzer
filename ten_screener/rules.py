"""Deterministic eligibility rules and derived figures.

Claude proposes facts; these functions decide. Every rule only counts a fact
whose evidence survived citation verification, and treats ``None`` as unknown -
never as zero.

Stage-gate principle: a gate *fails* only on affirmative evidence of failure
(the deck says it is pre-revenue, only pilots are evidenced, the pathway is
stated to be undetermined, zero paying customers is disclosed). Silence is
"Cannot Determine", which still blocks a Strong/Moderate recommendation.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ten_screener.evidence import supported
from ten_screener.schemas import (
    READINESS_RUBRIC,
    CapitalSummary,
    FundingEvent,
    GateResult,
    GateStatus,
    InstrumentFlag,
    LedgerOutput,
    ReadinessItem,
    ReadinessResult,
    RunwayResult,
    SensitivityFlags,
)

TRACK_LABELS = {
    "A": "Track A - Non-life-science",
    "B": "Track B - Life science",
    "undetermined": "Track Undetermined",
}

CATEGORY_GROUPS = {
    "equity": "Equity",
    "safe": "Convertible (SAFE/note/KISS)",
    "convertible_note": "Convertible (SAFE/note/KISS)",
    "kiss": "Convertible (SAFE/note/KISS)",
    "debt": "Debt",
    "grant": "Grants & non-dilutive",
    "non_dilutive_other": "Grants & non-dilutive",
    "unknown": "Instrument not disclosed",
}


# ---------------------------------------------------------------------------
# Stage gate
# ---------------------------------------------------------------------------
def evaluate_stage_gate(ledger: LedgerOutput) -> GateResult:
    track = ledger.track.track
    if track == "A":
        status, reasons, ids = _gate_track_a(ledger)
    elif track == "B":
        status, reasons, ids = _gate_track_b(ledger)
    else:
        status = GateStatus.CANNOT_DETERMINE
        reasons = [f"Track could not be determined: {ledger.track.rationale}"]
        ids = list(ledger.track.evidence_ids)
    return GateResult(track=track, track_label=TRACK_LABELS[track], status=status, reasons=reasons, evidence_ids=ids)


def _gate_track_a(ledger: LedgerOutput) -> tuple[GateStatus, list[str], list[str]]:
    facts = ledger.track_a
    if facts is None:
        return GateStatus.CANNOT_DETERMINE, ["No commercial traction facts were extracted."], []

    def ok(ids: list[str]) -> bool:
        return supported(ledger, ids)

    actual = [r for r in facts.revenue if r.nature == "actual" and r.amount is not None and r.amount > 0 and ok(r.evidence_ids)]
    pilot = [r for r in facts.revenue if r.nature in ("pilot", "paid_pilot") and ok(r.evidence_ids)]
    forward = [r for r in facts.revenue if r.nature in ("projected", "bookings") and ok(r.evidence_ids)]
    customers_known = facts.paying_customers is not None and ok(facts.paying_customers_evidence_ids)
    ids = [i for r in actual + pilot + forward for i in r.evidence_ids] + facts.paying_customers_evidence_ids

    if facts.states_pre_revenue and not actual:
        return GateStatus.DOES_NOT_MEET, ["The deck describes the company as pre-revenue; no actual commercial revenue is evidenced."], ids
    if customers_known and facts.paying_customers == 0:
        return GateStatus.DOES_NOT_MEET, ["The deck discloses zero paying customers."], ids
    if not actual and (facts.customers_are_pilots_only or pilot) and facts.commercial_sales_beyond_pilots is not True:
        return GateStatus.DOES_NOT_MEET, [
            "Only pilot activity is evidenced. Pilots, including paid pilots, do not satisfy the Track A gate."
        ], ids
    if actual:
        if facts.customers_are_pilots_only or facts.commercial_sales_beyond_pilots is False:
            return GateStatus.PARTIAL, [
                "Revenue is disclosed, but the evidence suggests it comes from pilots rather than commercial sales."
            ], ids
        if customers_known and facts.paying_customers and facts.paying_customers > 0:
            metric = actual[0]
            return GateStatus.MEETS, [
                f"Actual revenue disclosed ({metric.metric}{', ' + metric.period if metric.period else ''}) "
                f"with {facts.paying_customers} paying customer(s)."
            ], ids
        return GateStatus.PARTIAL, [
            "Actual revenue is disclosed, but the number of paying commercial customers is not evidenced."
        ], ids
    if customers_known and facts.paying_customers and facts.paying_customers > 0:
        return GateStatus.PARTIAL, [
            f"{facts.paying_customers} paying customer(s) disclosed, but no actual revenue figure is evidenced."
        ], ids
    if forward:
        return GateStatus.CANNOT_DETERMINE, [
            "Only projected revenue or bookings are disclosed; actual recognized revenue is not evidenced."
        ], ids
    return GateStatus.CANNOT_DETERMINE, ["Revenue and paying-customer information is not disclosed."], ids


def _gate_track_b(ledger: LedgerOutput) -> tuple[GateStatus, list[str], list[str]]:
    facts = ledger.track_b
    if facts is None:
        return GateStatus.CANNOT_DETERMINE, ["No regulatory facts were extracted."], []
    ids = list(facts.pathway_evidence_ids)
    pathway_ok = bool(facts.pathway) and supported(ledger, facts.pathway_evidence_ids)

    if facts.product_type == "digital_health_unregulated":
        return GateStatus.CANNOT_DETERMINE, [
            "The product appears not to require regulatory clearance; Track B classification should be revisited."
        ], ids
    if not pathway_ok:
        if facts.states_pathway_undetermined:
            return GateStatus.DOES_NOT_MEET, ["The deck states the regulatory pathway has not yet been determined."], ids
        if facts.pathway:
            return GateStatus.CANNOT_DETERMINE, [
                f"A pathway ('{facts.pathway}') was mentioned but could not be confirmed against the deck text."
            ], ids
        return GateStatus.CANNOT_DETERMINE, ["No regulatory pathway is disclosed."], ids

    basis = {
        "management_proposal": "management's proposal; no regulatory feedback is evidenced",
        "regulatory_feedback": "supported by disclosed regulatory feedback",
        "authorization_obtained": "authorization disclosed",
        "unknown": "basis not stated",
    }[facts.pathway_basis]
    where = facts.jurisdiction or "jurisdiction not stated"
    if facts.pathway_appropriate == "questionable":
        return GateStatus.PARTIAL, [
            f"Pathway stated ({facts.pathway}, {where}), but its fit to the product is questionable: "
            f"{facts.pathway_rationale or 'see analysis'}."
        ], ids
    if not facts.jurisdiction:
        return GateStatus.PARTIAL, [f"Pathway stated ({facts.pathway}) but the target jurisdiction is not identified."], ids
    if facts.pathway_appropriate == "unclear":
        return GateStatus.PARTIAL, [
            f"Pathway stated ({facts.pathway}, {where}); its appropriateness for the product cannot be confirmed from the deck."
        ], ids
    return GateStatus.MEETS, [f"Defined regulatory pathway: {facts.pathway} ({where}) - {basis}."], ids


# ---------------------------------------------------------------------------
# Capital history
# ---------------------------------------------------------------------------
def _norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).replace("round", "").strip()


def _same_amount(a: float, b: float) -> bool:
    return abs(a - b) <= 0.01 * max(abs(a), abs(b), 1.0)


def _is_duplicate(a: FundingEvent, b: FundingEvent) -> bool:
    if a.amount is None or b.amount is None or a.currency != b.currency or not _same_amount(a.amount, b.amount):
        return False
    if _norm_label(a.label) and _norm_label(a.label) == _norm_label(b.label):
        return True
    if a.date and b.date and a.date.strip().lower() == b.date.strip().lower():
        return True
    if a.instrument == b.instrument and (not a.date or not b.date):
        return True
    return False


def summarise_capital(ledger: LedgerOutput) -> CapitalSummary:
    events = [e for e in ledger.funding_events if supported(ledger, e.evidence_ids)]
    dropped = [e.label for e in ledger.funding_events if e not in events]
    cumulative = [e for e in events if e.is_cumulative_total]
    discrete: list[FundingEvent] = []
    duplicates: list[str] = []
    for event in (e for e in events if not e.is_cumulative_total):
        match = next((d for d in discrete if _is_duplicate(d, event)), None)
        if match is not None:
            duplicates.append(f"{event.label} (same as {match.label})")
            match.evidence_ids = sorted(set(match.evidence_ids) | set(event.evidence_ids))
            match.investors = sorted(set(match.investors) | set(event.investors))
            continue
        discrete.append(event.model_copy(deep=True))

    notes: list[str] = []
    if dropped:
        notes.append("Excluded funding claims whose citations could not be verified: " + ", ".join(dropped))
    undisclosed = [e.label for e in discrete if e.amount is None]
    with_amount = [e for e in discrete if e.amount is not None]
    currencies = {e.currency for e in with_amount} | {e.currency for e in cumulative if e.amount is not None}

    summary = CapitalSummary(
        counted_events=discrete,
        duplicates_removed=duplicates,
        cumulative_statements=cumulative,
        undisclosed_amount_events=undisclosed,
        notes=notes,
    )
    if len(currencies) > 1:
        summary.total_basis = "mixed_currency"
        summary.notes.append("Funding is disclosed in multiple currencies; amounts were not summed.")
        return summary
    currency = next(iter(currencies), "USD")
    summary.currency = currency
    by_category: dict[str, float] = defaultdict(float)
    for event in with_amount:
        by_category[CATEGORY_GROUPS[event.instrument]] += event.amount or 0.0
    summary.by_category = dict(by_category)
    rounds_total = sum(e.amount or 0.0 for e in with_amount)
    stated = max((e.amount for e in cumulative if e.amount is not None), default=None)

    if stated is not None:
        summary.total_raised = stated
        summary.total_basis = "stated_cumulative"
        if with_amount and rounds_total > stated * 1.01:
            summary.notes.append(
                f"Itemised rounds sum to {fmt_money(rounds_total, currency)}, more than the stated cumulative total "
                f"of {fmt_money(stated, currency)}. The figures are contradictory and need reconciliation."
            )
        elif with_amount and rounds_total < stated * 0.99:
            summary.notes.append(
                f"Itemised rounds account for {fmt_money(rounds_total, currency)} of the stated "
                f"{fmt_money(stated, currency)}; the remainder is not itemised."
            )
        summary.notes.append("Cumulative 'raised to date' statements are reported, not added to itemised rounds.")
    elif with_amount:
        summary.total_raised = rounds_total
        summary.total_basis = "sum_of_rounds"
        if undisclosed:
            summary.notes.append("Some rounds have no disclosed amount; the total is a lower bound.")
    if duplicates:
        summary.notes.append(f"{len(duplicates)} duplicate funding reference(s) were merged to avoid double-counting.")
    return summary


# ---------------------------------------------------------------------------
# Runway, instruments, readiness, exclusion, sensitivity
# ---------------------------------------------------------------------------
def calculate_runway(ledger: LedgerOutput) -> RunwayResult:
    fin = ledger.financials
    have_support = supported(ledger, fin.evidence_ids)
    if fin.cash_on_hand is None or fin.monthly_burn is None or not have_support:
        if fin.stated_runway_months is not None and have_support:
            months = fin.stated_runway_months
            return RunwayResult(months=months, basis=f"Stated in deck ({months:g} months); not independently calculated.", below_six_months=months < 6)
        missing = [n for n, v in (("cash on hand", fin.cash_on_hand), ("monthly burn", fin.monthly_burn)) if v is None]
        return RunwayResult(basis="Not calculable: " + (" and ".join(missing) + " not disclosed" if missing else "inputs not verified") + ".")
    if fin.monthly_burn <= 0:
        return RunwayResult(basis="Not calculable: disclosed burn is zero or negative (cash-flow positive or unclear).")
    months = fin.cash_on_hand / fin.monthly_burn
    basis = (
        f"Calculated: cash {fmt_money(fin.cash_on_hand, fin.currency)}"
        f"{' as of ' + fin.cash_as_of if fin.cash_as_of else ''} / monthly burn "
        f"{fmt_money(fin.monthly_burn, fin.currency)} = {months:.1f} months (excludes new raise)."
    )
    return RunwayResult(months=round(months, 1), basis=basis, below_six_months=months < 6)


def instrument_flags(ledger: LedgerOutput) -> list[InstrumentFlag]:
    raise_ = ledger.current_raise
    text = " ".join(filter(None, [raise_.instrument, raise_.discount, raise_.maturity])).lower()
    category = raise_.instrument_category
    flags: list[InstrumentFlag] = []
    is_convertible = category in ("safe", "convertible_note", "kiss") or any(k in text for k in ("safe", "note", "kiss", "convertible"))

    if re.search(r"\buncapped\b|\bno (valuation )?cap\b|\bwithout a cap\b", text):
        flags.append(InstrumentFlag(
            flag="Uncapped convertible",
            concern="With no valuation cap, early investors carry the full upside of a high priced round with no price protection; confirm discount and MFN terms.",
        ))
    elif is_convertible and raise_.valuation_or_cap is None and "cap" not in text:
        flags.append(InstrumentFlag(
            flag="Cap not disclosed",
            concern="The deck describes a convertible instrument without a valuation cap. This may be an omission rather than an uncapped instrument; request the term sheet.",
        ))
    if re.search(r"custom(ized)? safe|modified safe|non[- ]standard safe|side letter", text):
        flags.append(InstrumentFlag(
            flag="Custom SAFE terms",
            concern="Non-standard SAFE language can change conversion mechanics, pro-rata or MFN rights; legal review of the actual document is needed.",
        ))
    if category == "kiss" or re.search(r"\bkiss\b", text):
        flags.append(InstrumentFlag(
            flag="KISS agreement",
            concern="KISS instruments can carry interest, maturity conversion and major-investor rights that differ from SAFEs; confirm which KISS version and its maturity terms.",
        ))
    pre_money_safes = [
        e for e in ledger.funding_events
        if e.instrument == "safe" and re.search(r"pre[- ]money", (e.label or "").lower())
    ]
    if re.search(r"pre[- ]money safe", text) or (category == "safe" and pre_money_safes):
        flags.append(InstrumentFlag(
            flag="Pre-money SAFE stacking",
            concern="Multiple pre-money SAFEs dilute each other and the founders in ways that are hard to model before conversion; request a pro-forma cap table.",
        ))
    if category == "convertible_note" and raise_.maturity is None and "matur" not in text:
        flags.append(InstrumentFlag(flag="Note maturity not disclosed", concern="Maturity and interest terms determine repayment or conversion risk; request them."))
    return flags


def readiness(ledger: LedgerOutput) -> ReadinessResult:
    proposed = {item.key: item for item in ledger.readiness}
    items: list[ReadinessItem] = []
    for key, description in READINESS_RUBRIC.items():
        item = proposed.get(key)
        if item is None:
            items.append(ReadinessItem(key=key, met=False, note=f"{description}: not assessed / not evidenced."))
            continue
        met = item.met and supported(ledger, item.evidence_ids)
        note = item.note or description
        if item.met and not met:
            note += " (claimed, but citation could not be verified)"
        items.append(ReadinessItem(key=key, met=met, note=note, evidence_ids=item.evidence_ids))
    score = max(1, sum(1 for i in items if i.met))
    return ReadinessResult(
        score=score,
        items=items,
        rubric_note=(
            "Investor Readiness (1-10) measures fundraising preparation and documentation, not investability. "
            "One point for each of ten evidenced items: " + "; ".join(READINESS_RUBRIC.values()) + ". Minimum score 1."
        ),
    )


def exclusion_confirmed(ledger: LedgerOutput) -> bool:
    exc = ledger.exclusion
    return exc.status == "confirmed" and exc.category != "none" and supported(ledger, exc.evidence_ids)


def sensitivity(ledger: LedgerOutput) -> SensitivityFlags:
    reasons: list[str] = []
    investors = {i for e in ledger.funding_events for i in e.investors if i.strip()}
    if ledger.current_raise.lead_investor:
        investors.add(ledger.current_raise.lead_investor)
    if investors:
        reasons.append("Names investors")
    if ledger.current_raise.committed_amount is not None:
        reasons.append("Discloses committed capital")
    if ledger.financials.cash_on_hand is not None or ledger.financials.monthly_burn is not None:
        reasons.append("Discloses cash or burn")
    if ledger.current_raise.valuation_or_cap is not None:
        reasons.append("Discloses valuation or cap")
    return SensitivityFlags(confidential=bool(reasons), reasons=reasons)


def fmt_money(amount: float | None, currency: str = "USD") -> str:
    if amount is None:
        return "Not disclosed"
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
    suffix = "" if symbol else f" {currency.upper()}"
    value = abs(amount)
    sign = "-" if amount < 0 else ""
    if value >= 1_000_000_000:
        text = f"{value / 1_000_000_000:.2f}".rstrip("0").rstrip(".") + "B"
    elif value >= 1_000_000:
        text = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    elif value >= 1_000:
        text = f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    else:
        text = f"{value:,.0f}"
    return f"{sign}{symbol}{text}{suffix}"
