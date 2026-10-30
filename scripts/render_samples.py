"""Render sample PDFs from SYNTHETIC fixtures (no API call) for visual layout inspection.

    python scripts/render_samples.py [output_dir]

Writes one-page, dense/long-name, public and full-report PDFs plus PNG previews.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import pymupdf  # noqa: E402

from synthetic import FakeAnthropic, dense_assessment, dense_ledger, track_a_assessment_json, track_a_extraction, track_a_ledger_json  # noqa: E402
from ten_screener.analysis.analyzer import analyse  # noqa: E402
from ten_screener.analysis.llm import ClaudeClient  # noqa: E402
from ten_screener.config import load_settings  # noqa: E402
from ten_screener.pdf.full_report import render_full_report  # noqa: E402
from ten_screener.pdf.one_page import render_one_page  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "samples"
    out.mkdir(parents=True, exist_ok=True)
    settings = dataclasses.replace(load_settings(), api_key="synthetic", model="synthetic-fixture")

    def report(ledger: str, assessment: str):
        client = ClaudeClient(settings, client=FakeAnthropic([ledger, assessment]))
        return analyse(track_a_extraction(), settings, client=client)[0]

    standard = report(track_a_ledger_json(), track_a_assessment_json())
    dense = report(json.dumps(dense_ledger()), json.dumps(dense_assessment()))
    outputs = {
        "synthetic_onepage.pdf": render_one_page(standard),
        "synthetic_dense_long_name.pdf": render_one_page(dense),
        "synthetic_public.pdf": render_one_page(standard, public=True),
    }
    for name, result in outputs.items():
        (out / name).write_bytes(result.pdf)
        with pymupdf.open(stream=result.pdf, filetype="pdf") as doc:
            doc[0].get_pixmap(dpi=110).save(str(out / name.replace(".pdf", ".png")))
        print(f"{name}: {result.pages} page, {result.words} words, {result.body_size:g} pt body, wording level {result.level}")
    (out / "synthetic_full_report.pdf").write_bytes(render_full_report(standard))
    print(f"Wrote samples to {out}")


if __name__ == "__main__":
    main()
