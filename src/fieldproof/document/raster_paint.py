"""Observe native text's raster contribution using an independent reference PDF.

The reference retains images, paths and text clipping while suppressing native
text paint. A positive regional difference is not proof of glyph identity or
readability; overlapping native text can contribute to the same region.
"""

from __future__ import annotations

import ctypes
import math
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import ImageChops
from pypdfium2 import raw

from fieldproof.document.limits import DocumentLimitError, check_page_pixels
from fieldproof.document.model import BBox, RasterState

MAX_PAGE_OBJECTS = 50_000
MAX_FORM_DEPTH = 32


def _suppress_text(page: pdfium.PdfPage) -> None:
    count = raw.FPDFPage_CountObjects(page.raw)
    if not 0 <= count <= MAX_PAGE_OBJECTS:
        raise ValueError("Page object traversal is unavailable or exceeds its budget")
    pending = [(raw.FPDFPage_GetObject(page.raw, index), 0) for index in range(count)]
    seen = set()
    inspected = 0
    texts: list[tuple[Any, int]] = []
    while pending:
        obj, depth = pending.pop()
        inspected += 1
        if inspected > MAX_PAGE_OBJECTS or depth > MAX_FORM_DEPTH or not obj:
            raise ValueError("Page object traversal could not finish")
        identity = ctypes.cast(obj, ctypes.c_void_p).value
        if identity in seen:
            continue
        seen.add(identity)
        kind = raw.FPDFPageObj_GetType(obj)
        if kind == raw.FPDF_PAGEOBJ_FORM:
            children = raw.FPDFFormObj_CountObjects(obj)
            if not 0 <= children <= MAX_PAGE_OBJECTS - len(pending):
                raise ValueError("Form traversal is unavailable or exceeds its budget")
            pending.extend(
                (raw.FPDFFormObj_GetObject(obj, index), depth + 1) for index in range(children)
            )
        elif kind == raw.FPDF_PAGEOBJ_TEXT:
            mode = raw.FPDFTextObj_GetTextRenderMode(obj)
            if mode not in range(8):
                raise ValueError("Unsupported text rendering mode")
            # Retain glyph clipping, including fill/stroke-and-clip modes.
            texts.append((obj, 7 if mode >= 4 else 3))
        elif kind not in (raw.FPDF_PAGEOBJ_PATH, raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_SHADING):
            raise ValueError("Unsupported page object type")
    # Collect first: shared Form children must only be changed once, and every
    # original mode must be read before any state can be changed.
    for obj, target in texts:
        if not raw.FPDFTextObj_SetTextRenderMode(obj, target):
            raise ValueError("Text paint suppression failed")
    if any(raw.FPDFTextObj_GetTextRenderMode(obj) != target for obj, target in texts):
        raise ValueError("Text paint suppression could not be confirmed")


def _render_rgb(page: pdfium.PdfPage, max_pixels: int) -> Any:
    width, height = page.get_size()
    check_page_pixels(width, height, 2.0, max_pixels)
    bitmap = page.render(scale=2.0)
    image = None
    try:
        image = bitmap.to_pil()
        return image.convert("RGB")  # An owned image, independent of the native bitmap.
    finally:
        if image is not None:
            image.close()
        bitmap.close()


class RasterProbe:
    def __init__(self, image: Any, width: float, height: float) -> None:
        self.image = image
        self.width = width
        self.height = height

    def check(self, box: BBox) -> RasterState:
        if self.image is None or not all(
            math.isfinite(n) for n in (box.x0, box.top, box.x1, box.bottom)
        ):
            return "unavailable"
        if box.width <= 0 or box.height <= 0:
            return "unavailable"
        sx, sy = self.image.width / self.width, self.image.height / self.height
        # Observe only complete pixels inside the glyph's layout rectangle.
        # Rounding outward can borrow an adjacent character's antialiased edge
        # and falsely establish variation for an entirely hidden digit.
        left = max(0, min(self.image.width, math.ceil(box.x0 * sx)))
        top = max(0, min(self.image.height, math.ceil(box.top * sy)))
        right = max(0, min(self.image.width, math.floor(box.x1 * sx)))
        bottom = max(0, min(self.image.height, math.floor(box.bottom * sy)))
        if right <= left or bottom <= top:
            return "unavailable"
        with self.image.crop((left, top, right, bottom)) as region:
            return "contributes" if region.getbbox() is not None else "no_contribution"


@contextmanager
def page_raster(
    page: pdfium.PdfPage,
    width: float,
    height: float,
    *,
    source: str | Path | bytes,
    page_index: int,
    max_pixels: int,
    needed: bool,
) -> Iterator[RasterProbe]:
    image = foreground = background = control = None
    try:
        if needed:
            try:
                # Match the review PNG's 144 DPI. The actual page is never
                # edited; each disposable reference document starts from source.
                check_page_pixels(width, height, 2.0, max_pixels)
                foreground = _render_rgb(page, max_pixels)
                with closing(pdfium.PdfDocument(source)) as reference:
                    reference_page = reference[page_index]
                    try:
                        control = _render_rgb(reference_page, max_pixels)
                        if foreground.size != control.size:
                            raise ValueError("Reference canvas differs from the original")
                        with ImageChops.difference(foreground, control) as comparison:
                            if comparison.getbbox() is not None:
                                raise ValueError("Reference rendering differs before suppression")
                        control.close()
                        control = None
                        _suppress_text(reference_page)
                        background = _render_rgb(reference_page, max_pixels)
                        image = ImageChops.difference(foreground, background)
                    finally:
                        reference_page.close()
            except (
                DocumentLimitError,
                pdfium.PdfiumError,
                ValueError,
                OverflowError,
                AttributeError,
            ):
                pass
            finally:
                for rendered in (foreground, background, control):
                    if rendered is not None:
                        rendered.close()
        yield RasterProbe(image, width, height)
    finally:
        if image is not None:
            image.close()
