"""Fonts, the default palette and shared page decorations.

The navy / teal / white palette is a restrained *default*, not verified TEN
Capital brand guidance; change ``PALETTE`` to apply official brand colours.
The footer follows the TEN Capital document standard in CLAUDE.md:
``[Document Title]  [PAGE#]  Compiled on [DATE] by TEN Capital Network  [logo]``
in Open Sans 7 pt, centred.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ten_screener.config import DEFAULT_FOOTER_LOGO, FONT_DIR

LOGGER = logging.getLogger(__name__)

PALETTE = {
    "navy": HexColor("#0B2545"),
    "navy_soft": HexColor("#13315C"),
    "teal": HexColor("#11807F"),
    "teal_light": HexColor("#E3F2F1"),
    "teal_mid": HexColor("#9CCFCC"),
    "ink": HexColor("#1D2733"),
    "muted": HexColor("#56657A"),
    "rule": HexColor("#C8D3DD"),
    "panel": HexColor("#F3F6F9"),
    "white": white,
}

FIT_COLOURS = {
    "Strong Fit": HexColor("#0E7C66"),
    "Moderate Fit": HexColor("#11807F"),
    "Weak Fit": HexColor("#8A6D1F"),
    "Likely Pass": HexColor("#8C2F39"),
}

_FONT_FILES = {
    "OpenSans": "OpenSans-Regular.ttf",
    "OpenSans-SemiBold": "OpenSans-SemiBold.ttf",
    "OpenSans-Bold": "OpenSans-Bold.ttf",
    "OpenSans-Italic": "OpenSans-Italic.ttf",
}
_FALLBACK = {
    "OpenSans": "Helvetica",
    "OpenSans-SemiBold": "Helvetica-Bold",
    "OpenSans-Bold": "Helvetica-Bold",
    "OpenSans-Italic": "Helvetica-Oblique",
}


@dataclass(frozen=True)
class Fonts:
    regular: str
    semibold: str
    bold: str
    italic: str


_fonts: Fonts | None = None


def fonts() -> Fonts:
    global _fonts
    if _fonts is not None:
        return _fonts
    resolved: dict[str, str] = {}
    for name, filename in _FONT_FILES.items():
        path = FONT_DIR / filename
        try:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
            resolved[name] = name
        except Exception as exc:  # noqa: BLE001 - missing asset degrades to Helvetica
            LOGGER.warning("font %s unavailable (%s); using %s", filename, exc.__class__.__name__, _FALLBACK[name])
            resolved[name] = _FALLBACK[name]
    if resolved["OpenSans"] == "OpenSans":
        from reportlab.lib.fonts import addMapping

        addMapping("OpenSans", 0, 0, resolved["OpenSans"])
        addMapping("OpenSans", 1, 0, resolved["OpenSans-Bold"])
        addMapping("OpenSans", 0, 1, resolved["OpenSans-Italic"])
        addMapping("OpenSans", 1, 1, resolved["OpenSans-Bold"])
    _fonts = Fonts(resolved["OpenSans"], resolved["OpenSans-SemiBold"], resolved["OpenSans-Bold"], resolved["OpenSans-Italic"])
    return _fonts


def image_reader(data: bytes | None) -> ImageReader | None:
    if not data:
        return None
    try:
        return ImageReader(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - an unreadable logo is skipped, never fatal
        return None


def footer_logo() -> ImageReader | None:
    try:
        return ImageReader(str(DEFAULT_FOOTER_LOGO)) if DEFAULT_FOOTER_LOGO.exists() else None
    except Exception:  # noqa: BLE001
        return None


def compiled_date(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso_date


def draw_footer(canvas, doc_title: str, page_number: int, iso_date: str, page_width: float, y: float = 22) -> None:  # noqa: ANN001
    """The single-line, centred TEN Capital footer (Open Sans 7 pt + inline logo)."""
    f = fonts()
    size = 7
    left = f" {doc_title}"
    middle = str(page_number)
    right = f"Compiled on {compiled_date(iso_date)} by TEN Capital Network"
    gap = 22
    logo = footer_logo()
    logo_w, logo_h = (48.4, 18.0) if logo else (0, 0)  # 0.67" x 0.25"
    widths = [pdfmetrics.stringWidth(t, f.regular, size) for t in (left, middle, right)]
    total = sum(widths) + gap * 2 + ((gap / 2 + logo_w) if logo else 0)
    x = (page_width - total) / 2
    canvas.saveState()
    canvas.setFont(f.regular, size)
    canvas.setFillColor(PALETTE["muted"])
    for text, width in zip((left, middle, right), widths):
        canvas.drawString(x, y, text)
        x += width + gap
    if logo:
        canvas.drawImage(logo, x - gap / 2, y - 6, width=logo_w, height=logo_h, mask="auto", preserveAspectRatio=True)
    canvas.restoreState()
