"""Render pages to compressed JPEG images for visual inspection by Claude."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

from ten_screener.schemas import ExtractedPage

LOGGER = logging.getLogger(__name__)


def choose_pages(pages: list[ExtractedPage], limit: int) -> list[int]:
    """All pages when within the limit; otherwise prioritise low-text and image-bearing pages, then deck order."""
    numbers = [p.number for p in pages]
    if len(numbers) <= limit:
        return numbers
    priority = [p.number for p in pages if p.char_count < 200 or p.has_images]
    chosen = priority[:limit]
    for n in numbers:
        if len(chosen) >= limit:
            break
        if n not in chosen:
            chosen.append(n)
    return sorted(chosen)


def render_pdf_pages(pdf_path: Path, page_map: dict[int, int], width_px: int) -> dict[int, bytes]:
    """Render PDF pages. ``page_map`` maps deck page/slide number -> 0-based PDF page index."""
    images: dict[int, bytes] = {}
    doc = pymupdf.open(str(pdf_path))
    try:
        for deck_page, pdf_index in page_map.items():
            if pdf_index >= doc.page_count:
                continue
            try:
                page = doc.load_page(pdf_index)
                zoom = min(3.0, width_px / max(page.rect.width, 1))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                images[deck_page] = pix.tobytes(output="jpg", jpg_quality=72)
            except Exception as exc:  # noqa: BLE001 - one bad page must not lose the rest
                LOGGER.info("render failed on a page: %s", exc.__class__.__name__)
    finally:
        doc.close()
    return images
