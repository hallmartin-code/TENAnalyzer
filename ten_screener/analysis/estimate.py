"""Stage and regulatory-pathway estimate, used when the deck alone cannot settle the stage gate.

Rather than reporting "Cannot Determine", the screener looks the company up (FDA
510(k) / De Novo / PMA / registration databases for Track B, funding and customer
announcements for Track A) and asks Claude for a committed, confidence-rated estimate
grounded in the deck, the uploaded context and the cited search results. Only the
company's public identity is sent as search context - never deck figures or
investor information. The estimate is always labeled as an estimate.
"""

from __future__ import annotations

import json
import logging

from ten_screener.analysis import prompts
from ten_screener.analysis.llm import ClaudeClient
from ten_screener.analysis.research import cited_search
from ten_screener.errors import AnalysisError
from ten_screener.schemas import ExternalFinding, GateResult, LedgerOutput, StageEstimate

LOGGER = logging.getLogger(__name__)


def run_estimate(
    client: ClaudeClient,
    ledger: LedgerOutput,
    gate: GateResult,
    deck_blocks: list[dict],
    retrieved_on: str,
) -> tuple[StageEstimate | None, list[ExternalFinding], list[str]]:
    company = ledger.company
    findings, notes = cited_search(
        client,
        prompts.stage_search_prompt(
            company.name or "the company", company.website, company.one_line_description,
            ledger.track.track, ledger.track_b.product_type if ledger.track_b else None,
        ),
        retrieved_on,
        id_prefix="S",
        label="Stage and FDA pathway search",
        max_uses=8,
    )
    facts = ledger.model_dump(
        mode="json", exclude_none=True,
        include={"company", "track", "track_a", "track_b", "current_raise", "financials", "funding_events", "evidence"},
    )
    try:
        estimate = client.generate_json(
            prompts.SYSTEM_PROMPT,
            [{
                "role": "user",
                "content": deck_blocks + [{
                    "type": "text",
                    "text": prompts.estimate_task(
                        json.dumps(facts), json.dumps(gate.model_dump(mode="json")),
                        json.dumps([f.model_dump(mode="json") for f in findings]),
                    ),
                }],
            }],
            StageEstimate,
            label="stage estimate",
        )
    except AnalysisError as exc:
        notes.append(f"Stage and FDA pathway estimate failed: {exc.user_message}")
        return None, findings, notes
    known = {e.id for e in ledger.evidence} | {f.id for f in findings}
    estimate.evidence_ids = [i for i in estimate.evidence_ids if i in known]
    return estimate, findings, notes
