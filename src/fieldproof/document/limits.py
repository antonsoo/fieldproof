"""Opt-in budgets for the local server's PDF intake and page rendering."""

from __future__ import annotations

import math
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium


class DocumentLimitError(ValueError):
    """A document exceeds a supported intake or rendering budget."""


@dataclass(frozen=True)
class DocumentLimits:
    max_pages: int = 64
    max_pixels: int = 16_000_000
    max_words: int = 100_000
    max_text_chars: int = 2_000_000


def check_page_pixels(width: float, height: float, scale: float, maximum: int) -> None:
    if not all(math.isfinite(n) and n > 0 for n in (width, height, scale)):
        raise DocumentLimitError("PDF page dimensions must be finite and positive")
    pixel_width, pixel_height = width * scale, height * scale
    if (
        not math.isfinite(pixel_width)
        or not math.isfinite(pixel_height)
        or math.ceil(pixel_width) * math.ceil(pixel_height) > maximum
    ):
        raise DocumentLimitError(f"PDF page exceeds the {maximum:,}-pixel rendering limit")


def check_pdf_geometry(source: str | Path | bytes, limits: DocumentLimits) -> None:
    """Inspect page metadata before pdfplumber creates per-page text objects."""
    with closing(pdfium.PdfDocument(source)) as pdf:
        if not 1 <= len(pdf) <= limits.max_pages:
            raise DocumentLimitError(f"PDF must contain between 1 and {limits.max_pages} pages")
        for number in range(len(pdf)):
            page = pdf[number]
            try:
                width, height = page.get_size()
                check_page_pixels(width, height, 2.0, limits.max_pixels)
            finally:
                page.close()
