from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ten_screener.config import load_settings  # noqa: E402


@pytest.fixture
def settings(monkeypatch):
    """Settings with dummy credentials; the Anthropic client is always faked in tests."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "TEN_REFUSAL_FALLBACK", "TEN_EFFORT", "TEN_THINKING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("ten_screener.config.load_dotenv", lambda *a, **k: None)
    base = load_settings()
    # Fallback off keeps request-shape tests on the standard endpoint; the default (on) has its own test in test_llm.py.
    return dataclasses.replace(base, api_key="test-key", model="test-model-from-env", max_visual_pages=4, refusal_fallback=False)
