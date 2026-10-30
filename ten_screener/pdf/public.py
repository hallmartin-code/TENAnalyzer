"""Public-version redaction: a separate copy of the report with sensitive deal information removed.

Removed: investor names, committed capital, lead investor, cash, burn, runway,
valuation/cap, verbatim deck excerpts and analyst-supplied context. Free text
written by the model is scrubbed at sentence level: investor names are replaced,
and any sentence quoting a removed amount is dropped. The result is best-effort
and labeled for review before sharing.
"""

from __future__ import annotations

import re

from ten_screener.schemas import ScreeningReport


def _amount_variants(amount: float | None) -> set[str]:
    if amount is None or amount == 0:
        return set()
    variants = {f"{amount:,.0f}", f"{amount:.0f}"}
    for divisor, short, long in ((1e9, "B", "billion"), (1e6, "M", "million"), (1e3, "K", "thousand")):
        if amount >= divisor:
            v = amount / divisor
            for text in {f"{v:.1f}".rstrip("0").rstrip("."), f"{v:.2f}".rstrip("0").rstrip(".")}:
                variants |= {f"{text}{short}", f"{text} {long}", f"{text}{short.lower()}"}
            break
    return {v for v in variants if len(v) >= 2}


def _scrub(text: str, names: list[str], amounts: set[str]) -> str:
    if not text:
        return text
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(re.escape(name), "an investor", text, flags=re.IGNORECASE)
    if not amounts:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not any(a.lower() in s.lower() for a in amounts)]
    return " ".join(kept) if kept else "[Details withheld in public version.]"


def redact(report: ScreeningReport) -> ScreeningReport:
    r = report.model_copy(deep=True)
    ledger = r.ledger
    names = sorted({i for e in ledger.funding_events for i in e.investors if len(i.strip()) > 2}
                   | ({ledger.current_raise.lead_investor} if ledger.current_raise.lead_investor else set()))
    amounts: set[str] = set()
    for value in (ledger.current_raise.committed_amount, ledger.financials.cash_on_hand,
                  ledger.financials.monthly_burn, ledger.current_raise.valuation_or_cap):
        amounts |= _amount_variants(value)
    if r.runway.months is not None:  # runway is derived from cash and burn, so it is withheld too
        amounts |= {f"{r.runway.months:g} month", f"{r.runway.months:g}-month"}

    for event in ledger.funding_events:
        event.investors = []
    ledger.current_raise.lead_investor = None
    ledger.current_raise.committed_amount = None
    ledger.current_raise.valuation_or_cap = None
    if ledger.current_raise.instrument:
        ledger.current_raise.instrument = _scrub(ledger.current_raise.instrument, names, amounts)
    ledger.financials.cash_on_hand = None
    ledger.financials.monthly_burn = None
    ledger.financials.stated_runway_months = None
    r.runway = r.runway.model_copy(update={"months": None, "below_six_months": None, "basis": "Withheld in public version."})
    r.user_context = None
    for item in ledger.evidence:
        for src in item.sources:
            src.excerpt = ""
        item.claim = _scrub(item.claim, names, amounts)
        item.value = _scrub(item.value, names, amounts) if item.value else item.value

    a = r.assessment
    a.investor_verdict = _scrub(a.investor_verdict, names, amounts)
    a.business_description = _scrub(a.business_description, names, amounts)
    a.fundraising_actions = [_scrub(x, names, amounts) for x in a.fundraising_actions]
    for point in a.company_strengths + a.company_concerns:
        point.headline = _scrub(point.headline, names, amounts)
        point.detail = _scrub(point.detail, names, amounts)
    for cat in r.scoring.categories:
        cat.short_justification = _scrub(cat.short_justification, names, amounts)
        cat.justification = _scrub(cat.justification, names, amounts)
    r.sensitivity = r.sensitivity.model_copy(update={"confidential": False, "reasons": ["Public version: sensitive details removed"]})
    return r
