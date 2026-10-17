"""Load PDFs with a text layer into the `Document` model.

Uses pdfplumber for word-level extraction (text + bounding boxes) because its
`extract_words` gives us individual words with boxes, in reading order.
PDFium compares the original page with a separate reference whose native text
paint is suppressed. Regional contribution is not proof of glyph identity or
readability; see raster_paint.
"""

from __future__ import annotations

import io
from contextlib import closing
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from fieldproof.document.limits import DocumentLimitError, DocumentLimits, check_pdf_geometry
from fieldproof.document.model import BBox, Document, Page, RasterState, Word
from fieldproof.document.raster_paint import RasterProbe, page_raster
from fieldproof.document.text_modes import ModePage


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
    views = _visible_page_boxes(source)
    with closing(pdfium.PdfDocument(source)) as raster_pdf, pdfplumber.open(stream) as pdf:
        for page_number, (original, view_box) in enumerate(
            zip(pdf.pages, views, strict=True), start=1
        ):
            page = ModePage(pdf, original.page_obj, original.page_number, original.initial_doctop)
            left, top, width, height = view_box
            origin_x, origin_top = page.mediabox[0] + left, page.mediabox[1] + top
            # PDFium displays the CropBox/MediaBox intersection after rotation.
            # pdfplumber's default page and CropBox are in a different frame.
            # Keep only fully visible characters before assembling words.
            visible = page.within_bbox(
                (origin_x, origin_top, origin_x + width, origin_top + height),
                strict=False,
            )
            raster_page = None
            try:
                raster_page = raster_pdf[page_number - 1]
                with page_raster(
                    raster_page,
                    width,
                    height,
                    source=source,
                    page_index=page_number - 1,
                    max_pixels=limits.max_pixels
                    if limits is not None
                    else DocumentLimits().max_pixels,
                    needed=any(_needs_raster(char) for char in visible.chars),
                    miter_limit=page.miter_limit_bound,
                ) as probe:
                    loaded = _load_page(visible, page_number, probe)
            finally:
                if raster_page is not None:
                    raster_page.close()
                visible.close()
                page.close()  # Release pdfplumber's cached character/layout objects per page.
                original.close()
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


def _visible_page_boxes(source: str | Path | bytes) -> list[tuple[float, float, float, float]]:
    """Visible top-left rectangles relative to each rotated MediaBox."""
    boxes = []
    with closing(pdfium.PdfDocument(source)) as pdf:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                ml, mb, mr, mt = page.get_mediabox()
                left, bottom, right, top = page.get_bbox()
                width, height = page.get_size()
                rotation = page.get_rotation()
                if rotation == 0:
                    x, y = left - ml, mt - top
                elif rotation == 90:
                    x, y = bottom - mb, left - ml
                elif rotation == 180:
                    x, y = mr - right, bottom - mb
                elif rotation == 270:
                    x, y = mt - top, mr - right
                else:
                    raise ValueError("PDF rotation must be a multiple of 90 degrees")
                boxes.append((float(x), float(y), float(width), float(height)))
            finally:
                page.close()
    return boxes


def _may_paint(char: dict[str, Any]) -> bool:
    return (
        bool(char["text"])
        and not char["text"].isspace()
        and char["render_mode"] not in (3, 7)
        and not char["zero_opacity"]
    )


def _needs_raster(char: dict[str, Any]) -> bool:
    return _may_paint(char) and not char["clip_risk"]


def _word_raster(chars: list[dict[str, Any]]) -> RasterState | None:
    states = {char["raster_state"] for char in chars}
    if "unavailable" in states:
        return "unavailable"
    if "no_contribution" in states:
        return "no_contribution"
    if "ambiguous_overlap" in states:
        return "ambiguous_overlap"
    return "contributes" if states == {"contributes"} else None


def _visible_words(page: pdfplumber.page.Page, probe: RasterProbe) -> list[dict[str, Any]]:
    """Word segmentation follows each glyph's transformed baseline direction."""
    groups: dict[str, list[dict[str, Any]]] = {}
    origin_x, origin_top = page.bbox[:2]
    for char in page.chars:
        a, b = char.get("matrix", (1, 0))[:2]
        horizontal_direction = "ltr" if a >= 0 else "rtl"
        vertical_direction = "btt" if b >= 0 else "ttb"
        direction = horizontal_direction if abs(a) >= abs(b) else vertical_direction
        horizontal = direction in {"ltr", "rtl"}
        # pdfminer calls a vertical glyph's advance its "size", which varies
        # by letter and would split a rotated word into single characters.
        size = char["size"] if horizontal else char["width"]
        raster_state = (
            probe.check(
                BBox(
                    char["x0"] - origin_x,
                    char["top"] - origin_top,
                    char["x1"] - origin_x,
                    char["bottom"] - origin_top,
                ),
                char["text"],
            )
            if _needs_raster(char)
            else None
        )
        groups.setdefault(direction, []).append(
            {
                **char,
                "upright": horizontal,
                "size": size,
                "raster_state": raster_state,
            }
        )
    words = []
    for direction, chars in groups.items():
        horizontal = direction in {"ltr", "rtl"}
        segmented = pdfplumber.utils.extract_words(
            chars,
            return_chars=True,
            keep_blank_chars=False,
            use_text_flow=False,
            extra_attrs=["size", "render_mode", "zero_opacity", "clip_risk"],
            char_dir=direction if horizontal else "ltr",
            line_dir="ttb" if direction != "rtl" else "btt",
            char_dir_rotated=direction if not horizontal else "ttb",
            line_dir_rotated="rtl" if direction == "ttb" else "ltr",
        )
        for word in segmented:
            # Keep existing segmentation: a hidden digit must mark the whole
            # original word, not insert artificial spaces into its text.
            word["raster_state"] = _word_raster(word.pop("chars"))
        words.extend(segmented)
    return words


def _load_page(page: pdfplumber.page.Page, page_number: int, probe: RasterProbe) -> Page:
    raw_words = _visible_words(page, probe)

    text_parts: list[str] = []
    words: list[Word] = []
    cursor = 0
    origin_x, origin_top = page.bbox[:2]
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
                bbox=BBox(
                    x0=raw["x0"] - origin_x,
                    top=raw["top"] - origin_top,
                    x1=raw["x1"] - origin_x,
                    bottom=raw["bottom"] - origin_top,
                ),
                start=start,
                end=cursor,
                render_mode=raw["render_mode"],
                zero_opacity=raw["zero_opacity"],
                clip_risk=raw["clip_risk"],
                raster_state=raw["raster_state"],
            )
        )

    return Page(
        number=page_number,
        width=float(page.width),
        height=float(page.height),
        text="".join(text_parts),
        words=words,
    )
