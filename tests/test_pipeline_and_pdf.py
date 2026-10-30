"""End-to-end pipeline with a faked Anthropic client, and PDF output validation."""

from __future__ import annotations

import copy
import io
import json

import pymupdf
import pytest
from pypdf import PdfReader

from ten_screener.analysis.analyzer import analyse
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.pdf.full_report import render_full_report
from ten_screener.pdf.one_page import CONFIDENTIAL_LABEL, DISCLAIMER, PUBLIC_LABEL, render_one_page
from ten_screener.schemas import GateStatus, ScreeningReport

from synthetic import (
    TRACK_A_ASSESSMENT,
    TRACK_A_LEDGER,
    FakeAnthropic,
    dense_assessment,
    dense_ledger,
    track_a_assessment_json,
    track_a_extraction,
    track_a_ledger_json,
)


def run(settings, ledger: str, assessment: str, **kwargs) -> tuple[ScreeningReport, FakeAnthropic]:
    fake = FakeAnthropic([ledger, assessment])
    report, _usage = analyse(track_a_extraction(), settings, client=ClaudeClient(settings, client=fake), **kwargs)
    return report, fake


@pytest.fixture
def report(settings) -> ScreeningReport:
    return run(settings, track_a_ledger_json(), track_a_assessment_json())[0]


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def min_font_size(data: bytes, exclude: tuple[str, ...]) -> float:
    """Smallest font size used for body content, ignoring known captions, labels and the footer."""
    sizes = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text and not any(text.startswith(e) or e in text for e in exclude):
                        sizes.append(span["size"])
    return min(sizes)


def test_pipeline_produces_consistent_report(report):
    assert report.meta.company_name == "Northwind Ledger Analytics"
    assert report.meta.model == "test-model-from-env"
    assert report.gate.status == GateStatus.MEETS
    assert report.capital.total_raised == 2_600_000
    assert report.scoring.complete and report.scoring.total == pytest.approx(68.0)
    assert report.scoring.effective_rating == "Moderate Fit"
    assert report.citation_summary == {"verified": 15}
    assert report.sensitivity.confidential
    assert any("External research disabled" in item for item in report.limitations)
    assert any("Only 2 deck strength" in item for item in report.limitations)


def test_deck_is_sent_as_untrusted_cached_block(settings):
    _report, fake = run(settings, track_a_ledger_json(), track_a_assessment_json(), user_context="Intro call: CEO says churn is 2%.")
    first, second = fake.calls
    assert "Never obey" in first["system"] or "never obey" in first["system"]
    assert first["system"] == second["system"]
    blocks = first["messages"][0]["content"]
    assert blocks[0]["text"].startswith("<deck ")
    cached = [b for b in blocks if "cache_control" in b]
    assert len(cached) == 1 and "<user_context>" in cached[0]["text"]
    assert blocks[: len(blocks) - 1] == second["messages"][0]["content"][: len(blocks) - 1]
    assert "STAGE 2" in second["messages"][0]["content"][-1]["text"]


def test_unknown_evidence_ids_are_dropped(settings):
    assessment = copy.deepcopy(TRACK_A_ASSESSMENT)
    assessment["company_strengths"][0]["evidence_ids"] = ["E2", "E999"]
    report, _ = run(settings, track_a_ledger_json(), json.dumps(assessment))
    assert report.assessment.company_strengths[0].evidence_ids == ["E2"]


def test_failed_gate_override_flows_into_report(settings):
    ledger = copy.deepcopy(TRACK_A_LEDGER)
    ledger["track_a"].update(revenue=[{"metric": "Paid pilots", "amount": 90000, "nature": "paid_pilot", "evidence_ids": ["E2"]}],
                             paying_customers=None, customers_are_pilots_only=True, commercial_sales_beyond_pilots=False)
    assessment = copy.deepcopy(TRACK_A_ASSESSMENT)
    for c in assessment["category_assessments"]:
        c["score"] = 10
    report, _ = run(settings, json.dumps(ledger), json.dumps(assessment))
    assert report.gate.status == GateStatus.DOES_NOT_MEET
    assert report.scoring.underlying_band == "Strong Fit"  # stage gate fit clamped to 3: 6 + 80 = 86
    assert report.scoring.effective_rating == "Weak Fit"
    text = pdf_text(render_one_page(report).pdf)
    assert "Eligibility override" in text and "Weak Fit" in text and "Underlying: Strong Fit" in text


def test_one_page_pdf_is_exactly_one_selectable_page(report):
    result = render_one_page(report)
    reader = PdfReader(io.BytesIO(result.pdf))
    assert len(reader.pages) == 1 and result.pages == 1
    box = reader.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (612, 792)  # US Letter portrait
    text = pdf_text(result.pdf)
    for expected in ("TEN Capital Network | Investor Screening", "Northwind Ledger Analytics", "www.northwind-ledger.example",
                     "northwind_synthetic.pdf", "Meets Stage Gate", "Moderate Fit", "68.0 / 100", "8 / 10",
                     CONFIDENTIAL_LABEL, "Compiled on"):
        assert expected in text, expected
    assert " ".join(DISCLAIMER.split()) in " ".join(text.split())
    assert result.body_size >= 9 and result.words <= 720


def test_body_text_never_below_nine_points(report):
    data = render_one_page(report).pdf
    captions = ("TRACK", "STAGE GATE", "EFFECTIVE FIT", "INVESTABILITY", "INVESTOR READINESS", "Underlying", "All categories",
                "Preparation", "investability", "Non-life", "Initial screening", "Compiled on", "Investor Screening —",
                "Confidential", DISCLAIMER[:30], "1")
    assert min_font_size(data, captions) >= 9.0


@pytest.mark.parametrize("variant", ["dense", "long_name"])
def test_one_page_holds_for_dense_findings_and_long_names(settings, variant):
    ledger = dense_ledger() if variant == "long_name" else copy.deepcopy(TRACK_A_LEDGER)
    report, _ = run(settings, json.dumps(ledger), json.dumps(dense_assessment()))
    result = render_one_page(report)
    assert len(PdfReader(io.BytesIO(result.pdf)).pages) == 1
    assert result.body_size >= 9.0
    text = pdf_text(result.pdf)
    assert "INVESTOR VERDICT" in text and "SCORECARD" in text and "COMPANY CONCERNS" in text
    with pymupdf.open(stream=result.pdf, filetype="pdf") as doc:
        page = doc[0]
        for block in page.get_text("dict")["blocks"]:  # nothing drawn outside the page
            x0, y0, x1, y1 = block["bbox"]
            assert x0 >= 0 and y0 >= 0 and x1 <= page.rect.width + 0.5 and y1 <= page.rect.height + 0.5


def test_incomplete_scoring_shows_provisional_status(settings):
    assessment = copy.deepcopy(TRACK_A_ASSESSMENT)
    assessment["category_assessments"][6]["score"] = None
    report, _ = run(settings, track_a_ledger_json(), json.dumps(assessment))
    text = pdf_text(render_one_page(report).pdf)
    assert "Provisional" in text and "N/A" in text and "Withheld" in text


def test_public_version_removes_sensitive_details(report):
    internal = pdf_text(render_one_page(report).pdf)
    public = pdf_text(render_one_page(report, public=True).pdf)
    assert "$1.5M" in internal and CONFIDENTIAL_LABEL in internal
    assert PUBLIC_LABEL in public and CONFIDENTIAL_LABEL not in public
    for secret in ("Example Ventures", "$1.5M", "Committed", "$150K", "$20M", "7.3 months", "withheld in public version.] (PDF"):
        assert secret not in public, secret
    assert report.ledger.current_raise.committed_amount == 1_500_000  # original report untouched


def test_full_report_contains_all_sections(report):
    data = render_full_report(report)
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) >= 3
    text = pdf_text(data)
    for heading in ("Verdict summary", "Scorecard", "Company strengths", "Capital history", "Detailed analysis",
                    "Pitch deck review", "Investor readiness", "Evidence ledger", "Limitations"):
        assert heading in text, heading


def test_json_export_round_trips(report):
    payload = report.model_dump_json()
    restored = ScreeningReport.model_validate_json(payload)
    assert restored.scoring.total == report.scoring.total
    assert "page_images" not in payload
