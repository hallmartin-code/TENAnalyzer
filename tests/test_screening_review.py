"""Multi-page Screening Review (TEN format), its content rules, and the hosted-deployment password gate."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from ten_screener import auth, review
from ten_screener.analysis.analyzer import analyse
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.pdf.screening_review import render_screening_review
from ten_screener.schemas import ExternalFinding

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

SECTIONS = ["1. Track Classification & Stage Gate", "2. Capital History & Current Raise", "3. Company Maturity & Team",
            "4. Differentiation & Defensibility", "5. Growth Potential", "6. Financial Review", "7. Exit Potential",
            "8. Exclusion Check", "9. Pitch Document Review", "10. Investability Score", "11. Final Investor Verdict"]


def run(settings, ledger=None, assessment=None):
    fake = FakeAnthropic([ledger or track_a_ledger_json(), assessment or track_a_assessment_json()])
    return analyse(track_a_extraction(), settings, client=ClaudeClient(settings, client=fake))[0]


def pages_text(pdf: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(pdf)).pages]


def test_review_has_cover_all_sections_and_disclaimers(settings):
    pages = pages_text(render_screening_review(run(settings)))
    cover, body = pages[0], " ".join(pages[1:])
    for expected in ("INVESTOR SCREENING REVIEW", "Northwind Ledger Analytics: automated month-end reconciliation",
                     "Investability Score", "68.0", "Moderate Fit", "8 / 10", "Meets Stage Gate",
                     "Recommended next step", "CONFIDENTIAL"):
        assert expected in cover, expected
    for heading in SECTIONS:
        assert heading in body, heading
    for label in ("PROS OF THE PITCH DOCUMENT", "CRITIQUES OF THE PITCH DOCUMENT", "MISSING DATA",
                  "DILIGENCE ITEMS INVESTORS WILL REQUEST", "COMPANY STRENGTHS", "COMPANY CONCERNS",
                  "KEY ACTIONS BEFORE FUNDRAISING", "SOURCES", "Funding as a Service", "not independent verification"):
        assert label in body, label
    assert "Stage fit:" in body and "Claimed edge:" in body and "Likely acquirers:" in body
    assert all("Compiled on" in p for p in pages)  # CLAUDE.md footer on every page


@pytest.mark.parametrize("variant", ["standard", "dense_long_name"])
def test_cover_is_exactly_one_page(settings, variant):
    if variant == "standard":
        report = run(settings)
    else:
        assessment = dense_assessment()
        assessment["value_proposition_headline"] = "an extremely long value proposition headline that keeps going on"
        report = run(settings, json.dumps(dense_ledger()), json.dumps(assessment))
    pages = pages_text(render_screening_review(report))
    assert "Recommended next step" in pages[0]
    assert "1. Track Classification" not in pages[0]
    assert pages[1].count("1. Track Classification & Stage Gate") == 1


def test_comparables_require_retrieved_external_source(settings):
    assessment = copy.deepcopy(TRACK_A_ASSESSMENT)
    assessment["exit_comparables"] = [{"comparable": "Invented Co – Imaginary Target", "year": "2024",
                                       "terms": "$1B", "relevance": "made up", "source_id": "X1"}]
    report = run(settings, assessment=json.dumps(assessment))
    assert report.assessment.exit_comparables == []  # no external research ran, so no comparable can stand
    text = " ".join(pages_text(render_screening_review(report)))
    assert "Invented Co" not in text and "Comparable exits were not researched" in text


def test_comparable_kept_and_linked_when_externally_sourced(settings):
    report = run(settings)
    report.external_findings = [ExternalFinding(id="X1", claim="Acquirer bought Target for $500M.", url="https://example.com/deal",
                                                source_title="Example news", retrieved_on="2026-10-30")]
    report.meta.external_research_enabled = True
    report.assessment.exit_comparables = []
    from ten_screener.schemas import ExitComparable

    report.assessment.exit_comparables.append(ExitComparable(comparable="Acquirer – Target", year="2025", terms="$500M",
                                                             relevance="Synthetic", source_id="X1"))
    pdf = render_screening_review(report)
    text = " ".join(pages_text(pdf))
    assert "Acquirer – Target" in text and "Example news" in text
    links = [a.get_object().get("/A", {}).get("/URI") for p in PdfReader(io.BytesIO(pdf)).pages for a in (p.get("/Annots") or [])]
    assert "https://example.com/deal" in links


def test_capital_disclosure_statuses(settings):
    rows = {item: (status, detail) for item, status, detail in review.capital_disclosure_rows(run(settings))}
    assert rows["Equity raised to date"][0] == "No"
    assert rows["Convertible instruments (SAFE / note / KISS)"][0] == "Yes"
    assert rows["Non-dilutive / grant funding"][0] == "Yes"
    assert rows["Amount committed / lead"] == ("Partly", "$1.5M / no lead named")
    assert rows["Named investors"] == ("Yes", "Example Ventures")


def test_nothing_disclosed_reads_as_not_disclosed(settings):
    ledger = copy.deepcopy(TRACK_A_LEDGER)
    ledger["funding_events"] = []
    ledger["current_raise"] = {}
    report = run(settings, ledger=json.dumps(ledger))
    assert review.current_raise_line(report).startswith("Not disclosed")
    assert review.funding_line(report) == "Not disclosed"
    rows = {item: status for item, status, _ in review.capital_disclosure_rows(report)}
    assert rows["Current raise amount"] == "No" and rows["Use of funds"] == "No"


def test_single_page_source_cites_sections_not_pages(settings):
    report = run(settings)
    report.meta.page_count = 1
    assert review.source_description(report) == "single-page company document"
    assert "sections" in review.citation_convention(report)
    assert review.page_refs(report, [1]) == ""
    assert "short company document" in review.source_note(report)


# --- password gate -------------------------------------------------------------
def test_hosted_detection_and_password_check():
    assert auth.is_hosted({"RAILWAY_ENVIRONMENT_NAME": "production"})
    assert not auth.is_hosted({})
    assert auth.configured_password({"APP_PASSWORD": "  "}) is None
    assert auth.password_matches("s3cret", "s3cret") and not auth.password_matches("guess", "s3cret")


def _app(monkeypatch, **env):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)  # ignore any local .env
    for key in ("APP_PASSWORD", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID", "TEN_REQUIRE_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=60)


def _main_app_visible(at) -> bool:
    return any("Deck Analyzer" in m.value for m in at.markdown)


def test_hosted_app_without_password_is_locked(monkeypatch):
    at = _app(monkeypatch, RAILWAY_ENVIRONMENT_NAME="production").run()
    assert not at.exception
    assert any("APP_PASSWORD" in e.value for e in at.error)
    assert not _main_app_visible(at)


def test_app_requires_correct_password(monkeypatch):
    at = _app(monkeypatch, RAILWAY_ENVIRONMENT_NAME="production", APP_PASSWORD="correct horse").run()
    assert not _main_app_visible(at)
    at.text_input[0].input("wrong").run()
    at.button[0].click().run()
    assert any("Incorrect password" in e.value for e in at.error)
    at.text_input[0].input("correct horse").run()
    at.button[0].click().run()
    assert _main_app_visible(at)


def test_markdown_escaping_prevents_latex_and_formatting():
    from ten_screener import ui

    text = ui.md(r"**$1.2M ARR** and $4M raise_size [link] `code` # \ path")
    assert r"\$1.2M" in text and r"\$4M" in text
    assert r"\*\*" in text and r"raise\_size" in text and r"\[link\]" in text and r"\`code\`" in text
    assert r"\\ path" in text  # backslashes escaped first, so no double-escaping
    assert r"\\$" not in text  # ...and dollar escapes are not themselves re-escaped
    assert ui.md(None) == ""


def test_ui_html_fragments_escape_dynamic_values():
    from ten_screener import ui

    tile = ui.tiles([("Label", "<script>x</script>", "a & b", "teal")])
    assert "<script>" not in tile and "&lt;script&gt;" in tile and "a &amp; b" in tile
    assert "<code>a@b.com</code>" in ui.disclosure(("a@b.com",)) and "not configured" in ui.disclosure(None)
    assert ui.stepper(3).count("done") == 2 and 'class="ten-step current"' in ui.stepper(3)


def test_favicon_in_public_static_dir_and_configured():
    import tomllib

    from PIL import Image

    from ten_screener import ui

    assert ui.FAVICON.exists() and ui.favicon() == str(ui.FAVICON)
    assert Image.open(ui.FAVICON).size == (236, 236)
    assert {(16, 16), (32, 32), (48, 48)} <= Image.open(ui.STATIC_DIR / "favicon.ico").info["sizes"]
    config = tomllib.loads((ui.STATIC_DIR.parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["enableStaticServing"] is True
    assert "COPY static ./static" in (ui.STATIC_DIR.parent / "Dockerfile").read_text(encoding="utf-8")
