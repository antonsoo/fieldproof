"""Render PDF pages to PNG images for the review UI.

Uses pypdfium2 (a Python binding to PDFium, the rendering engine behind
Chrome's PDF viewer) rather than pdfplumber's rendering path, which shells
out to Poppler's `pdftoppm` and is both slower and an extra system
dependency. pypdfium2 ships prebuilt wheels with the renderer statically
linked, so `pip install` is enough - no system PDF tooling required.
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium


def render_page_png(source: str | Path | bytes, page_number: int, *, scale: float = 2.0) -> bytes:
    """Render one page (1-indexed) to PNG bytes at `scale` * 72 DPI.

    `scale=2.0` (the default) gives 144 DPI, which is sharp enough to read
    small print on screen without producing huge files.
    """
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[page_number - 1]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        pdf.close()


def page_pixel_size(
    source: str | Path | bytes, page_number: int, *, scale: float = 2.0
) -> tuple[int, int]:
    """Return the (width, height) in pixels the rendered PNG will have,
    without re-rendering - used by the UI to map PDF points to pixels."""
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[page_number - 1]
        width_pt, height_pt = page.get_size()
        return round(width_pt * scale), round(height_pt * scale)
    finally:
        pdf.close()
