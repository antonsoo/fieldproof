"""The local review server's explicit, bounded text-source choices."""

from __future__ import annotations

from typing import Literal, cast

TextMode = Literal["native", "ocr-missing", "ocr-all"]
TEXT_MODES = ("native", "ocr-missing", "ocr-all")
OCR_MAX_PAGES = 8
OCR_PAGE_TIMEOUT_SECONDS = 10.0


def text_mode(value: object) -> TextMode:
    if not isinstance(value, str) or value not in TEXT_MODES:
        raise ValueError("Text source must be native, ocr-missing or ocr-all")
    return cast(TextMode, value)
