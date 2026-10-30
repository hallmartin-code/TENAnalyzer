"""Anthropic API wrapper: streaming requests, JSON validation, one repair pass, actionable errors.

The model id, effort, thinking mode and refusal fallback all come from settings
(environment variables). Requests stream so that long analyses never hit an HTTP
timeout; the SDK retries 408/409/429/5xx and connection errors itself
(``TEN_API_MAX_RETRIES``) before an error reaches this module.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from ten_screener.analysis.prompts import REPAIR_SYSTEM_PROMPT, schema_text
from ten_screener.config import DEFAULT_MODEL, Settings
from ten_screener.errors import AnalysisError, ConfigurationError

LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    repairs: int = 0
    notes: list[str] = field(default_factory=list)

    def add(self, usage: Any) -> None:
        self.requests += 1
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_tokens,
            "cache_creation_input_tokens": self.cache_write_tokens,
            "json_repairs": self.repairs,
            "notes": self.notes,
        }


def extract_json_text(text: str) -> str:
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the response")
    return cleaned[start : end + 1]


def parse_model(text: str, model: type[T]) -> T:
    return model.model_validate(json.loads(extract_json_text(text)))


def _errors_summary(exc: Exception, limit: int = 25) -> str:
    if isinstance(exc, ValidationError):
        lines = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:limit]]
        return "\n".join(lines)
    return str(exc)[:2000]


class ClaudeClient:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        missing = settings.missing_api_config()
        if missing and client is None:
            raise ConfigurationError(
                "Analysis needs " + " and ".join(missing) + ". Add it to .env (or the Railway variables) and restart the app."
            )
        self.settings = settings
        self.model = settings.model or DEFAULT_MODEL
        self.usage = Usage()
        self._client = client or anthropic.Anthropic(
            api_key=settings.api_key,
            max_retries=settings.max_retries,
            timeout=settings.request_timeout_s,
        )

    # ------------------------------------------------------------------ raw
    def _kwargs(self, system: str, messages: list[dict[str, Any]], max_tokens: int, tools: list[dict] | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if self.settings.thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}
        if self.settings.effort:
            kwargs["output_config"] = {"effort": self.settings.effort}
        if tools:
            kwargs["tools"] = tools
        return kwargs

    def create(self, system: str, messages: list[dict[str, Any]], *, max_tokens: int | None = None,
               tools: list[dict] | None = None) -> Any:
        kwargs = self._kwargs(system, messages, max_tokens or self.settings.max_output_tokens, tools)
        try:
            if self.settings.refusal_fallback:
                stream = self._client.beta.messages.stream(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
            else:
                stream = self._client.messages.stream(**kwargs)
            with stream as s:
                message = s.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ConfigurationError("The Anthropic API rejected the API key (401). Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ConfigurationError("The API key does not have permission for this request or model (403).") from exc
        except anthropic.NotFoundError as exc:
            raise ConfigurationError(
                f"Model '{self.model}' was not found (404). If you set ANTHROPIC_MODEL, check it is a valid model id for your account, or remove it to use the default."
            ) from exc
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after") if exc.response is not None else None
            wait = f" Retry after about {retry_after} seconds." if retry_after else " Wait a minute and retry."
            raise AnalysisError("The Anthropic API rate limit was reached after automatic retries." + wait, retryable=True) from exc
        except anthropic.BadRequestError as exc:
            hint = ""
            if self.settings.refusal_fallback:
                hint = " If your model does not support server-side refusal fallback, set TEN_REFUSAL_FALLBACK=off."
            if "effort" in str(exc).lower() or "thinking" in str(exc).lower():
                hint += " Your model may not support the configured TEN_EFFORT / TEN_THINKING; try TEN_EFFORT=omit or TEN_THINKING=omit."
            raise AnalysisError("The API rejected the request (400): " + _api_message(exc) + hint) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 413:
                raise AnalysisError("The deck is too large for one request. Reduce TEN_MAX_VISUAL_PAGES or upload a shorter deck.") from exc
            retryable = exc.status_code >= 500
            raise AnalysisError(
                f"The Anthropic API returned an error ({exc.status_code})." + (" The service may be overloaded; retry shortly." if retryable else ""),
                retryable=retryable,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise AnalysisError("Could not reach the Anthropic API. Check the network connection and retry.", retryable=True) from exc

        self.usage.add(getattr(message, "usage", None))
        if message.stop_reason == "refusal":
            raise AnalysisError(
                "The model declined to complete this analysis (refusal). Review the deck content; if it is a legitimate "
                "deck, retry or enable TEN_REFUSAL_FALLBACK."
            )
        return message

    # ----------------------------------------------------------------- json
    def generate_json(self, system: str, messages: list[dict[str, Any]], model: type[T], *, label: str) -> T:
        message = self.create(system, messages)
        text = "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")
        if message.stop_reason == "max_tokens":
            self.usage.notes.append(f"{label}: response hit max_tokens")
            raise AnalysisError(
                f"The {label} response was cut off at the output limit. Increase TEN_MAX_OUTPUT_TOKENS and retry."
            )
        try:
            return parse_model(text, model)
        except (ValueError, ValidationError) as exc:
            LOGGER.warning("%s: response failed validation; attempting one repair", label)
            return self._repair(text, model, exc, label)

    def _repair(self, text: str, model: type[T], error: Exception, label: str) -> T:
        self.usage.repairs += 1
        prompt = (
            f"JSON Schema:\n{schema_text(model)}\n\nValidation errors:\n{_errors_summary(error)}\n\n"
            f"JSON to repair:\n{text[:200_000]}"
        )
        message = self.create(REPAIR_SYSTEM_PROMPT, [{"role": "user", "content": prompt}])
        repaired = "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")
        try:
            return parse_model(repaired, model)
        except (ValueError, ValidationError) as exc:
            raise AnalysisError(
                f"The model returned a malformed {label} twice (structured output failed validation). Retry the analysis; "
                "if it persists, try a more capable model or a higher TEN_EFFORT.",
                detail=_errors_summary(exc),
                retryable=True,
            ) from exc


def _api_message(exc: anthropic.APIStatusError) -> str:
    try:
        body = exc.body if isinstance(exc.body, dict) else {}
        return str(body.get("error", {}).get("message") or exc.message)[:400]
    except Exception:  # noqa: BLE001
        return "request invalid"
