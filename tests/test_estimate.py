"""Stage and FDA pathway estimate: replaces Cannot Determine with a labeled, confidence-rated estimate. No network."""

from __future__ import annotations

import copy
import dataclasses
import json
from types import SimpleNamespace

from ten_screener.analysis.analyzer import analyse
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.rules import apply_estimate, evaluate_stage_gate
from ten_screener.schemas import GateResult, GateStatus, LedgerOutput, StageEstimate
from ten_screener.scoring import score

from synthetic import TRACK_A_LEDGER, FakeAnthropic, fake_message, track_a_assessment_json, track_a_extraction

FDA_URL = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K231234"


def device_ledger() -> dict:
    """A Track B deck that claims FDA clearance but discloses no pathway: the gate is Cannot Determine."""
    data = copy.deepcopy(TRACK_A_LEDGER)
    data["track"] = {"track": "B", "rationale": "Medical device claiming FDA clearance.", "evidence_ids": []}
    data["track_a"] = None
    data["track_b"] = {"product_type": "medical_device"}
    return data


def estimate_json(**overrides) -> str:
    data = {
        "track": "B",
        "estimated_stage": "Seed - FDA-cleared device, pre-commercial launch",
        "gate_status": "Meets Stage Gate",
        "confidence": "medium",
        "regulatory_pathway": "510(k)",
        "jurisdiction": "US (FDA)",
        "authorization_status": "Cleared - K231234, 2023",
        "clearance_reference": "K231234",
        "rationale": "FDA 510(k) database lists a clearance for the company's laser system (S1).",
        "verification_needed": "FDA 510(k) clearance letter with indications for use",
        "evidence_ids": ["S1", "E999"],
    }
    data.update(overrides)
    return json.dumps(data)


def search_message():
    citation = SimpleNamespace(url=FDA_URL, title="510(k) Premarket Notification", cited_text="K231234 ... dental laser")
    block = SimpleNamespace(type="text", text="FDA cleared the company's dental laser under K231234 in 2023.", citations=[citation])
    message = fake_message("")
    message.content = [block]
    return message


def unsettled_gate() -> GateResult:
    gate = evaluate_stage_gate(LedgerOutput.model_validate(device_ledger()))
    assert gate.status == GateStatus.CANNOT_DETERMINE
    return gate


def test_estimate_replaces_cannot_determine():
    gate = apply_estimate(unsettled_gate(), StageEstimate.model_validate_json(estimate_json()))
    assert gate.status == GateStatus.MEETS and gate.estimated
    assert gate.label == "Meets Stage Gate (estimated)"
    text = " ".join(gate.reasons)
    assert "510(k)" in text and "K231234" in text and "medium confidence" in text and "To verify" in text


def test_decided_gate_is_not_overwritten():
    decided = GateResult(track="A", track_label="Track A", status=GateStatus.DOES_NOT_MEET, reasons=["pre-revenue"])
    assert apply_estimate(decided, StageEstimate.model_validate_json(estimate_json())) is decided


def test_estimate_counts_fully_at_any_confidence():
    from synthetic import TRACK_A_ASSESSMENT
    from ten_screener.schemas import AssessmentOutput

    assessment = AssessmentOutput.model_validate(TRACK_A_ASSESSMENT)
    low = apply_estimate(unsettled_gate(), StageEstimate.model_validate_json(estimate_json(confidence="low")))
    result = score(assessment, low, exclusion_confirmed=False)
    assert result.effective_rating != "Pending stage verification"
    stage_fit = next(c for c in result.categories if c.key == "stage_gate_fit")
    assert stage_fit.score is not None and 6 <= stage_fit.score <= 10


def test_pipeline_runs_search_and_estimate_when_gate_unsettled(settings):
    s = dataclasses.replace(settings, stage_estimate_enabled=True)
    fake = FakeAnthropic([json.dumps(device_ledger()), search_message(), estimate_json(), track_a_assessment_json()])
    report, _ = analyse(track_a_extraction(), s, client=ClaudeClient(s, client=fake))
    assert report.gate.estimated and report.gate.status == GateStatus.MEETS
    assert report.gate.estimate.evidence_ids == ["S1"]  # unknown ids dropped
    assert [f.id for f in report.external_findings] == ["S1"] and report.external_findings[0].url == FDA_URL
    search_call = fake.calls[1]
    assert search_call["tools"][0]["name"] == "web_search" and "510(k)" in search_call["messages"][0]["content"]
    assert "estimated" in fake.calls[3]["messages"][0]["content"][-1]["text"]  # gate passed to the assessment
    assert any("estimated from the deck and public web sources" in item for item in report.limitations)


def test_search_failure_still_produces_estimate(settings):
    from test_llm import _raising, api_error
    import anthropic

    s = dataclasses.replace(settings, stage_estimate_enabled=True)
    responses = [json.dumps(device_ledger()), "SEARCH_FAILS", estimate_json(confidence="low", gate_status="Partially Meets",
                 evidence_ids=[]), track_a_assessment_json()]
    fake = FakeAnthropic(responses)
    original = fake.messages.stream

    def stream(**kw):
        if fake.responses and fake.responses[0] == "SEARCH_FAILS":
            fake.responses.pop(0)
            return _raising(api_error(anthropic.BadRequestError, 400))
        return original(**kw)

    fake.messages.stream = stream
    report, _ = analyse(track_a_extraction(), s, client=ClaudeClient(s, client=fake))
    assert report.gate.estimated and report.gate.label == "Partially Meets (estimated)"
    assert any("Stage and FDA pathway search failed" in item for item in report.limitations)


def test_estimate_disabled_keeps_cannot_determine(settings):
    fake = FakeAnthropic([json.dumps(device_ledger()), track_a_assessment_json()])
    report, _ = analyse(track_a_extraction(), settings, client=ClaudeClient(settings, client=fake))
    assert report.gate.status == GateStatus.CANNOT_DETERMINE and not report.gate.estimated
