"""Optional OCR fallback for scanned (image-only) documents.

This module is only reached when `load_pdf` raises `EmptyDocumentError` -
i.e. the PDF has no text layer at all. It requires the `pytesseract` Python
package *and* the Tesseract binary on PATH; neither is a hard dependency of
fieldproof (see the `ocr` extra in pyproject.toml). Import this module
lazily and call `is_available()` before using it - do not add it to the
default install, since Tesseract is a system package with its own install
story per OS and pulling it in unconditionally would break `pip install
fieldproof` on machines without it.

OCR word boxes are visibly lower-precision than a native text layer:
Tesseract gives per-word pixel boxes at whatever DPI you render at, with no
sub-word offsets, and accuracy drops sharply on skewed scans, low contrast,
or unusual fonts. Treat OCR'd documents as a degraded mode - grounding still
works (it fuzzy-matches against whatever text OCR produced) but confidence
should be read as "OCR thinks this is what's there," not ground truth.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.document.render import render_page_png

#: Checked without importing either package, so `import fieldproof.document.ocr`
#: never fails on a machine that only has fieldproof's required dependencies.
_HAS_OCR_PACKAGES = (
    importlib.util.find_spec("pytesseract") is not None
    and importlib.util.find_spec("PIL") is not None
)


def is_available() -> bool:
    """True only if both the `pytesseract` package is importable and the
    Tesseract binary itself can be found on PATH."""
    if not _HAS_OCR_PACKAGES:
        return False
    import pytesseract

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def load_scanned_pdf(
    source: str | Path | bytes, page_count: int, *, label: str | None = None
) -> Document:
    """OCR every page of a PDF that has no text layer.

    Raises `RuntimeError` if OCR isn't available - callers should check
    `is_available()` first and give the user a clear message rather than
    let this raise from deep in a pipeline.
    """
    if not is_available():
        raise RuntimeError(
            "OCR is not available: install the 'ocr' extra (pytesseract, Pillow) "
            "and the Tesseract binary (e.g. `apt install tesseract-ocr`)."
        )

    import pytesseract
    from PIL import Image

    pages: list[Page] = []
    for page_number in range(1, page_count + 1):
        png_bytes = render_page_png(source, page_number, scale=2.0)
        image = Image.open(io.BytesIO(png_bytes))
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        pages.append(_page_from_ocr(page_number, image.width, image.height, data))

    return Document(
        source=label or (source if isinstance(source, str) else "<scanned>"), pages=pages
    )


def _page_from_ocr(page_number: int, width_px: int, height_px: int, data: dict) -> Page:
    # OCR renders at scale=2.0 (144 DPI); convert pixel boxes back to PDF
    # points (72 DPI) so they share the coordinate system with native pages.
    scale = 2.0
    text_parts: list[str] = []
    words: list[Word] = []
    cursor = 0
    n = len(data["text"])
    for i in range(n):
        token = data["text"][i].strip()
        if not token:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        if text_parts:
            text_parts.append(" ")
            cursor += 1
        start = cursor
        text_parts.append(token)
        cursor += len(token)
        words.append(
            Word(
                text=token,
                bbox=BBox(x0=x / scale, top=y / scale, x1=(x + w) / scale, bottom=(y + h) / scale),
                start=start,
                end=cursor,
            )
        )

    return Page(
        number=page_number,
        width=width_px / scale,
        height=height_px / scale,
        text="".join(text_parts),
        words=words,
    )
