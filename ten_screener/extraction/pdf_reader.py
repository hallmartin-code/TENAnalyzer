"""PDF text and table extraction with PyMuPDF, page by page, with optional local OCR.

Citations use the PDF page index ("PDF p. N"), never a printed slide number,
because the two frequently disagree (cover pages, appendix numbering, merged decks).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pymupdf

from ten_screener.errors import ExtractionError
from ten_screener.schemas import ExtractedPage

LOGGER = logging.getLogger(__name__)

#: Below this many characters a page is treated as having no usable text layer.
LOW_TEXT_CHARS = 40

_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
)


def tesseract_available() -> bool:
    """OCR via PyMuPDF needs a local Tesseract install with language data."""
    if shutil.which("tesseract"):
        return True
    return any(Path(p).exists() for p in _TESSERACT_CANDIDATES)


def _tessdata_dir() -> str | None:
    if os.environ.get("TESSDATA_PREFIX"):
        return os.environ["TESSDATA_PREFIX"]
    exe = shutil.which("tesseract") or next((p for p in _TESSERACT_CANDIDATES if Path(p).exists()), None)
    if exe:
        candidate = Path(exe).resolve().parent / "tessdata"
        if candidate.exists():
            return str(candidate)
    for candidate in ("/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata", "/usr/share/tessdata"):
        if Path(candidate).exists():
            return candidate
    return None


def open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:  # noqa: BLE001 - any parser failure means unreadable
        raise ExtractionError(
            "The PDF could not be opened. It may be corrupt or not a real PDF. "
            "Re-export it from the original application and upload again.",
            detail=str(exc),
        ) from exc
    if doc.needs_pass and not doc.authenticate(""):
        doc.close()
        raise ExtractionError(
            "The PDF is password-protected. Remove the password (or export an unprotected copy) and upload again."
        )
    return doc


def extract_pdf(path: Path, *, ocr_language: str = "eng") -> tuple[list[ExtractedPage], bool, list[str]]:
    """Return pages, whether OCR was available, and per-page warnings."""
    doc = open_pdf(path)
    ocr_ok = tesseract_available()
    tessdata = _tessdata_dir() if ocr_ok else None
    warnings: list[str] = []
    pages: list[ExtractedPage] = []
    try:
        if doc.page_count == 0:
            raise ExtractionError("The PDF contains no pages.")
        for index in range(doc.page_count):
            number = index + 1
            try:
                page = doc.load_page(index)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"PDF p. {number} could not be loaded ({exc.__class__.__name__}).")
                pages.append(
                    ExtractedPage(number=number, label=f"PDF p. {number}", text_source="none",
                                  needs_review=True, review_reason="Page could not be parsed")
                )
                continue
            text = _safe_text(page)
            text_source = "text_layer" if text.strip() else "none"
            has_images = _has_images(page)
            if len(text.strip()) < LOW_TEXT_CHARS and ocr_ok:
                ocr_text = _ocr_page(page, ocr_language, tessdata)
                if len(ocr_text.strip()) > len(text.strip()):
                    text, text_source = ocr_text, "ocr"
            pages.append(
                ExtractedPage(
                    number=number,
                    label=f"PDF p. {number}",
                    text=text.strip(),
                    tables=_tables(page),
                    text_source=text_source,
                    has_images=has_images,
                )
            )
    finally:
        doc.close()
    return pages, ocr_ok, warnings


def _safe_text(page: pymupdf.Page) -> str:
    try:
        return page.get_text("text", sort=True) or ""
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("text extraction failed: %s", exc.__class__.__name__)
        return ""


def _has_images(page: pymupdf.Page) -> bool:
    """Embedded images, or enough vector drawing to suggest a chart or diagram."""
    try:
        if page.get_images(full=False):
            return True
        return len(page.get_drawings()) > 40
    except Exception:  # noqa: BLE001
        return False


def _tables(page: pymupdf.Page) -> list[list[list[str]]]:
    out: list[list[list[str]]] = []
    try:
        finder = page.find_tables()
        for table in finder.tables[:6]:
            rows = [[(cell or "").strip() for cell in row] for row in table.extract()]
            rows = [r for r in rows if any(r)]
            if len(rows) >= 2:
                out.append(rows)
    except Exception as exc:  # noqa: BLE001 - table detection is best-effort
        LOGGER.debug("table detection failed: %s", exc.__class__.__name__)
    return out


def _ocr_page(page: pymupdf.Page, language: str, tessdata: str | None) -> str:
    try:
        kwargs = {"language": language, "dpi": 300, "full": True}
        if tessdata:
            kwargs["tessdata"] = tessdata
        textpage = page.get_textpage_ocr(**kwargs)
        return page.get_text("text", textpage=textpage, sort=True) or ""
    except Exception as exc:  # noqa: BLE001 - OCR failure leaves the page flagged for review
        LOGGER.info("OCR failed on a page: %s", exc.__class__.__name__)
        return ""
