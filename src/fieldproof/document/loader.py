"""Load PDFs with a text layer into the `Document` model.

Uses pdfplumber for word-level extraction (text + bounding boxes) because its
`extract_words` gives us exactly the granularity grounding needs: individual
words with boxes, in reading order. pypdfium2 is used separately for page
rendering (see `render.py`) since pdfplumber's rendering path is slower and
we only need pixels there, not text.
"""

from __future__ import annotations

import io
from pathlib import Path

import pdfplumber

from fieldproof.document.limits import DocumentLimitError, DocumentLimits, check_pdf_geometry
from fieldproof.document.model import BBox, Document, Page, Word


class EmptyDocumentError(ValueError):
    """Raised when a PDF has no extractable text on any page."""


def load_pdf(
    source: str | Path | bytes,
    *,
    label: str | None = None,
    limits: DocumentLimits | None = None,
) -> Document:
    """Load a PDF that has a text layer (not a scanned image).

    `source` may be a path or raw PDF bytes. Raises `EmptyDocumentError` if
    no page yields any words - that's the signal callers should use to fall
    back to OCR (see `fieldproof.document.ocr`).
    """
    if limits is not None:
        check_pdf_geometry(source, limits)
    if isinstance(source, bytes):
        stream: str | Path | io.BytesIO = io.BytesIO(source)
        name = label or "<bytes>"
    else:
        stream = source
        name = label or str(source)

    pages: list[Page] = []
    word_count = text_chars = 0
    with pdfplumber.open(stream) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            try:
                loaded = _load_page(page, page_number)
            finally:
                page.close()  # Release pdfplumber's cached character/layout objects per page.
            word_count += len(loaded.words)
            text_chars += len(loaded.text)
            if limits is not None:
                if word_count > limits.max_words:
                    raise DocumentLimitError(f"PDF exceeds the {limits.max_words:,}-word limit")
                if text_chars > limits.max_text_chars:
                    raise DocumentLimitError(
                        f"PDF exceeds the {limits.max_text_chars:,}-character text limit"
                    )
            pages.append(loaded)

    if not any(p.words for p in pages):
        raise EmptyDocumentError(
            f"{name!r} has no extractable text on any page - "
            "it may be a scanned image; see fieldproof.document.ocr"
        )
    return Document(source=name, pages=pages)


def _load_page(page: pdfplumber.page.Page, page_number: int) -> Page:
    raw_words = page.extract_words(
        keep_blank_chars=False,
        use_text_flow=False,
        extra_attrs=["size"],
    )

    text_parts: list[str] = []
    words: list[Word] = []
    cursor = 0
    for raw in raw_words:
        token = raw["text"]
        if not token:
            continue
        if text_parts:
            text_parts.append(" ")
            cursor += 1
        start = cursor
        text_parts.append(token)
        cursor += len(token)
        words.append(
            Word(
                text=token,
                bbox=BBox(x0=raw["x0"], top=raw["top"], x1=raw["x1"], bottom=raw["bottom"]),
                start=start,
                end=cursor,
            )
        )

    return Page(
        number=page_number,
        width=float(page.width),
        height=float(page.height),
        text="".join(text_parts),
        words=words,
    )
