"""Runtime settings, read from environment variables (optionally via a local .env file).

Credentials and the model identifier are never hard-coded: both must be supplied
through the environment. See ``.env.example`` for every variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
DEFAULT_FOOTER_LOGO = ASSETS_DIR / "TEN_Capital_logo_footer.png"

_EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}
_EMAIL_ATTACHMENT_KEYS = ("review", "onepage", "evidence", "json")
DEFAULT_EMAIL_TO = "Info@tencapital.group"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    value = _env(name)
    try:
        return max(minimum, int(value)) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str | None
    effort: str | None
    thinking: str  # "adaptive" or "omit"
    refusal_fallback: bool
    max_output_tokens: int
    max_retries: int
    request_timeout_s: float
    max_upload_mb: int
    max_pages: int
    max_visual_pages: int
    visual_width_px: int
    external_research_enabled: bool
    web_search_tool_type: str
    ocr_language: str
    resend_api_key: str | None = None
    email_mode: str = "auto"  # off | auto (send when RESEND_API_KEY is set) | on
    email_to: tuple[str, ...] = (DEFAULT_EMAIL_TO,)
    email_from: str | None = None
    email_reply_to: str | None = None
    email_attachments: tuple[str, ...] = ("review", "onepage")
    email_on_failure: bool = True

    @property
    def email_enabled(self) -> bool:
        return self.email_mode == "on" or (self.email_mode == "auto" and bool(self.resend_api_key))

    def missing_api_config(self) -> list[str]:
        missing = []
        if not self.api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.model:
            missing.append("ANTHROPIC_MODEL")
        return missing


def load_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env", override=False)
    effort = _env("TEN_EFFORT", "high")
    if effort and effort.lower() in {"omit", "none", "default"}:
        effort = None
    elif effort and effort.lower() not in _EFFORT_LEVELS:
        effort = "high"
    thinking = (_env("TEN_THINKING", "adaptive") or "adaptive").lower()
    if thinking not in {"adaptive", "omit"}:
        thinking = "adaptive"
    return Settings(
        api_key=_env("ANTHROPIC_API_KEY"),
        model=_env("ANTHROPIC_MODEL"),
        effort=effort.lower() if effort else None,
        thinking=thinking,
        refusal_fallback=_env_bool("TEN_REFUSAL_FALLBACK", False),
        max_output_tokens=_env_int("TEN_MAX_OUTPUT_TOKENS", 48000, minimum=4000),
        max_retries=_env_int("TEN_API_MAX_RETRIES", 3, minimum=0),
        request_timeout_s=float(_env_int("TEN_API_TIMEOUT_SECONDS", 900, minimum=30)),
        max_upload_mb=_env_int("TEN_MAX_UPLOAD_MB", 50),
        max_pages=_env_int("TEN_MAX_PAGES", 120),
        max_visual_pages=_env_int("TEN_MAX_VISUAL_PAGES", 40, minimum=0),
        visual_width_px=_env_int("TEN_VISUAL_WIDTH_PX", 1280, minimum=400),
        external_research_enabled=_env_bool("TEN_ENABLE_EXTERNAL_RESEARCH", False),
        web_search_tool_type=_env("TEN_WEB_SEARCH_TOOL", "web_search_20260209") or "web_search_20260209",
        ocr_language=_env("TEN_OCR_LANGUAGE", "eng") or "eng",
        resend_api_key=_env("RESEND_API_KEY"),
        email_mode=_email_mode(),
        email_to=_csv("TEN_EMAIL_TO", (DEFAULT_EMAIL_TO,)),
        email_from=_env("TEN_EMAIL_FROM"),
        email_reply_to=_env("TEN_EMAIL_REPLY_TO"),
        email_attachments=tuple(k for k in _csv("TEN_EMAIL_ATTACH", ("review", "onepage")) if k in _EMAIL_ATTACHMENT_KEYS),
        email_on_failure=_env_bool("TEN_EMAIL_ON_FAILURE", True),
    )


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _env(name)
    if value is None:
        return default
    items = tuple(part.strip() for part in value.split(",") if part.strip())
    return items or default


def _email_mode() -> str:
    mode = (_env("TEN_EMAIL_ENABLED", "auto") or "auto").lower()
    mode = {"true": "on", "1": "on", "yes": "on", "false": "off", "0": "off", "no": "off"}.get(mode, mode)
    return mode if mode in ("off", "auto", "on") else "auto"
