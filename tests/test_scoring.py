"""Weighted scoring, band boundaries, incomplete scoring and eligibility overrides."""

from __future__ import annotations

import pytest

from ten_screener.schemas import AssessmentOutput, GateResult, GateStatus
from ten_screener.scoring import WEIGHTS, band_for, score, weighted_points

from synthetic import TRACK_A_ASSESSMENT

KEYS = list(WEIGHTS)


def gate(status: GateStatus, track: str = "A") -> GateResult:
    return GateResult(track=track, track_label="Track A - Non-life-science", status=status, reasons=["test"])


def assessment(scores: dict[str, int | None]) -> AssessmentOutput:
    data = dict(TRACK_A_ASSESSMENT)
    data["category_assessments"] = [
        {"category": k, "score": scores.get(k), "justification": f"{k} justification", "short_justification": k}
        for k in KEYS
    ]
    return AssessmentOutput.model_validate(data)


def uniform(value: int | None) -> dict[str, int | None]:
    return {k: value for k in KEYS}


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100
    assert WEIGHTS == {"stage_gate_fit": 20, "team": 15, "market_growth": 15, "differentiation": 15,
                       "financials": 10, "deal_terms": 10, "exit_potential": 10, "pitch_deck": 5}


def test_weighted_total_formula():
    scores = {"stage_gate_fit": 9, "team": 7, "market_growth": 6, "differentiation": 5,
              "financials": 7, "deal_terms": 7, "exit_potential": 6, "pitch_deck": 6}
    points, assessed = weighted_points(scores)
    expected = 0.9 * 20 + 0.7 * 15 + 0.6 * 15 + 0.5 * 15 + 0.7 * 10 + 0.7 * 10 + 0.6 * 10 + 0.6 * 5
    assert points == pytest.approx(expected) == pytest.approx(68.0)
    assert assessed == 100


@pytest.mark.parametrize("value,expected", [(10, 100.0), (1, 10.0), (5, 50.0)])
def test_uniform_extremes(value, expected):
    assert weighted_points(uniform(value))[0] == pytest.approx(expected)


@pytest.mark.parametrize("total,band", [
    (100, "Strong Fit"), (80.0, "Strong Fit"), (79.99, "Moderate Fit"), (65.0, "Moderate Fit"),
    (64.99, "Weak Fit"), (50.0, "Weak Fit"), (49.99, "Likely Pass"), (10.0, "Likely Pass"),
])
def test_band_boundaries(total, band):
    assert band_for(total) == band


def test_band_applied_before_rounding():
    # 79.95 would display as "80.0" when rounded to one decimal, but must stay Moderate.
    assert band_for(79.95) == "Moderate Fit"
    assert f"{79.95:.0f}" == "80"


def test_out_of_range_score_rejected():
    with pytest.raises(ValueError):
        weighted_points({"team": 11})


def test_complete_scoring_meets_gate_no_override():
    result = score(assessment(uniform(9)), gate(GateStatus.MEETS), exclusion_confirmed=False)
    assert result.complete and result.total == pytest.approx(90.0)
    assert result.underlying_band == "Strong Fit" and result.effective_rating == "Strong Fit"
    assert result.override_applied is None


def test_failed_stage_gate_caps_strong_at_weak():
    scores = uniform(10)
    scores["stage_gate_fit"] = 2
    result = score(assessment(scores), gate(GateStatus.DOES_NOT_MEET), exclusion_confirmed=False)
    assert result.total == pytest.approx(0.2 * 20 + 1.0 * 80)  # 84.0
    assert result.underlying_band == "Strong Fit"
    assert result.effective_rating == "Weak Fit"
    assert "capped" in (result.override_applied or "").lower()


def test_failed_stage_gate_underlying_computed_separately():
    scores = uniform(9)
    result = score(assessment(scores), gate(GateStatus.DOES_NOT_MEET), exclusion_confirmed=False)
    # Stage Gate Fit is clamped to 1-3 for a failed gate: 9 -> 3.
    gate_cat = next(c for c in result.categories if c.key == "stage_gate_fit")
    assert gate_cat.score == 3 and "Adjusted from 9 to 3" in gate_cat.adjustment_note
    assert result.total == pytest.approx(0.3 * 20 + 0.9 * 80)  # 78.0 -> Moderate underlying
    assert result.underlying_band == "Moderate Fit"
    assert result.effective_rating == "Weak Fit"


def test_failed_gate_keeps_likely_pass():
    result = score(assessment(uniform(2)), gate(GateStatus.DOES_NOT_MEET), exclusion_confirmed=False)
    assert result.underlying_band == "Likely Pass"
    assert result.effective_rating == "Likely Pass"


def test_confirmed_exclusion_caps_rating():
    result = score(assessment(uniform(9)), gate(GateStatus.MEETS), exclusion_confirmed=True)
    assert result.underlying_band == "Strong Fit"
    assert result.effective_rating == "Weak Fit"
    assert "exclusion" in result.override_applied


@pytest.mark.parametrize("status", [GateStatus.PARTIAL, GateStatus.CANNOT_DETERMINE])
def test_partial_or_undetermined_gate_is_pending(status):
    result = score(assessment(uniform(9)), gate(status), exclusion_confirmed=False)
    assert result.effective_rating == "Pending stage verification"
    assert result.effective_rating not in ("Strong Fit", "Moderate Fit")


def test_partial_gate_clamps_stage_gate_score():
    result = score(assessment(uniform(9)), gate(GateStatus.PARTIAL), exclusion_confirmed=False)
    gate_cat = next(c for c in result.categories if c.key == "stage_gate_fit")
    assert gate_cat.score == 6
    assert result.underlying_band == "Strong Fit"  # 0.6*20 + 0.9*80 = 84; displayed separately from the override
    assert result.effective_rating == "Pending stage verification"


def test_cannot_determine_gate_makes_stage_gate_not_assessable():
    result = score(assessment(uniform(8)), gate(GateStatus.CANNOT_DETERMINE), exclusion_confirmed=False)
    gate_cat = next(c for c in result.categories if c.key == "stage_gate_fit")
    assert gate_cat.score is None
    assert not result.complete and result.total is None and result.underlying_band is None


def test_missing_evidence_withholds_band_and_reports_range():
    scores = uniform(7)
    scores["exit_potential"] = None  # 10%
    scores["pitch_deck"] = None  # 5%
    result = score(assessment(scores), gate(GateStatus.MEETS), exclusion_confirmed=False)
    assert not result.complete
    assert result.total is None and result.underlying_band is None
    assert result.assessed_weight == 85
    assert result.supported_points == pytest.approx(0.7 * 85)
    assert result.possible_min == pytest.approx(0.7 * 85 + 1.5)  # missing categories at score 1
    assert result.possible_max == pytest.approx(0.7 * 85 + 15)  # missing categories at score 10
    assert result.effective_rating.startswith("Withheld")
    # Weight is not redistributed: supported points are not rescaled to 100.
    assert result.supported_points < 70


def test_missing_category_entry_counts_as_not_assessable():
    a = assessment(uniform(7))
    a.category_assessments = [c for c in a.category_assessments if c.category != "team"]
    result = score(a, gate(GateStatus.MEETS), exclusion_confirmed=False)
    assert not result.complete
    assert next(c for c in result.categories if c.key == "team").score is None


def test_failed_gate_with_incomplete_scoring_still_capped():
    scores = uniform(9)
    scores["pitch_deck"] = None
    result = score(assessment(scores), gate(GateStatus.DOES_NOT_MEET), exclusion_confirmed=False)
    assert result.effective_rating == "Weak Fit or below (capped)"
