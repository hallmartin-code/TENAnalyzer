"""Error types. Each carries a user-facing message that is safe to show in the UI.

The ``stage`` attribute lets the interface distinguish processing failures
(file, extraction, API, rendering) from investment findings, which are never
raised as exceptions.
"""

from __future__ import annotations


class ScreenerError(Exception):
    stage = "processing"

    def __init__(self, user_message: str, *, detail: str | None = None, retryable: bool = False):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail
        self.retryable = retryable


class FileValidationError(ScreenerError):
    stage = "upload"


class ExtractionError(ScreenerError):
    stage = "extraction"


class ConfigurationError(ScreenerError):
    stage = "configuration"


class AnalysisError(ScreenerError):
    stage = "analysis"


class RenderError(ScreenerError):
    stage = "rendering"
