"""Upload validation, isolated temporary workspaces, and extraction dispatch.

Uploaded bytes are written to a fresh temporary directory under a neutral name,
processed, and the directory is removed before this module returns - nothing
from the deck persists on disk. Only extracted text and in-memory page images
are kept, in the caller's session.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ten_screener.config import Settings
from ten_screener.errors import ExtractionError, FileValidationError
from ten_screener.extraction import convert, pdf_reader, pptx_reader, render
from ten_screener.schemas import ExtractedPage, ExtractionIssue, ExtractionResult

LOGGER = logging.getLogger(__name__)

ALLOWED_TYPES = {".pdf": "pdf", ".pptx": "pptx", ".ppt": "ppt"}
_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE compound file: legacy .ppt, or an encrypted Office file

#: Text in a deck that looks like an attempt to instruct the analysing model. It is
#: never obeyed (the deck is passed as untrusted data); it is surfaced to the user.
_INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the |all )?(previous|prior|above)"
    r"|you are now|system prompt|as an ai (language )?model|rate this (company|deck) (as )?(a )?(10|strong)"
    r"|assign (a )?(score|rating) of|override (the )?(scoring|instructions))",
    re.IGNORECASE,
)


def safe_display_name(filename: str) -> str:
    name = Path(filename or "deck").name
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip() or "deck"
    return name[:120]


def validate_upload(filename: str, data: bytes, max_mb: int) -> str:
    """Return the file type, or raise ``FileValidationError`` with an actionable message."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise FileValidationError(
            f"Unsupported file type '{ext or 'none'}'. Upload a pitch deck as PDF, PPTX or PPT."
        )
    if not data:
        raise FileValidationError("The uploaded file is empty (0 bytes).")
    size_mb = len(data) / (1024 * 1024)
    if size_mb > max_mb:
        raise FileValidationError(
            f"The file is {size_mb:.1f} MB, above the {max_mb} MB limit. Compress images or export a smaller PDF."
        )
    file_type = ALLOWED_TYPES[ext]
    head = data[:2048]
    if file_type == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise FileValidationError("The file has a .pdf extension but is not a PDF document.")
    elif file_type == "pptx":
        if head.startswith(_CFB_MAGIC):
            raise FileValidationError(
                "This .pptx appears to be password-protected (encrypted Office files are stored in a different "
                "container), or it is a legacy .ppt renamed to .pptx. Remove the password and save as .pptx or PDF."
            )
        if not head.startswith(b"PK") or not _is_pptx_package(data):
            raise FileValidationError(
                "The file has a .pptx extension but is not a readable PowerPoint package (it may be corrupt). "
                "Re-save it from PowerPoint as .pptx or export a PDF."
            )
    elif file_type == "ppt":
        if not head.startswith(_CFB_MAGIC):
            raise FileValidationError("The file has a .ppt extension but is not a legacy PowerPoint file.")
    return file_type


@contextmanager
def isolated_workspace() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="ten_screen_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def extract_upload(filename: str, data: bytes, settings: Settings, *, visual: bool = True) -> ExtractionResult:
    display_name = safe_display_name(filename)
    file_type = validate_upload(display_name, data, settings.max_upload_mb)
    issues: list[ExtractionIssue] = []
    images: dict[int, bytes] = {}
    converted = False

    with isolated_workspace() as workdir:
        source = workdir / f"deck.{file_type}"
        source.write_bytes(data)

        if file_type == "pdf":
            pages, ocr_ok, warnings = pdf_reader.extract_pdf(source, ocr_language=settings.ocr_language)
            issues.extend(ExtractionIssue(severity="warning", message=w) for w in warnings)
            _check_page_limit(pages, settings)
            if visual and settings.max_visual_pages > 0:
                chosen = render.choose_pages(pages, settings.max_visual_pages)
                images = render.render_pdf_pages(source, {n: n - 1 for n in chosen}, settings.visual_width_px)
            label_kind = "PDF page"
        else:
            ocr_ok = False
            pptx_path = source
            if file_type == "ppt":
                pptx_path = convert.convert(source, "pptx", workdir)
                converted = True
                issues.append(ExtractionIssue(severity="info", message="Legacy .ppt was converted to .pptx with LibreOffice before extraction."))
            pages = pptx_reader.extract_pptx(pptx_path)
            _check_page_limit(pages, settings)
            if visual and settings.max_visual_pages > 0:
                images, visual_issue = _render_slides(pptx_path, pages, settings, workdir)
                if visual_issue:
                    issues.append(visual_issue)
            label_kind = "Slide"

    result = ExtractionResult(
        filename=display_name,
        file_type=file_type,  # type: ignore[arg-type]
        page_label_kind=label_kind,  # type: ignore[arg-type]
        pages=pages,
        issues=issues,
        ocr_available=ocr_ok,
        visual_inspection_available=bool(images),
        page_images=images,
        converted_from_ppt=converted,
    )
    assess_quality(result, visual_requested=visual)
    LOGGER.info("extracted %s file: %d pages, %d chars", file_type, result.page_count, result.total_chars)
    return result


def _check_page_limit(pages: list[ExtractedPage], settings: Settings) -> None:
    if len(pages) > settings.max_pages:
        raise FileValidationError(
            f"The deck has {len(pages)} pages, above the {settings.max_pages}-page limit. "
            "Upload the main pitch deck rather than a full data room export."
        )


def _render_slides(
    pptx_path: Path, pages: list[ExtractedPage], settings: Settings, workdir: Path
) -> tuple[dict[int, bytes], ExtractionIssue | None]:
    if not convert.find_soffice():
        return {}, ExtractionIssue(
            severity="warning",
            message="Slide images could not be rendered (LibreOffice not installed), so charts, images and layout "
            "were not visually inspected. Visual-design judgments are limited to extracted text.",
        )
    try:
        pdf_path = convert.convert(pptx_path, "pdf", workdir)
    except ExtractionError as exc:
        return {}, ExtractionIssue(severity="warning", message=f"Slide rendering failed: {exc.user_message} Visual inspection skipped.")

    import pymupdf

    with pymupdf.open(str(pdf_path)) as doc:
        pdf_pages = doc.page_count
    visible = [p.number for p in pages if not p.hidden]
    if pdf_pages == len(pages):
        mapping_all = {p.number: i for i, p in enumerate(pages)}
    elif pdf_pages == len(visible):
        mapping_all = {n: i for i, n in enumerate(visible)}
    else:
        return {}, ExtractionIssue(
            severity="warning",
            message=f"Rendered slide count ({pdf_pages}) did not match the deck ({len(pages)} slides), so rendered "
            "images could not be matched to slide numbers safely. Visual inspection skipped.",
        )
    chosen = set(render.choose_pages([p for p in pages if p.number in mapping_all], settings.max_visual_pages))
    mapping = {n: i for n, i in mapping_all.items() if n in chosen}
    return render.render_pdf_pages(pdf_path, mapping, settings.visual_width_px), None


def assess_quality(result: ExtractionResult, *, visual_requested: bool) -> None:
    """Flag pages needing review and summarise extraction limitations. Mutates ``result``."""
    low_pages: list[int] = []
    for page in result.pages:
        if page.char_count < pdf_reader.LOW_TEXT_CHARS and not page.tables:
            page.needs_review = True
            seen = " A rendered image was supplied for visual reading." if page.number in result.page_images else ""
            page.review_reason = page.review_reason or (
                ("Little or no extractable text (likely scanned or image-only)." if not page.has_images
                 else "Content appears to be mostly images or charts.") + seen
            )
            low_pages.append(page.number)
        elif page.text_source == "ocr":
            page.needs_review = True
            page.review_reason = "Text obtained by OCR; check figures against the original."

    if result.total_chars < 200 and not any(p.tables for p in result.pages):
        result.issues.insert(
            0,
            ExtractionIssue(
                severity="error",
                message="Almost no text could be extracted. This does not mean the deck is empty: it is likely "
                "scanned or image-based. "
                + ("Rendered page images will be read visually, with lower citation reliability."
                   if result.page_images else
                   "Install Tesseract OCR or enable visual inspection, or upload a text-based export."),
                pages=[p.number for p in result.pages],
            ),
        )
    elif low_pages:
        result.issues.append(
            ExtractionIssue(
                severity="warning",
                message="Some pages have little or no extractable text and need review."
                + ("" if result.ocr_available else " Local OCR (Tesseract) is not installed."),
                pages=low_pages,
            )
        )
    hidden = [p.number for p in result.pages if p.hidden]
    if hidden:
        result.issues.append(ExtractionIssue(severity="info", message="Hidden slides are present; their content is labeled as hidden.", pages=hidden))
    with_notes = [p.number for p in result.pages if p.notes]
    if with_notes:
        result.issues.append(ExtractionIssue(severity="info", message="Speaker notes were found; evidence from notes is labeled separately from visible slide content.", pages=with_notes))
    if visual_requested and not result.page_images and not any("visual" in i.message.lower() for i in result.issues):
        result.issues.append(ExtractionIssue(severity="warning", message="Visual inspection is unavailable; no visual-design judgments will be made."))
    elif result.page_images and len(result.page_images) < result.page_count:
        missing = [p.number for p in result.pages if p.number not in result.page_images]
        result.issues.append(ExtractionIssue(severity="info", message=f"Only {len(result.page_images)} of {result.page_count} pages were rendered for visual inspection (TEN_MAX_VISUAL_PAGES).", pages=missing))

    flagged = [p.number for p in result.pages if _INJECTION_PATTERNS.search(p.text + "\n" + p.notes)]
    if flagged:
        result.issues.append(
            ExtractionIssue(
                severity="warning",
                message="The deck contains text resembling instructions to an AI system. It is treated strictly as "
                "deck content and does not alter the screening instructions.",
                pages=flagged,
            )
        )


def _is_pptx_package(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return "ppt/presentation.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False
