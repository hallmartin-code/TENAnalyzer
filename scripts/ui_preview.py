"""Preview the web UI with a SYNTHETIC report preloaded - no upload, API key or email needed.

    python -m streamlit run scripts/ui_preview.py

For design review only. The fictional company comes from tests/synthetic.py.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.chdir(ROOT)

import streamlit as st  # noqa: E402

if "report" not in st.session_state and os.environ.get("TEN_PREVIEW_EMPTY") != "1":
    from synthetic import FakeAnthropic, track_a_assessment_json, track_a_extraction, track_a_ledger_json
    from ten_screener.analysis.analyzer import analyse
    from ten_screener.analysis.llm import ClaudeClient
    from ten_screener.config import load_settings
    from ten_screener.notify import EmailResult

    settings = dataclasses.replace(load_settings(), api_key="preview", model="synthetic-preview")
    extraction = track_a_extraction()
    client = ClaudeClient(settings, client=FakeAnthropic([track_a_ledger_json(), track_a_assessment_json()]))
    report, usage = analyse(extraction, settings, client=client)
    st.session_state.update(extraction=extraction, report=report, usage=usage,
                            email_result=EmailResult(sent=True, message_id="preview", recipients=list(settings.email_to)))

exec(compile((ROOT / "app.py").read_text(encoding="utf-8"), str(ROOT / "app.py"), "exec"))  # noqa: S102
