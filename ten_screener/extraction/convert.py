"""Format conversion through a locally installed LibreOffice (``soffice``).

Used for legacy .ppt -> .pptx and for rendering .pptx slides (via PDF) for visual
inspection. Each conversion runs with its own throwaway LibreOffice profile so
concurrent runs never contend for the user's profile lock.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ten_screener.errors import ExtractionError

LOGGER = logging.getLogger(__name__)

_SOFFICE_CANDIDATES = (
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)

TIMEOUT_SECONDS = 180

PPT_HELP = (
    "Legacy .ppt files need LibreOffice for conversion, and it was not found on this machine. "
    "Either install LibreOffice (https://www.libreoffice.org) so 'soffice' is available, or open the deck "
    "in PowerPoint / Keynote / Google Slides and use File > Save As (or Download) to save it as .pptx or PDF."
)


def find_soffice() -> str | None:
    for candidate in _SOFFICE_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if Path(candidate).exists():
            return candidate
    return None


def convert(source: Path, target_ext: str, workdir: Path) -> Path:
    """Convert ``source`` to ``target_ext`` ("pptx" or "pdf") inside ``workdir``."""
    soffice = find_soffice()
    if not soffice:
        raise ExtractionError(PPT_HELP)
    outdir = workdir / f"converted_{target_ext}"
    profile = workdir / "lo_profile"
    outdir.mkdir(exist_ok=True)
    profile.mkdir(exist_ok=True)
    cmd = [
        soffice,
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--headless",
        "--norestore",
        "--convert-to",
        target_ext,
        "--outdir",
        str(outdir),
        str(source),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(f"LibreOffice conversion to .{target_ext} timed out.") from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ExtractionError(
            f"LibreOffice could not convert the file to .{target_ext}. The file may be corrupt or "
            "password-protected; save it as .pptx or PDF and try again.",
            detail=exc.__class__.__name__,
        ) from exc
    produced = next(iter(outdir.glob(f"*.{target_ext}")), None)
    if produced is None:
        raise ExtractionError(f"LibreOffice produced no .{target_ext} output.")
    return produced
