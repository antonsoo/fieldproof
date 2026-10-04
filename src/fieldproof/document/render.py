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

from fieldproof.document.limits import check_page_pixels


def render_page_png(
    source: str | Path | bytes,
    page_number: int,
    *,
    scale: float = 2.0,
    max_pixels: int | None = None,
) -> bytes:
    """Render one page (1-indexed) to PNG bytes at `scale` * 72 DPI.

    `scale=2.0` (the default) gives 144 DPI, which is sharp enough to read
    small print on screen without producing huge files.
    """
    pdf = pdfium.PdfDocument(source)
    page = bitmap = pil_image = None
    try:
        page = pdf[page_number - 1]
        if max_pixels is not None:
            width, height = page.get_size()
            check_page_pixels(width, height, scale, max_pixels)
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        if pil_image is not None:
            pil_image.close()
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        pdf.close()


def page_pixel_size(
    source: str | Path | bytes, page_number: int, *, scale: float = 2.0
) -> tuple[int, int]:
    """Return the (width, height) in pixels the rendered PNG will have,
    without re-rendering - used by the UI to map PDF points to pixels."""
    pdf = pdfium.PdfDocument(source)
    page = None
    try:
        page = pdf[page_number - 1]
        width_pt, height_pt = page.get_size()
        return round(width_pt * scale), round(height_pt * scale)
    finally:
        if page is not None:
            page.close()
        pdf.close()
