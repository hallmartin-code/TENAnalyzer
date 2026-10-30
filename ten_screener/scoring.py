"""Weighted investability scoring, fit bands and deterministic eligibility overrides.

Weighted total = sum(category score / 10 x category weight), out of 100.
Bands are applied to the unrounded total. A category without sufficient evidence
is "Not assessable": its weight is not redistributed, the total is reported as a
provisional supported-points figure with its possible range, and no final band
is issued until every category is assessable.
"""

from __future__ import annotations

from ten_screener.schemas import (
    AssessmentOutput,
    CategoryAssessment,
    CategoryScore,
    FitBand,
    GateResult,
    GateStatus,
    ScoreResult,
)

WEIGHTS: dict[str, int] = {
    "stage_gate_fit": 20,
    "team": 15,
    "market_growth": 15,
    "differentiation": 15,
    "financials": 10,
    "deal_terms": 10,
    "exit_potential": 10,
    "pitch_deck": 5,
}

NAMES: dict[str, str] = {
    "stage_gate_fit": "Stage Gate Fit",
    "team": "Team",
    "market_growth": "Market & Growth Potential",
    "differentiation": "Differentiation & Defensibility",
    "financials": "Financials & Capital Efficiency",
    "deal_terms": "Deal Terms & Capital History",
    "exit_potential": "Exit Potential",
    "pitch_deck": "Pitch Deck Quality",
}

SCORING_ANCHORS = "1-2 severe weakness; 3-4 weak; 5-6 mixed; 7-8 strong; 9-10 exceptional and well supported."

#: The Stage Gate Fit category score must agree with the deterministic gate result.
GATE_SCORE_BOUNDS: dict[GateStatus, tuple[int, int] | None] = {
    GateStatus.MEETS: (6, 10),
    GateStatus.PARTIAL: (3, 6),
    GateStatus.DOES_NOT_MEET: (1, 3),
    GateStatus.CANNOT_DETERMINE: None,  # insufficient evidence -> Not assessable
}

assert sum(WEIGHTS.values()) == 100


def band_for(total: float) -> FitBand:
    if total >= 80:
        return "Strong Fit"
    if total >= 65:
        return "Moderate Fit"
    if total >= 50:
        return "Weak Fit"
    return "Likely Pass"


def weighted_points(scores: dict[str, int | None]) -> tuple[float, int]:
    """Supported points and assessed weight for the categories that have a score."""
    points = 0.0
    assessed = 0
    for key, weight in WEIGHTS.items():
        score = scores.get(key)
        if score is None:
            continue
        if not 1 <= score <= 10:
            raise ValueError(f"Score for {key} must be between 1 and 10, got {score}")
        points += score / 10 * weight
        assessed += weight
    return points, assessed


def _gate_adjusted(assessment: CategoryAssessment | None, gate: GateResult) -> tuple[int | None, str | None]:
    bounds = GATE_SCORE_BOUNDS[gate.status]
    proposed = assessment.score if assessment else None
    if bounds is None:
        return None, "Not assessable: stage gate cannot be determined from the supplied materials."
    low, high = bounds
    if proposed is None:
        midpoint = (low + high) // 2
        return midpoint, f"Score set to {midpoint} from the deterministic gate result ({gate.status.value})."
    if proposed < low or proposed > high:
        clamped = min(max(proposed, low), high)
        return clamped, f"Adjusted from {proposed} to {clamped} to agree with the gate result ({gate.status.value})."
    return proposed, None


def score(assessment: AssessmentOutput, gate: GateResult, *, exclusion_confirmed: bool) -> ScoreResult:
    by_key = {c.category: c for c in assessment.category_assessments}
    categories: list[CategoryScore] = []
    scores: dict[str, int | None] = {}
    for key, weight in WEIGHTS.items():
        item = by_key.get(key)
        note = None
        if key == "stage_gate_fit":
            value, note = _gate_adjusted(item, gate)
        else:
            value = item.score if item else None
        scores[key] = value
        justification = item.justification if item else "Not assessed."
        if value is None and item is not None and item.score is None:
            justification = justification or "Not assessable: insufficient evidence."
        categories.append(
            CategoryScore(
                key=key,  # type: ignore[arg-type]
                name=NAMES[key],
                weight=weight,
                score=value,
                points=round(value / 10 * weight, 2) if value is not None else None,
                justification=justification,
                short_justification=(item.short_justification or item.justification) if item else "Not assessed.",
                adjustment_note=note,
                evidence_ids=item.evidence_ids if item else [],
            )
        )
    return finalise(categories, scores, gate, exclusion_confirmed=exclusion_confirmed)


def finalise(
    categories: list[CategoryScore],
    scores: dict[str, int | None],
    gate: GateResult,
    *,
    exclusion_confirmed: bool,
) -> ScoreResult:
    points, assessed = weighted_points(scores)
    unassessed = 100 - assessed
    complete = unassessed == 0
    possible_min = points + unassessed * 0.1  # every missing category at score 1
    possible_max = points + unassessed  # every missing category at score 10
    underlying: FitBand | None = band_for(points) if complete else None

    failed = gate.status == GateStatus.DOES_NOT_MEET
    pending = gate.status in (GateStatus.PARTIAL, GateStatus.CANNOT_DETERMINE)
    override = None

    if failed or exclusion_confirmed:
        reason = "failed stage gate" if failed else "confirmed TEN exclusion category"
        if failed and exclusion_confirmed:
            reason = "failed stage gate and confirmed exclusion"
        if underlying == "Likely Pass":
            effective = "Likely Pass"
        elif underlying is None and possible_max < 50:
            effective = "Likely Pass"
        elif underlying is None:
            effective = "Weak Fit or below (capped)"
        else:
            effective = "Weak Fit"
        if underlying in ("Strong Fit", "Moderate Fit") or underlying is None:
            override = f"Rating capped at Weak Fit: {reason}."
        if pending:
            override = (override or "") + " Stage gate also pending verification."
    elif pending:
        effective = "Pending stage verification"
        override = (
            f"Stage gate {gate.status.value.lower()}: no final Strong or Moderate Fit recommendation "
            "can be issued until the gate is verified."
        )
    elif complete:
        effective = underlying  # type: ignore[assignment]
    else:
        effective = "Withheld - scoring incomplete"

    if complete:
        status_label = f"{points:.1f} / 100"
    else:
        status_label = f"Provisional: {points:.1f} pts from {assessed}% assessed weight (range {possible_min:.1f}-{possible_max:.1f})"

    return ScoreResult(
        categories=categories,
        complete=complete,
        total=round(points, 2) if complete else None,
        supported_points=round(points, 2),
        assessed_weight=assessed,
        possible_min=round(possible_min, 2),
        possible_max=round(possible_max, 2),
        underlying_band=underlying,
        effective_rating=effective,
        override_applied=override.strip() if override else None,
        status_label=status_label,
    )
