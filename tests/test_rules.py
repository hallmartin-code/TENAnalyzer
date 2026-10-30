"""Stage gate, funding double-counting, unknown-vs-zero, runway, instrument flags, readiness."""

from __future__ import annotations

import copy

import pytest

from ten_screener.evidence import verify_ledger
from ten_screener.rules import (
    calculate_runway,
    evaluate_stage_gate,
    fmt_money,
    instrument_flags,
    readiness,
    sensitivity,
    summarise_capital,
)
from ten_screener.schemas import GateStatus, LedgerOutput

from synthetic import TRACK_A_LEDGER, TRACK_B_LEDGER, track_a_extraction, track_b_extraction


def ledger_a(**track_a_overrides) -> LedgerOutput:
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["track_a"].update(track_a_overrides)
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    return ledger


def ledger_b(**track_b_overrides) -> LedgerOutput:
    data = copy.deepcopy(TRACK_B_LEDGER)
    data["track_b"].update(track_b_overrides)
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_b_extraction())
    return ledger


# --- Track A -----------------------------------------------------------------
def test_track_a_actual_revenue_and_customers_meets():
    result = evaluate_stage_gate(ledger_a())
    assert result.status == GateStatus.MEETS


def test_track_a_paid_pilots_only_does_not_meet():
    ledger = ledger_a(
        revenue=[{"metric": "Pilot revenue", "amount": 150000, "nature": "paid_pilot", "evidence_ids": ["E2"]}],
        paying_customers=None, paying_customers_evidence_ids=[],
        customers_are_pilots_only=True, commercial_sales_beyond_pilots=False,
    )
    result = evaluate_stage_gate(ledger)
    assert result.status == GateStatus.DOES_NOT_MEET
    assert "paid pilots" in result.reasons[0]


def test_track_a_paid_pilot_revenue_without_flag_still_fails():
    ledger = ledger_a(
        revenue=[{"metric": "Paid pilots", "amount": 90000, "nature": "paid_pilot", "evidence_ids": ["E2"]}],
        paying_customers=None, paying_customers_evidence_ids=[], customers_are_pilots_only=None,
        commercial_sales_beyond_pilots=None,
    )
    assert evaluate_stage_gate(ledger).status == GateStatus.DOES_NOT_MEET


def test_track_a_revenue_without_customer_count_is_partial():
    ledger = ledger_a(paying_customers=None, paying_customers_evidence_ids=[])
    assert evaluate_stage_gate(ledger).status == GateStatus.PARTIAL


def test_track_a_unknown_customers_is_not_zero():
    """None means not disclosed: it must never be treated as zero customers (which fails the gate)."""
    ledger = ledger_a(revenue=[], paying_customers=None, paying_customers_evidence_ids=[])
    result = evaluate_stage_gate(ledger)
    assert result.status == GateStatus.CANNOT_DETERMINE


def test_track_a_disclosed_zero_customers_fails():
    ledger = ledger_a(revenue=[], paying_customers=0)
    assert evaluate_stage_gate(ledger).status == GateStatus.DOES_NOT_MEET


def test_track_a_stated_pre_revenue_fails():
    ledger = ledger_a(revenue=[], paying_customers=None, paying_customers_evidence_ids=[], states_pre_revenue=True)
    assert evaluate_stage_gate(ledger).status == GateStatus.DOES_NOT_MEET


def test_track_a_projection_only_cannot_determine():
    ledger = ledger_a(
        revenue=[{"metric": "Revenue", "amount": 9000000, "period": "2028", "nature": "projected", "evidence_ids": ["E12"]}],
        paying_customers=None, paying_customers_evidence_ids=[],
    )
    result = evaluate_stage_gate(ledger)
    assert result.status == GateStatus.CANNOT_DETERMINE
    assert "projected" in result.reasons[0]


def test_track_a_unverified_revenue_not_counted():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["evidence"][1]["sources"] = [{"page": 3, "kind": "slide_text", "excerpt": "$5.0M ARR with 400 enterprise logos"}]
    data["evidence"][2]["sources"] = [{"page": 3, "kind": "slide_text", "excerpt": "four hundred paying enterprise customers"}]
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    assert evaluate_stage_gate(ledger).status == GateStatus.CANNOT_DETERMINE


def test_track_undetermined_cannot_determine():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["track"] = {"track": "undetermined", "rationale": "Unclear whether the product needs FDA clearance."}
    ledger = LedgerOutput.model_validate(data)
    result = evaluate_stage_gate(ledger)
    assert result.status == GateStatus.CANNOT_DETERMINE and result.track_label == "Track Undetermined"


# --- Track B -----------------------------------------------------------------
def test_track_b_pathway_without_preclinical_meets():
    ledger = ledger_b()
    assert ledger.track_b.preclinical_completed is None
    result = evaluate_stage_gate(ledger)
    assert result.status == GateStatus.MEETS
    assert "management's proposal" in result.reasons[0]


def test_track_b_no_pathway_cannot_determine():
    result = evaluate_stage_gate(ledger_b(pathway=None, pathway_evidence_ids=[]))
    assert result.status == GateStatus.CANNOT_DETERMINE


def test_track_b_pathway_stated_undetermined_fails():
    result = evaluate_stage_gate(ledger_b(pathway=None, pathway_evidence_ids=[], states_pathway_undetermined=True))
    assert result.status == GateStatus.DOES_NOT_MEET


def test_track_b_missing_jurisdiction_partial():
    assert evaluate_stage_gate(ledger_b(jurisdiction=None)).status == GateStatus.PARTIAL


def test_track_b_questionable_pathway_partial():
    assert evaluate_stage_gate(ledger_b(pathway_appropriate="questionable")).status == GateStatus.PARTIAL


# --- Capital -----------------------------------------------------------------
def test_cumulative_total_not_added_and_duplicates_merged():
    summary = summarise_capital(ledger_a())
    assert summary.total_raised == pytest.approx(2_600_000)  # not 2.6M + 2.0M + 2.0M + 0.6M
    assert summary.total_basis == "stated_cumulative"
    assert len(summary.counted_events) == 2
    assert summary.duplicates_removed and "Seed round" in summary.duplicates_removed[0]
    assert summary.by_category == {"Convertible (SAFE/note/KISS)": 2_000_000, "Grants & non-dilutive": 600_000}
    merged = next(e for e in summary.counted_events if e.instrument == "safe")
    assert merged.investors == ["Example Ventures"]


def test_sum_of_rounds_when_no_cumulative_statement():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["funding_events"] = [e for e in data["funding_events"] if not e.get("is_cumulative_total")]
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    summary = summarise_capital(ledger)
    assert summary.total_raised == pytest.approx(2_600_000) and summary.total_basis == "sum_of_rounds"


def test_rounds_exceeding_cumulative_flagged_as_contradictory():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["funding_events"][3]["amount"] = 1_600_000  # grant now makes itemised 3.6M > stated 2.6M
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    summary = summarise_capital(ledger)
    assert summary.total_raised == pytest.approx(2_600_000)
    assert any("contradictory" in n for n in summary.notes)


def test_no_funding_is_not_disclosed_not_zero():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["funding_events"] = []
    summary = summarise_capital(LedgerOutput.model_validate(data))
    assert summary.total_raised is None and summary.total_basis == "not_disclosed"
    assert fmt_money(summary.total_raised) == "Not disclosed"


def test_mixed_currencies_not_summed():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["funding_events"] = [e for e in data["funding_events"] if not e.get("is_cumulative_total")]
    data["funding_events"][2]["currency"] = "EUR"
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    summary = summarise_capital(ledger)
    assert summary.total_raised is None and summary.total_basis == "mixed_currency"


# --- Runway, instruments, readiness ------------------------------------------
def test_runway_calculated_from_disclosed_inputs():
    runway = calculate_runway(ledger_a())
    assert runway.months == pytest.approx(7.3)
    assert runway.below_six_months is False
    assert "$1.1M" in runway.basis and "$150K" in runway.basis


def test_runway_unknown_burn_is_not_zero():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["financials"]["monthly_burn"] = None
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    runway = calculate_runway(ledger)
    assert runway.months is None and runway.below_six_months is None
    assert "monthly burn not disclosed" in runway.basis


def test_runway_zero_burn_not_calculable():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["financials"]["monthly_burn"] = 0
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    assert calculate_runway(ledger).months is None


def test_runway_below_six_months_flagged():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["financials"]["monthly_burn"] = 250_000
    ledger = LedgerOutput.model_validate(data)
    verify_ledger(ledger, track_a_extraction())
    runway = calculate_runway(ledger)
    assert runway.months == pytest.approx(4.4) and runway.below_six_months is True


@pytest.mark.parametrize("instrument,category,cap,expected", [
    ("uncapped SAFE with 20% discount", "safe", None, "Uncapped convertible"),
    ("SAFE", "safe", None, "Cap not disclosed"),
    ("KISS (convertible debt version)", "kiss", 8_000_000, "KISS agreement"),
    ("custom SAFE with side letter", "safe", 10_000_000, "Custom SAFE terms"),
    ("pre-money SAFE, $6M cap", "safe", 6_000_000, "Pre-money SAFE stacking"),
])
def test_instrument_flags(instrument, category, cap, expected):
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["current_raise"].update(instrument=instrument, instrument_category=category, valuation_or_cap=cap)
    flags = [f.flag for f in instrument_flags(LedgerOutput.model_validate(data))]
    assert expected in flags


def test_standard_post_money_safe_not_flagged():
    assert instrument_flags(ledger_a()) == []


def test_pre_seed_safe_label_not_mistaken_for_pre_money():
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["funding_events"].append({"label": "Pre-seed SAFE", "amount": 250000, "instrument": "safe", "evidence_ids": ["E6"]})
    flags = [f.flag for f in instrument_flags(LedgerOutput.model_validate(data))]
    assert "Pre-money SAFE stacking" not in flags


def test_readiness_counts_only_verified_items_and_has_floor():
    result = readiness(ledger_a())
    assert result.score == 8
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["readiness"] = []
    assert readiness(LedgerOutput.model_validate(data)).score == 1


def test_sensitivity_flags_investors_and_committed_capital():
    flags = sensitivity(ledger_a())
    assert flags.confidential
    assert "Names investors" in flags.reasons and "Discloses committed capital" in flags.reasons


@pytest.mark.parametrize("amount,text", [(None, "Not disclosed"), (0, "$0"), (1_200_000, "$1.2M"), (600_000, "$600K"), (2_500_000_000, "$2.5B")])
def test_fmt_money(amount, text):
    assert fmt_money(amount) == text
