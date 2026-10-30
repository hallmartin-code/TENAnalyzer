"""Evidence handling: deck serialisation for the model, and citation verification.

Every excerpt Claude cites is checked against the extracted text of the page it
names. Outcomes:

* ``verified``     - the normalised excerpt occurs on the cited page.
* ``approximate``  - nearly all excerpt words occur on the cited page (OCR noise, line breaks).
* ``relocated``    - the excerpt occurs on a different page; the citation is corrected.
* ``not_found``    - the excerpt does not occur anywhere in the extracted text.
* ``page_out_of_range`` - the cited page does not exist.
* ``visual_unverifiable`` - cited from a rendered image; text verification is impossible.

A "Disclosed in deck" item left with no usable source is downgraded to "Analyst
inference", so an unlocatable figure can never pass as a deck fact.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ten_screener.schemas import (
    EvidenceItem,
    EvidenceStatus,
    ExtractionResult,
    LedgerOutput,
    SourceRef,
)

_WRAPPER_TAGS = re.compile(
    r"<(/?)(deck|page|slide_text|speaker_notes|tables|extraction_note|user_context|external_research|ledger)\b",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^0-9a-z$%€£.]+")
_TRAILING_DOTS = re.compile(r"(?<![0-9])\.|\.(?![0-9])")


def neutralise_tags(text: str) -> str:
    """Stop deck text from closing or opening the XML-style wrappers the prompt uses."""
    return _WRAPPER_TAGS.sub(lambda m: "‹" + m.group(1) + m.group(2), text)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = _NON_WORD.sub(" ", text)
    text = _TRAILING_DOTS.sub(" ", text)
    return " ".join(text.split())


def _page_corpus(result: ExtractionResult) -> dict[int, dict[str, str]]:
    corpus: dict[int, dict[str, str]] = {}
    for page in result.pages:
        table_text = "\n".join(" | ".join(row) for table in page.tables for row in table)
        corpus[page.number] = {
            "slide_text": normalise(page.text + "\n" + table_text),
            "speaker_notes": normalise(page.notes),
        }
    return corpus


def _matches(excerpt_norm: str, haystack: str) -> str | None:
    if not excerpt_norm or not haystack:
        return None
    if excerpt_norm in haystack:
        return "verified"
    words = excerpt_norm.split()
    if len(words) >= 4:
        hay_counts = Counter(haystack.split())
        need = Counter(words)
        present = sum(min(c, hay_counts.get(w, 0)) for w, c in need.items())
        if present / len(words) >= 0.85:
            return "approximate"
    return None


def verify_source(src: SourceRef, corpus: dict[int, dict[str, str]]) -> SourceRef:
    if src.page not in corpus:
        return src.model_copy(update={"verification": "page_out_of_range"})
    if src.kind == "visual":
        return src.model_copy(update={"verification": "visual_unverifiable"})
    excerpt_norm = normalise(src.excerpt)
    if len(excerpt_norm) < 3:
        return src.model_copy(update={"verification": "not_found"})
    field = "speaker_notes" if src.kind == "speaker_notes" else "slide_text"
    outcome = _matches(excerpt_norm, corpus[src.page][field])
    if outcome:
        return src.model_copy(update={"verification": outcome})
    # Cited text may sit in the other field of the same page (notes vs visible text).
    other = "slide_text" if field == "speaker_notes" else "speaker_notes"
    outcome = _matches(excerpt_norm, corpus[src.page][other])
    if outcome:
        return src.model_copy(update={"verification": outcome, "kind": other})
    for page_no, fields in corpus.items():
        for name in ("slide_text", "speaker_notes"):
            if _matches(excerpt_norm, fields[name]) == "verified":
                return src.model_copy(
                    update={"verification": "relocated", "page": page_no, "original_page": src.page, "kind": name}
                )
    return src.model_copy(update={"verification": "not_found"})


def verify_ledger(ledger: LedgerOutput, result: ExtractionResult) -> dict[str, int]:
    """Verify all citations in place. Returns counts by verification outcome."""
    corpus = _page_corpus(result)
    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for index, item in enumerate(ledger.evidence):
        if not item.id or item.id in seen_ids:
            item.id = f"E{index + 1}x"
        seen_ids.add(item.id)
        item.sources = [verify_source(s, corpus) for s in item.sources]
        for s in item.sources:
            counts[s.verification] += 1
        _apply_downgrades(item)
    return dict(counts)


def _apply_downgrades(item: EvidenceItem) -> None:
    bad = [s for s in item.sources if s.verification in ("not_found", "page_out_of_range")]
    relocated = [s for s in item.sources if s.verification == "relocated"]
    notes: list[str] = []
    if relocated:
        notes.append(
            "Citation corrected: excerpt found on page "
            + ", ".join(f"{s.page} (cited as {s.original_page})" for s in relocated)
        )
    if bad:
        notes.append(f"{len(bad)} cited excerpt(s) could not be located in the extracted text")
    if item.status in (EvidenceStatus.DISCLOSED, EvidenceStatus.CONTRADICTORY) and not item.is_supported:
        if item.status == EvidenceStatus.DISCLOSED:
            item.status = EvidenceStatus.INFERENCE
        notes.append("no source cited" if not item.sources else "not confirmed against the deck text; treat as unverified")
    if notes:
        item.citation_note = "; ".join(notes)


def supported(ledger: LedgerOutput, evidence_ids: list[str]) -> bool:
    """True when at least one referenced evidence item survived verification."""
    by_id = {e.id: e for e in ledger.evidence}
    return any(by_id[i].is_supported for i in evidence_ids if i in by_id)


def drop_unknown_ids(ids: list[str], known: set[str]) -> list[str]:
    return [i for i in ids if i in known]


def serialise_deck(result: ExtractionResult) -> str:
    """Deck text with explicit page boundaries, labels and source kinds. All deck text is neutralised."""
    lines = [
        f'<deck filename="{neutralise_tags(result.filename)}" file_type="{result.file_type}" '
        f'page_label_kind="{result.page_label_kind}" page_count="{result.page_count}">'
    ]
    for page in result.pages:
        attrs = f'number="{page.number}" label="{page.label}" text_source="{page.text_source}"'
        if page.hidden:
            attrs += ' hidden="true"'
        lines.append(f"<page {attrs}>")
        lines.append("<slide_text>")
        lines.append(neutralise_tags(page.text) if page.text.strip() else "[no extractable text]")
        lines.append("</slide_text>")
        if page.tables:
            lines.append("<tables>")
            for t_index, table in enumerate(page.tables, start=1):
                lines.append(f"Table {t_index}:")
                lines.extend(neutralise_tags(" | ".join(row)) for row in table)
            lines.append("</tables>")
        if page.notes:
            lines.append("<speaker_notes>")
            lines.append(neutralise_tags(page.notes))
            lines.append("</speaker_notes>")
        if page.needs_review:
            lines.append(f"<extraction_note>{page.review_reason or 'Needs review'}</extraction_note>")
        lines.append("</page>")
    lines.append("</deck>")
    return "\n".join(lines)
