"""PowerPoint (.pptx) extraction: slide text, tables, charts and speaker notes, in slide order.

Speaker notes are kept in their own field so that evidence drawn from them can be
labeled as notes rather than as visible slide content.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from ten_screener.errors import ExtractionError
from ten_screener.schemas import ExtractedPage

LOGGER = logging.getLogger(__name__)


def extract_pptx(path: Path) -> list[ExtractedPage]:
    try:
        from pptx import Presentation
        from pptx.exc import PackageNotFoundError
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise ExtractionError("python-pptx is not installed; PowerPoint files cannot be read.") from exc

    if not zipfile.is_zipfile(path):
        raise ExtractionError(
            "The file is not a valid .pptx package. It may be password-protected, corrupt, or a legacy .ppt "
            "renamed to .pptx. Open it in PowerPoint, remove any password, and save as .pptx or PDF."
        )
    try:
        presentation = Presentation(str(path))
    except PackageNotFoundError as exc:
        raise ExtractionError("The .pptx file could not be opened as a presentation.", detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(
            "The .pptx file is corrupt or uses features that could not be parsed. Save it again as .pptx or PDF.",
            detail=str(exc),
        ) from exc

    pages: list[ExtractedPage] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        tables: list[list[list[str]]] = []
        has_images = False
        for shape in _ordered_shapes(slide.shapes):
            texts.extend(_shape_text(shape))
            table = _shape_table(shape)
            if table:
                tables.append(table)
            has_images = has_images or _is_visual(shape)
        hidden = slide._element.get("show") == "0"  # noqa: SLF001 - python-pptx has no public accessor
        pages.append(
            ExtractedPage(
                number=index,
                label=f"Slide {index}",
                text="\n".join(t for t in texts if t.strip()),
                tables=tables,
                notes=_slide_notes(slide),
                text_source="text_layer" if any(t.strip() for t in texts) else "none",
                has_images=has_images,
                hidden=hidden,
            )
        )
    if not pages:
        raise ExtractionError("The presentation contains no slides.")
    return pages


def _ordered_shapes(shapes):  # noqa: ANN001, ANN202
    """Top-to-bottom, left-to-right reading order; shapes without a position keep their z-order."""
    def key(shape):  # noqa: ANN001, ANN202
        top = getattr(shape, "top", None)
        left = getattr(shape, "left", None)
        return (top if top is not None else 0, left if left is not None else 0)

    try:
        return sorted(list(shapes), key=key)
    except Exception:  # noqa: BLE001
        return list(shapes)


def _shape_text(shape) -> list[str]:  # noqa: ANN001
    out: list[str] = []
    try:
        if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
            out.append(shape.text_frame.text.strip())
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("shape text unreadable: %s", exc.__class__.__name__)
    try:
        if getattr(shape, "has_chart", False):
            out.extend(_chart_text(shape.chart))
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("chart unreadable: %s", exc.__class__.__name__)
    try:
        if hasattr(shape, "shapes"):  # group shape
            for child in _ordered_shapes(shape.shapes):
                out.extend(_shape_text(child))
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("group unreadable: %s", exc.__class__.__name__)
    return out


def _chart_text(chart) -> list[str]:  # noqa: ANN001
    out: list[str] = []
    try:
        if chart.has_title and chart.chart_title.text_frame.text.strip():
            out.append("[Chart] " + chart.chart_title.text_frame.text.strip())
    except Exception:  # noqa: BLE001
        pass
    try:
        categories = [str(c) for c in chart.plots[0].categories if c is not None]
        if categories:
            out.append("[Chart categories] " + " | ".join(categories))
    except Exception:  # noqa: BLE001
        pass
    try:
        for series in chart.series:
            values = [v for v in (getattr(series, "values", None) or []) if v is not None]
            rendered = ", ".join(f"{v:g}" for v in values[:16])
            out.append(f"[Chart series] {series.name}: {rendered}" if rendered else f"[Chart series] {series.name}")
    except Exception:  # noqa: BLE001
        pass
    return out


def _shape_table(shape) -> list[list[str]] | None:  # noqa: ANN001
    try:
        if not getattr(shape, "has_table", False):
            return None
        rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
        rows = [r for r in rows if any(r)]
        return rows or None
    except Exception:  # noqa: BLE001
        return None


def _is_visual(shape) -> bool:  # noqa: ANN001
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        return shape.shape_type in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.CHART) or getattr(shape, "has_chart", False)
    except Exception:  # noqa: BLE001
        return False


def _slide_notes(slide) -> str:  # noqa: ANN001
    try:
        if slide.has_notes_slide:
            return (slide.notes_slide.notes_text_frame.text or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""
