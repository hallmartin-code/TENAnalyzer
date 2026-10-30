"""Resend result emails. All HTTP goes to an httpx.MockTransport - no email is ever sent."""

from __future__ import annotations

import base64
import dataclasses
import json

import httpx
import pytest

from ten_screener import notify
from ten_screener.analysis.analyzer import analyse
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.config import DEFAULT_EMAIL_TO, load_settings

from synthetic import FakeAnthropic, track_a_assessment_json, track_a_extraction, track_a_ledger_json


@pytest.fixture
def report(settings):
    fake = FakeAnthropic([track_a_ledger_json(), track_a_assessment_json()])
    return analyse(track_a_extraction(), settings, client=ClaudeClient(settings, client=fake))[0]


@pytest.fixture
def email_settings(settings):
    return dataclasses.replace(settings, resend_api_key="re_test_key", email_mode="auto",
                               email_from="TEN Capital Screening <screening@tencapital.group>")


def mock_client(status: int = 200, body: dict | None = None):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=body if body is not None else {"id": "email_123"})

    return httpx.Client(transport=httpx.MockTransport(handler)), captured


OUTPUTS = {"review": b"%PDF-review", "onepage": b"%PDF-onepage", "evidence": b"%PDF-evidence"}


def test_default_recipient_and_auto_mode(monkeypatch):
    for name in ("TEN_EMAIL_TO", "TEN_EMAIL_ENABLED", "RESEND_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)
    s = load_settings()
    assert s.email_to == (DEFAULT_EMAIL_TO,) == ("Info@tencapital.group",)
    assert not s.email_enabled  # auto, but no key
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("TEN_EMAIL_TO", "a@x.com, b@y.com")
    s = load_settings()
    assert s.email_enabled and s.email_to == ("a@x.com", "b@y.com")
    monkeypatch.setenv("TEN_EMAIL_ENABLED", "off")
    assert not load_settings().email_enabled


def test_analysis_email_payload(report, email_settings):
    client, captured = mock_client()
    result = notify.notify_analysis(report, OUTPUTS, email_settings, client=client)
    assert result.sent and result.message_id == "email_123"
    assert result.recipients == ["Info@tencapital.group"]
    request = captured[0]
    assert str(request.url) == notify.RESEND_ENDPOINT
    assert request.headers["Authorization"] == "Bearer re_test_key"
    assert request.headers["Idempotency-Key"] == f"ten-screening-{report.meta.run_id}"
    payload = json.loads(request.content)
    assert payload["to"] == ["Info@tencapital.group"]
    assert payload["from"] == "TEN Capital Screening <screening@tencapital.group>"
    assert payload["subject"].startswith("[Confidential] TEN Screening: Northwind Ledger Analytics - Moderate Fit (68.0/100)")
    names = [a["filename"] for a in payload["attachments"]]
    assert names == ["Northwind_Ledger_Analytics_TEN_Investor_Screening_Review.pdf", "Northwind_Ledger_Analytics_TEN_Screening_OnePage.pdf"]
    assert base64.b64decode(payload["attachments"][0]["content"]) == b"%PDF-review"
    for expected in ("Meets Stage Gate", "Investor verdict", "Company concerns", "not independent verification"):
        assert expected in payload["html"] and expected in payload["text"]
    assert all(set(t["value"]) <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") for t in payload["tags"])


def test_report_text_is_html_escaped(report, email_settings):
    report.assessment.investor_verdict = "<script>alert(1)</script> & <b>bold</b>"
    _, html, text = notify.analysis_email(report)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<script>" in text  # plain text is not HTML


def test_retry_uses_distinct_idempotency_key(report, email_settings):
    client, captured = mock_client()
    notify.notify_analysis(report, OUTPUTS, email_settings, attempt=2, client=client)
    assert captured[0].headers["Idempotency-Key"] == f"ten-screening-{report.meta.run_id}-retry2"


def test_json_and_evidence_attachments_optional(report, email_settings):
    s = dataclasses.replace(email_settings, email_attachments=("evidence", "json"))
    client, captured = mock_client()
    notify.notify_analysis(report, OUTPUTS, s, client=client)
    payload = json.loads(captured[0].content)
    names = [a["filename"] for a in payload["attachments"]]
    assert names[0].endswith("Evidence_Appendix.pdf") and names[1].endswith("Screening.json")
    restored = json.loads(base64.b64decode(payload["attachments"][1]["content"]))
    assert restored["meta"]["company_name"] == "Northwind Ledger Analytics"


def test_oversized_attachments_dropped_not_fatal(report, email_settings, monkeypatch):
    monkeypatch.setattr(notify, "MAX_ATTACHMENT_BYTES", 15)
    client, captured = mock_client()
    result = notify.notify_analysis(report, OUTPUTS, email_settings, client=client)
    assert result.sent and len(result.attachments_dropped) == 1
    assert "too large to attach" in result.summary


def test_disabled_or_unconfigured_skips_without_http(report, settings):
    client, captured = mock_client()
    no_key = notify.notify_analysis(report, OUTPUTS, dataclasses.replace(settings, resend_api_key=None), client=client)
    off = notify.notify_analysis(report, OUTPUTS, dataclasses.replace(settings, resend_api_key="re_x", email_mode="off"), client=client)
    assert not captured
    assert no_key.skipped_reason == "RESEND_API_KEY is not set." and not no_key.sent
    assert off.skipped_reason == "result emails are turned off."


@pytest.mark.parametrize("status,fragment,retryable", [
    (403, "verify tencapital.group", False),
    (422, "verified domain", False),
    (429, "HTTP 429", True),
    (500, "HTTP 500", True),
])
def test_resend_errors_reported_not_raised(report, settings, status, fragment, retryable):
    s = dataclasses.replace(settings, resend_api_key="re_x", email_from=None if status == 403 else "x@tencapital.group")
    client, _ = mock_client(status, {"message": "rejected"})
    result = notify.notify_analysis(report, OUTPUTS, s, client=client)
    assert not result.sent and fragment in result.error and result.retryable is retryable


def test_network_failure_reported(report, email_settings):
    def boom(request):
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    result = notify.notify_analysis(report, OUTPUTS, email_settings, client=client)
    assert not result.sent and result.retryable and "could not reach Resend" in result.error


def test_sandbox_sender_flagged(settings):
    s = dataclasses.replace(settings, resend_api_key="re_x", email_from=None)
    assert notify.uses_sandbox_sender(s)
    assert "sandbox sender" in notify.status_line(s)


def test_failure_notice_contains_no_deck_content(email_settings):
    client, captured = mock_client()
    result = notify.notify_failure("deck.pdf", "analysis", "The API rate limit was reached.", email_settings, client=client)
    payload = json.loads(captured[0].content)
    assert result.sent and payload["subject"] == "TEN Screening FAILED: deck.pdf"
    assert "not an investment finding" in payload["text"] and "attachments" not in payload


def test_failure_notice_can_be_disabled(email_settings):
    client, captured = mock_client()
    result = notify.notify_failure("deck.pdf", "analysis", "x", dataclasses.replace(email_settings, email_on_failure=False), client=client)
    assert not captured and not result.sent


def test_app_emails_once_after_analysis(monkeypatch, report):
    """Clicking Run renders the PDFs, emails them once, and shows the status; reruns do not resend."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)
    for key, value in {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": "m", "RESEND_API_KEY": "re_x",
                       "TEN_EMAIL_FROM": "screening@tencapital.group"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("ten_screener.analysis.analyzer.analyse", lambda *a, **k: (report, {}))
    sent: list[dict] = []

    def fake_notify(rep, outputs, settings, attempt=0, client=None):
        sent.append({"outputs": sorted(outputs), "to": settings.email_to})
        return notify.EmailResult(sent=True, message_id="id1", recipients=list(settings.email_to))

    monkeypatch.setattr(notify, "notify_analysis", fake_notify)
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=90)
    at.session_state["extraction"] = track_a_extraction()
    at.run()
    next(b for b in at.button if b.label == "Run investor screening").click().run()
    assert not at.exception
    assert sent == [{"outputs": ["evidence", "onepage", "review"], "to": ("Info@tencapital.group",)}]
    assert any("Results emailed to Info@tencapital.group" in s.value for s in at.success)
    at.run()  # an ordinary rerun must not send again
    assert len(sent) == 1
