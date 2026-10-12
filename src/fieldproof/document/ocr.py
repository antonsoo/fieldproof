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
import math
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium

from fieldproof.document.limits import DocumentLimitError, DocumentLimits, check_pdf_geometry
from fieldproof.document.loader import EmptyDocumentError
from fieldproof.document.model import BBox, Document, OcrProvenance, Page, Word
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
    source: str | Path | bytes,
    page_count: int | None = None,
    *,
    label: str | None = None,
    language: str = "eng",
    timeout: float = 30.0,
    limits: DocumentLimits | None = None,
) -> Document:
    """OCR every page of a PDF that has no text layer.

    The optional legacy `page_count` must match the PDF; it cannot silently
    truncate it. Each Tesseract process has a positive wall-clock timeout.
    Default geometry/text budgets match DocumentLimits. These are not a
    process sandbox or a timeout on the PDF renderer.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("OCR timeout must be finite and positive")
    if not language or any(not (ch.isascii() and (ch.isalnum() or ch in "_+")) for ch in language):
        raise ValueError(
            "OCR language must name installed Tesseract languages, e.g. eng or eng+fra"
        )
    if not is_available():
        raise RuntimeError(
            "OCR is not available: install the 'ocr' extra (pytesseract, Pillow) "
            "and the Tesseract binary (e.g. `apt install tesseract-ocr`)."
        )

    import pytesseract
    from PIL import Image

    limits = limits or DocumentLimits()
    check_pdf_geometry(source, limits)
    with closing(pdfium.PdfDocument(source)) as pdf:
        actual_pages = len(pdf)
    if page_count is not None and page_count != actual_pages:
        raise ValueError(
            f"OCR page_count {page_count} does not match the PDF's {actual_pages} pages"
        )
    version = str(pytesseract.get_tesseract_version())
    pages: list[Page] = []
    words = text_chars = 0
    for page_number in range(1, actual_pages + 1):
        png_bytes = render_page_png(source, page_number, scale=2.0, max_pixels=limits.max_pixels)
        with Image.open(io.BytesIO(png_bytes)) as image:
            try:
                data = pytesseract.image_to_data(
                    image, lang=language, timeout=timeout, output_type=pytesseract.Output.DICT
                )
            except (RuntimeError, OSError) as exc:
                raise RuntimeError(f"OCR failed on page {page_number}: {exc}") from exc
            page = _page_from_ocr(page_number, image.width, image.height, data)
        words += len(page.words)
        text_chars += len(page.text)
        if words > limits.max_words or text_chars > limits.max_text_chars:
            raise DocumentLimitError("OCR text exceeds the document word/character budget")
        pages.append(page)

    if not words:
        raise EmptyDocumentError("OCR recognized no words on any page; check the scan and language")

    return Document(
        source=label or (str(source) if isinstance(source, str | Path) else "<scanned>"),
        pages=pages,
        ocr=OcrProvenance(
            engine="tesseract",
            version=version,
            language=language,
            render_dpi=144,
            page_count=actual_pages,
            empty_pages=[page.number for page in pages if not page.words],
        ),
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
