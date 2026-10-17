"""Observe native text's raster contribution using an independent reference PDF.

The reference retains images, paths and text clipping while suppressing native
text paint. A glyph needs some contribution outside other painting glyphs'
renderer ink bounds. Shared pixels alone cannot establish which text contributed.
This remains a bounded observation, not proof of glyph identity or readability.
"""

from __future__ import annotations

import ctypes
import math
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image, ImageChops
from pypdfium2 import raw

from fieldproof.document.glyph_envelopes import GlyphEnvelope, glyph_envelopes
from fieldproof.document.limits import DocumentLimitError, check_page_pixels
from fieldproof.document.model import BBox, RasterState

MAX_PAGE_OBJECTS = 50_000
MAX_FORM_DEPTH = 32
MAX_OVERLAP_GLYPHS = 50_000
MAX_OVERLAP_PIXELS = 64_000_000
_GLYPH_CELL = 64


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
        self.overlaps: Any = None
        self.glyphs: dict[tuple[str, int, int], list[GlyphEnvelope]] | None = None

    def _pixels(self, box: BBox, *, outward: bool) -> tuple[int, int, int, int] | None:
        if self.image is None or not all(
            math.isfinite(n) for n in (box.x0, box.top, box.x1, box.bottom)
        ):
            return None
        if box.width <= 0 or box.height <= 0:
            return None
        sx, sy = self.image.width / self.width, self.image.height / self.height
        lower, upper = (math.floor, math.ceil) if outward else (math.ceil, math.floor)
        left = max(0, min(self.image.width, lower(box.x0 * sx)))
        top = max(0, min(self.image.height, lower(box.top * sy)))
        right = max(0, min(self.image.width, upper(box.x1 * sx)))
        bottom = max(0, min(self.image.height, upper(box.bottom * sy)))
        return (left, top, right, bottom) if right > left and bottom > top else None

    def observe_overlaps(self, glyphs: Iterable[GlyphEnvelope]) -> None:
        """Record pixels owned by multiple potentially painting native ink bounds.

        Two one-bit page masks avoid pairwise rectangle searches and full RGB
        copies. Work is bounded by both glyph count and accumulated pixel area;
        exhausting either budget leaves the whole page's attribution unchecked.
        Bounds round outward here so a fractional shared edge cannot lend ink.
        """
        self.close()
        if self.image is None:
            return
        covered = overlaps = None
        try:
            covered = Image.new("1", self.image.size)
            overlaps = Image.new("1", self.image.size)
            area = 0
            indexed: dict[tuple[str, int, int], list[GlyphEnvelope]] = {}
            for count, glyph in enumerate(glyphs, 1):
                box = glyph.ink
                if count > MAX_OVERLAP_GLYPHS:
                    raise ValueError("Glyph overlap traversal exceeds its budget")
                if not all(math.isfinite(v) for v in (box.x0, box.top, box.x1, box.bottom)):
                    raise ValueError("Glyph bounds are unavailable")
                if box.width <= 0 or box.height <= 0:
                    raise ValueError("Glyph bounds have no area")
                pixels = self._pixels(box, outward=True)
                if pixels is None:  # Entirely outside the visible canvas.
                    continue
                left, top, right, bottom = pixels
                area += (right - left) * (bottom - top)
                if area > MAX_OVERLAP_PIXELS:
                    raise ValueError("Glyph overlap pixel work exceeds its budget")
                with covered.crop(pixels) as previous:
                    # Masked paste sets only previously covered pixels. Existing
                    # overlap evidence cannot be erased by a later glyph.
                    overlaps.paste(1, pixels, previous)
                covered.paste(1, pixels)
                envelope = self._pixels(glyph.box, outward=True)
                if glyph.text and envelope is not None:
                    el, et, er, eb = envelope
                    area += (er - el) * (eb - et)
                    if area > MAX_OVERLAP_PIXELS:
                        raise ValueError("Glyph association work exceeds its budget")
                    for x in range(el // _GLYPH_CELL, (er - 1) // _GLYPH_CELL + 1):
                        for y in range(et // _GLYPH_CELL, (eb - 1) // _GLYPH_CELL + 1):
                            indexed.setdefault((glyph.text, x, y), []).append(glyph)
            self.overlaps = overlaps
            self.glyphs = indexed
            overlaps = None
        except (ValueError, OverflowError):
            pass
        finally:
            for mask in (covered, overlaps):
                if mask is not None:
                    mask.close()

    def close(self) -> None:
        self.glyphs = None
        if self.overlaps is not None:
            self.overlaps.close()
            self.overlaps = None

    def check(self, box: BBox, text: str) -> RasterState:
        # Observe only complete pixels inside the glyph's layout rectangle.
        # Rounding outward can borrow an adjacent character's antialiased edge
        # and falsely establish variation for an entirely hidden digit.
        pixels = self._pixels(box, outward=False)
        if pixels is None or self.overlaps is None or self.glyphs is None:
            return "unavailable"
        left, top, right, bottom = pixels
        candidates = self.glyphs.get((text, ((left + right) // 2) // _GLYPH_CELL,
                                     ((top + bottom) // 2) // _GLYPH_CELL), [])
        matched = [g for g in candidates if g.box.x0 <= box.x0 and g.box.top <= box.top
                   and g.box.x1 >= box.x1 and g.box.bottom >= box.bottom]
        if len(matched) != 1:
            # A coordinate alone cannot associate this source character with
            # the renderer's glyph. Keep missing/mismatched native evidence unknown.
            return "unavailable"
        support = self._pixels(matched[0].ink, outward=True)
        if support is None:
            return "unavailable"
        pixels = (
            max(left, support[0]), max(top, support[1]),
            min(right, support[2]), min(bottom, support[3]),
        )
        if pixels[2] <= pixels[0] or pixels[3] <= pixels[1]:
            return "unavailable"
        with self.image.crop(pixels) as region:
            if region.getbbox() is None:
                return "no_contribution"
            with self.overlaps.crop(pixels) as shared:
                region.paste((0, 0, 0), mask=shared)
            return "contributes" if region.getbbox() is not None else "ambiguous_overlap"


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
    miter_limit: float | None,
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
        with closing(RasterProbe(image, width, height)) as probe:
            if image is not None:
                try:
                    probe.observe_overlaps(glyph_envelopes(
                        page, width, height, image.size, max_glyphs=MAX_OVERLAP_GLYPHS,
                        miter_limit=miter_limit,
                    ))
                except (pdfium.PdfiumError, ValueError, OverflowError, AttributeError):
                    probe.close()
            yield probe
    finally:
        if image is not None:
            image.close()
