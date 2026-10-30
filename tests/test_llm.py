"""Claude client wrapper: request shape, JSON validation and repair, API failure handling. No network."""

from __future__ import annotations

import dataclasses

import anthropic
import httpx
import pytest

from ten_screener.analysis.llm import ClaudeClient, extract_json_text
from ten_screener.errors import AnalysisError, ConfigurationError
from ten_screener.schemas import LedgerOutput

from synthetic import FakeAnthropic, fake_message, track_a_ledger_json

MESSAGES = [{"role": "user", "content": "deck"}]


def api_error(cls, status: int, headers: dict | None = None):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request, headers=headers or {})
    return cls(f"error {status}", response=response, body={"error": {"message": f"status {status}"}})


def test_only_api_key_is_required(settings):
    assert dataclasses.replace(settings, model=None).missing_api_config() == []
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        ClaudeClient(dataclasses.replace(settings, api_key=None))


def test_defaults_to_current_model_with_refusal_fallback(monkeypatch):
    from ten_screener.config import DEFAULT_MODEL, load_settings

    for name in ("ANTHROPIC_MODEL", "TEN_REFUSAL_FALLBACK", "TEN_EFFORT", "TEN_THINKING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)
    s = load_settings()
    assert s.model == DEFAULT_MODEL == "claude-opus-5-5" and s.refusal_fallback
    fake = FakeAnthropic([track_a_ledger_json()])
    client = ClaudeClient(s, client=fake)
    client.generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and client.model == "claude-opus-5-5"
    assert call["thinking"] == {"type": "adaptive"} and call["output_config"] == {"effort": "high"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]


def test_model_override_from_env_and_fallback_can_be_disabled(monkeypatch):
    from ten_screener.config import load_settings

    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-other-model")
    monkeypatch.setenv("TEN_REFUSAL_FALLBACK", "off")
    s = load_settings()
    fake = FakeAnthropic([track_a_ledger_json()])
    ClaudeClient(s, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    call = fake.calls[0]
    assert call["model"] == "some-other-model" and "fallbacks" not in call and "betas" not in call


def test_optional_params_omitted(settings):
    s = dataclasses.replace(settings, effort=None, thinking="omit", refusal_fallback=False)
    fake = FakeAnthropic([track_a_ledger_json()])
    ClaudeClient(s, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    call = fake.calls[0]
    assert "thinking" not in call and "output_config" not in call


def test_fenced_json_accepted():
    assert extract_json_text('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_malformed_json_repaired_once(settings):
    fake = FakeAnthropic(['{"evidence": [], "company": ', track_a_ledger_json()])
    client = ClaudeClient(settings, client=fake)
    ledger = client.generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    assert ledger.company.name == "Northwind Ledger Analytics"
    assert client.usage.repairs == 1 and len(fake.calls) == 2
    assert "Validation errors" in fake.calls[1]["messages"][0]["content"]


def test_schema_invalid_json_repaired(settings):
    fake = FakeAnthropic(['{"evidence": "not a list"}', track_a_ledger_json()])
    ledger = ClaudeClient(settings, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    assert ledger.track.track == "A"


def test_malformed_twice_raises_actionable_error(settings):
    fake = FakeAnthropic(["not json", "still not json"])
    with pytest.raises(AnalysisError, match="malformed") as info:
        ClaudeClient(settings, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")
    assert info.value.retryable


def test_truncated_response_explains_limit(settings):
    fake = FakeAnthropic([fake_message('{"evidence": [', stop_reason="max_tokens")])
    with pytest.raises(AnalysisError, match="TEN_MAX_OUTPUT_TOKENS"):
        ClaudeClient(settings, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")


def test_refusal_reported(settings):
    fake = FakeAnthropic([fake_message("", stop_reason="refusal")])
    with pytest.raises(AnalysisError, match="declined"):
        ClaudeClient(settings, client=fake).generate_json("sys", MESSAGES, LedgerOutput, label="ledger")


def test_rate_limit_after_retries(settings):
    fake = FakeAnthropic([fake_message("")])
    fake.responses = [api_error(anthropic.RateLimitError, 429, {"retry-after": "30"})]
    fake.messages.stream = lambda **kw: _raising(fake.responses[0])
    with pytest.raises(AnalysisError, match="rate limit") as info:
        ClaudeClient(settings, client=fake).create("sys", MESSAGES)
    assert info.value.retryable and "30 seconds" in info.value.user_message


@pytest.mark.parametrize("cls,status,expected_type,match", [
    (anthropic.AuthenticationError, 401, ConfigurationError, "API key"),
    (anthropic.NotFoundError, 404, ConfigurationError, "ANTHROPIC_MODEL"),
    (anthropic.BadRequestError, 400, AnalysisError, "rejected the request"),
    (anthropic.InternalServerError, 529, AnalysisError, "overloaded"),
])
def test_api_errors_mapped(settings, cls, status, expected_type, match):
    fake = FakeAnthropic([])
    fake.messages.stream = lambda **kw: _raising(api_error(cls, status))
    with pytest.raises(expected_type, match=match):
        ClaudeClient(settings, client=fake).create("sys", MESSAGES)


def test_connection_error_mapped(settings):
    fake = FakeAnthropic([])
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake.messages.stream = lambda **kw: _raising(anthropic.APIConnectionError(request=request))
    with pytest.raises(AnalysisError, match="network") as info:
        ClaudeClient(settings, client=fake).create("sys", MESSAGES)
    assert info.value.retryable


def _raising(exc):
    class _S:
        def __enter__(self):
            raise exc

        def __exit__(self, *a):
            return False

    return _S()
