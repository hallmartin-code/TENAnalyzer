"""Display-ready lines derived from a report, shared by the PDFs and the interface.

Everything here reads validated, verified data; unknowns render as "Not disclosed".
"""

from __future__ import annotations

from ten_screener.evidence import supported
from ten_screener.rules import fmt_money
from ten_screener.schemas import NOT_DISCLOSED, EvidenceStatus, ScreeningReport

NATURE_LABELS = {
    "actual": "actual",
    "projected": "projected",
    "bookings": "bookings, not recognized revenue",
    "pilot": "pilot",
    "paid_pilot": "paid pilot",
    "unclear": "basis unclear",
}

SHORT_CATEGORY_NAMES = {
    "stage_gate_fit": "Stage Gate Fit",
    "team": "Team",
    "market_growth": "Market & Growth",
    "differentiation": "Differentiation",
    "financials": "Financials & Efficiency",
    "deal_terms": "Deal Terms & History",
    "exit_potential": "Exit Potential",
    "pitch_deck": "Pitch Deck",
}


def clip(text: str | None, words: int) -> str:
    """Shorten to at most ``words`` words: at a sentence end when one falls late enough, else at a word boundary."""
    if not text:
        return ""
    parts = " ".join(str(text).split()).split(" ")
    if len(parts) <= words:
        return " ".join(parts)
    for end in range(words, max(words // 2, 1) - 1, -1):
        if parts[end - 1].endswith((".", "!", "?")) and not parts[end - 1][:-1].replace(",", "").replace("$", "").isdigit():
            return " ".join(parts[:end])
    out = " ".join(parts[:words]).rstrip(",;:-–—")
    return out + "…"


def snapshot_title(report: ScreeningReport) -> str:
    return "Regulatory snapshot" if report.gate.track == "B" else "Traction snapshot"


def track_snapshot(report: ScreeningReport) -> list[str]:
    ledger = report.ledger
    lines: list[str] = []
    if report.gate.track == "B" and ledger.track_b:
        b = ledger.track_b
        basis = {
            "management_proposal": "management proposal",
            "regulatory_feedback": "supported by regulatory feedback",
            "authorization_obtained": "authorization disclosed",
            "unknown": "basis not stated",
        }[b.pathway_basis]
        pathway = f"{b.pathway} ({b.jurisdiction or 'jurisdiction not stated'}; {basis})" if b.pathway else NOT_DISCLOSED
        lines.append(f"Pathway: {pathway}")
        if b.authorization_status:
            lines.append(f"Authorization status: {b.authorization_status}")
        validation = "; ".join(filter(None, [b.clinical_completed, b.preclinical_completed])) or NOT_DISCLOSED
        lines.append(f"Validation: {validation}")
        lines.append(f"Next milestone: {b.next_regulatory_milestone or NOT_DISCLOSED}")
        if b.time_to_authorization or b.cost_to_authorization:
            lines.append(f"Time / cost to authorization: {b.time_to_authorization or NOT_DISCLOSED} / {b.cost_to_authorization or NOT_DISCLOSED}")
        lines.append(f"Reimbursement: {b.reimbursement or NOT_DISCLOSED}")
        return lines

    a = ledger.track_a
    if a is None:
        return ["Commercial traction: " + NOT_DISCLOSED]
    shown = 0
    for r in a.revenue:
        if not supported(ledger, r.evidence_ids) or shown >= 2:
            continue
        period = f", {r.period}" if r.period else ""
        lines.append(f"{r.metric}: {fmt_money(r.amount, r.currency)} ({NATURE_LABELS[r.nature]}{period})")
        shown += 1
    if not shown:
        lines.append("Revenue: " + ("pre-revenue (stated)" if a.states_pre_revenue else NOT_DISCLOSED))
    customers = a.paying_customers if a.paying_customers is not None and supported(ledger, a.paying_customers_evidence_ids) else None
    lines.append(f"Paying customers: {customers if customers is not None else NOT_DISCLOSED}")
    if a.customers_are_pilots_only:
        lines.append("Customer activity: pilots only")
    lines.append(f"Revenue growth: {a.revenue_growth or NOT_DISCLOSED}")
    if a.customer_concentration:
        lines.append(f"Concentration: {a.customer_concentration}")
    return lines


def capital_lines(report: ScreeningReport, *, public: bool = False) -> list[tuple[str, str]]:
    cap, raise_, fin = report.capital, report.ledger.current_raise, report.ledger.financials
    basis = {
        "stated_cumulative": "stated in deck",
        "sum_of_rounds": "sum of disclosed rounds",
        "not_disclosed": "",
        "mixed_currency": "multiple currencies; not summed",
    }[cap.total_basis]
    raised = fmt_money(cap.total_raised, cap.currency) if cap.total_raised is not None else NOT_DISCLOSED
    if cap.total_basis == "mixed_currency":
        raised = "See full report"
    lines = [("Raised to date", raised + (f" ({basis})" if basis and cap.total_raised is not None else ""))]

    ask = fmt_money(raise_.target_amount, raise_.currency) if raise_.target_amount is not None else NOT_DISCLOSED
    lines.append(("Current ask", ask))
    terms = raise_.instrument or NOT_DISCLOSED
    if not public and raise_.valuation_or_cap is not None and fmt_money(raise_.valuation_or_cap, raise_.currency) not in terms:
        label = {"pre_money": "pre-money", "post_money": "post-money", "cap": "cap", "unclear": "valuation"}[raise_.valuation_basis]
        terms += f"; {fmt_money(raise_.valuation_or_cap, raise_.currency)} {label}"
    lines.append(("Terms", terms))
    if not public:
        committed = fmt_money(raise_.committed_amount, raise_.currency) if raise_.committed_amount is not None else NOT_DISCLOSED
        lines.append(("Committed / lead", f"{committed} / {raise_.lead_investor or 'no lead named'}"))
        burn = f"{fmt_money(fin.monthly_burn, fin.currency)}/mo" if fin.monthly_burn is not None else NOT_DISCLOSED
        runway = f"{report.runway.months:g} months" if report.runway.months is not None else "not calculable"
        if report.runway.below_six_months:
            runway += " - BELOW 6 MONTHS"
        lines.append(("Burn / runway", f"{burn} / {runway}"))
    return lines


_TOPIC_PRIORITY = ["revenue", "customers", "regulatory", "clinical", "current_raise", "funding", "financials", "team", "market", "ip", "traction"]


def key_evidence(report: ScreeningReport, limit: int) -> list[str]:
    """Material, verified evidence with page references, most decision-relevant topics first."""
    items = [
        e for e in report.ledger.evidence
        if e.is_supported and e.status in (EvidenceStatus.DISCLOSED, EvidenceStatus.CALCULATED, EvidenceStatus.CONTRADICTORY)
    ]
    items.sort(key=lambda e: _TOPIC_PRIORITY.index(e.topic) if e.topic in _TOPIC_PRIORITY else 99)
    out: list[str] = []
    used_topics: set[str] = set()
    for item in items:
        if item.topic in used_topics and len(items) > limit:
            continue
        ref = report.cite([item.id], limit=2)
        if not ref:
            continue
        label = f"{item.claim}: {item.value}" if item.value else item.claim
        if "withheld" in label.lower():
            continue
        prefix = "CONTRADICTORY: " if item.status == EvidenceStatus.CONTRADICTORY else ""
        out.append(f"{prefix}{clip(label, 10)} ({ref})")
        used_topics.add(item.topic)
        if len(out) >= limit:
            break
    return out
