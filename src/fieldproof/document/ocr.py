"""Optional OCR fallback for scanned (image-only) documents.

The CLI's default fallback reaches this module when `load_pdf` raises
`EmptyDocumentError`. Opt-in `load_pdf_with_ocr` also recognizes pages without
native words inside a mixed document, preserving every native-text page.
It requires the `pytesseract` Python
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
from typing import Literal

import pypdfium2 as pdfium

from fieldproof.document.limits import DocumentLimitError, DocumentLimits, check_pdf_geometry
from fieldproof.document.loader import EmptyDocumentError, load_pdf
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
    """OCR every rendered page, without consulting a native text layer.

    The optional legacy `page_count` must match the PDF; it cannot silently
    truncate it. Each Tesseract process has a positive wall-clock timeout.
    Default geometry/text budgets match DocumentLimits. These are not a
    process sandbox or a timeout on the PDF renderer.
    """
    _validate_options(language, timeout)
    _require_engine()

    import pytesseract

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
        page = _recognize_page(source, page_number, language, timeout, limits)
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


def load_pdf_with_ocr(
    source: str | Path | bytes,
    *,
    label: str | None = None,
    language: str = "eng",
    timeout: float = 30.0,
    limits: DocumentLimits | None = None,
    mode: Literal["missing", "all"] = "missing",
) -> Document:
    """Recognize missing pages, or explicitly replace every page with OCR text.

    The default keeps native pages and does not detect a partial, incorrect or
    invisible text layer on them. Mode "all" reads only rendered appearances,
    including saved form values, and does not merge duplicate native words.
    Blank pages retain their positions and are named in the OCR provenance.
    In the default mode, native-only documents need no OCR dependency or engine.
    Limits apply to the resulting document's text.
    """
    if mode not in ("missing", "all"):
        raise ValueError("OCR mode must be 'missing' or 'all'")
    _validate_options(language, timeout)
    if mode == "all":
        document = load_scanned_pdf(
            source, label=label, language=language, timeout=timeout, limits=limits
        )
        assert document.ocr is not None
        document.ocr.processed_pages = [page.number for page in document.pages]
        document.ocr.note = (
            "All-page OCR: text recognized from rendered pages replaces native text. "
            "Grounding checks recognized text; review the page images, especially numbers, "
            "dates and word boxes."
        )
        return document
    limits = limits or DocumentLimits()
    try:
        document = load_pdf(source, label=label, limits=limits)
    except EmptyDocumentError:
        # Preserve the established all-scanned path and its provenance format.
        return load_scanned_pdf(
            source, label=label, language=language, timeout=timeout, limits=limits
        )
    processed = [page.number for page in document.pages if not page.words]
    if not processed:
        return document
    _require_engine()
    import pytesseract

    words = sum(len(page.words) for page in document.pages)
    text_chars = sum(len(page.text) for page in document.pages)
    pages = []
    for page in document.pages:
        if not page.words:
            page = _recognize_page(source, page.number, language, timeout, limits)
            words += len(page.words)
            text_chars += len(page.text)
            if words > limits.max_words or text_chars > limits.max_text_chars:
                raise DocumentLimitError(
                    "Combined native and OCR text exceeds the document word/character budget"
                )
        pages.append(page)
    numbers = ", ".join(map(str, processed))
    return Document(
        source=document.source,
        pages=pages,
        ocr=OcrProvenance(
            engine="tesseract",
            version=str(pytesseract.get_tesseract_version()),
            language=language,
            render_dpi=144,
            page_count=document.page_count,
            processed_pages=processed,
            empty_pages=[page.number for page in pages if not page.words],
            note=(
                f"Mixed PDF: OCR processed pages {numbers}; other pages retain native text. "
                "Grounding on OCR pages checks recognized text, not the printed original. "
                "Review those page images, especially numbers, dates and word boxes."
            ),
        ),
    )


def _validate_options(language: str, timeout: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("OCR timeout must be finite and positive")
    if not language or any(not (ch.isascii() and (ch.isalnum() or ch in "_+")) for ch in language):
        raise ValueError(
            "OCR language must name installed Tesseract languages, e.g. eng or eng+fra"
        )


def _require_engine() -> None:
    if not is_available():
        raise RuntimeError(
            "OCR is not available: install the 'ocr' extra (pytesseract, Pillow) "
            "and the Tesseract binary (e.g. `apt install tesseract-ocr`)."
        )


def _recognize_page(
    source: str | Path | bytes,
    page_number: int,
    language: str,
    timeout: float,
    limits: DocumentLimits,
) -> Page:
    import pytesseract
    from PIL import Image

    png_bytes = render_page_png(source, page_number, scale=2.0, max_pixels=limits.max_pixels)
    with Image.open(io.BytesIO(png_bytes)) as image:
        try:
            data = pytesseract.image_to_data(
                image, lang=language, timeout=timeout, output_type=pytesseract.Output.DICT
            )
        except (RuntimeError, OSError) as exc:
            raise RuntimeError(f"OCR failed on page {page_number}: {exc}") from exc
        return _page_from_ocr(page_number, image.width, image.height, data)


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
