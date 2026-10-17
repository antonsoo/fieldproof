"""Bound potentially painting glyphs in the renderer's displayed page frame.

Advance rectangles are layout measurements. Italic outlines can extend beyond
them. PDFium's character boxes include those font overhangs; native page-to-device
mapping retains the CropBox and page rotation used for the observed raster.
"""

from __future__ import annotations

import ctypes
import math
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdfium2 import raw

from fieldproof.document.model import BBox


@dataclass(frozen=True)
class GlyphEnvelope:
    text: str
    box: BBox
    ink: BBox


def _mapper(
    page: pdfium.PdfPage,
    width: float,
    height: float,
    pixels: tuple[int, int],
) -> Callable[[float, float], tuple[float, float]]:
    left, bottom, right, top = page.get_bbox()
    if (
        not all(math.isfinite(v) for v in (left, bottom, right, top))
        or right <= left
        or top <= bottom
    ):
        raise ValueError("Native page coordinates are unavailable")

    def device(x: float, y: float) -> tuple[float, float]:
        dx, dy = ctypes.c_int(), ctypes.c_int()
        if not raw.FPDF_PageToDevice(page.raw, 0, 0, *pixels, 0, x, y, dx, dy):
            raise ValueError("Native page-to-raster mapping is unavailable")
        return dx.value * width / pixels[0], dy.value * height / pixels[1]

    # These three page-boundary points establish the affine display transform.
    # Unlike guessing rotation signs, this follows the renderer's actual view.
    origin, across, above = device(left, bottom), device(right, bottom), device(left, top)

    def mapped(x: float, y: float) -> tuple[float, float]:
        u, v = (x - left) / (right - left), (y - bottom) / (top - bottom)
        return (
            origin[0] + u * (across[0] - origin[0]) + v * (above[0] - origin[0]),
            origin[1] + u * (across[1] - origin[1]) + v * (above[1] - origin[1]),
        )

    return mapped


def _paint_properties(obj: object, miter_limit: float | None) -> tuple[bool, float]:
    mode = raw.FPDFTextObj_GetTextRenderMode(obj)
    if mode not in range(8):
        raise ValueError("Native text rendering mode is unavailable")
    if mode in (3, 7):
        return False, 0.0

    def alpha(stroke: bool) -> int:
        colors = [ctypes.c_uint() for _ in range(4)]
        getter = raw.FPDFPageObj_GetStrokeColor if stroke else raw.FPDFPageObj_GetFillColor
        if not getter(obj, *colors):
            raise ValueError("Native text opacity is unavailable")
        return colors[3].value

    fill = mode in (0, 2, 4, 6) and alpha(False) > 0
    stroke = mode in (1, 2, 5, 6) and alpha(True) > 0
    join = raw.FPDFPageObj_GetLineJoin(obj) if stroke else 1
    if join not in (0, 1, 2):
        raise ValueError("Native text stroke join bounds are unavailable")
    miter_factor = 1.0
    if join == 0:
        if miter_limit is None:
            raise ValueError("Native text miter limit is unavailable")
        miter_factor = miter_limit
    width = ctypes.c_float()
    if stroke and (
        not raw.FPDFPageObj_GetStrokeWidth(obj, width)
        or not math.isfinite(width.value)
        or width.value < 0
    ):
        raise ValueError("Native text stroke width is unavailable")
    # A miter can extend much farther than half the stroke width. Its limit
    # comes from the parsed page/Form graphics declarations, not a guessed
    # native default. Round and bevel joins need only the half-width extent.
    return fill or stroke, width.value * miter_factor


def glyph_envelopes(
    page: pdfium.PdfPage,
    width: float,
    height: float,
    pixels: tuple[int, int],
    *,
    max_glyphs: int,
    miter_limit: float | None,
) -> list[GlyphEnvelope]:
    """Return bounded native envelopes, including partly cropped painting glyphs.

    Generated separators do not paint. Real glyphs are filtered by their native
    text object's rendering mode and opacity; invisible text cannot turn visible
    control text into an ambiguous overlap merely by sharing its coordinates.
    """
    transform = _mapper(page, width, height, pixels)
    padding_x, padding_y = width / pixels[0], height / pixels[1]
    result = []
    paint_objects: dict[int | None, tuple[bool, float]] = {}
    with closing(page.get_textpage()) as text:
        count = text.count_chars()
        if not 0 <= count <= max_glyphs:
            raise ValueError("Native glyph traversal is unavailable or exceeds its budget")
        for index in range(count):
            generated = raw.FPDFText_IsGenerated(text.raw, index)
            if generated == 1:
                continue
            if generated != 0:
                raise ValueError("Native character origin is unavailable")
            obj = raw.FPDFText_GetTextObject(text.raw, index)
            if not obj:
                raise ValueError("Native text object is unavailable")
            identity = ctypes.cast(obj, ctypes.c_void_p).value
            if identity not in paint_objects:
                paint_objects[identity] = _paint_properties(obj, miter_limit)
            painting, stroke_width = paint_objects[identity]
            if not painting:
                continue
            tight = text.get_charbox(index)
            loose = text.get_charbox(index, loose=True)
            if not all(math.isfinite(v) for v in (*tight, *loose)):
                raise ValueError("Native character bounds are unavailable")
            if tight[2] <= tight[0] or tight[3] <= tight[1]:
                continue  # A real space or an empty glyph has no observed ink area.
            if stroke_width:
                matrix = raw.FS_MATRIX()
                if not raw.FPDFText_GetMatrix(text.raw, index, matrix) or not all(
                    math.isfinite(v) for v in (matrix.a, matrix.b, matrix.c, matrix.d)
                ):
                    raise ValueError("Native text stroke transform is unavailable")
                dx = stroke_width * (abs(matrix.a) + abs(matrix.c)) / 2
                dy = stroke_width * (abs(matrix.b) + abs(matrix.d)) / 2
                tight = tight[0] - dx, tight[1] - dy, tight[2] + dx, tight[3] + dy
            left, bottom = min(tight[0], loose[0]), min(tight[1], loose[1])
            right, top = max(tight[2], loose[2]), max(tight[3], loose[3])
            corners = [transform(x, y) for x in (left, right) for y in (bottom, top)]
            # The font envelope associates the source character with native
            # geometry. It must not make an adjacent blank advance look painted.
            box = BBox(
                min(p[0] for p in corners) - padding_x,
                min(p[1] for p in corners) - padding_y,
                max(p[0] for p in corners) + padding_x,
                max(p[1] for p in corners) + padding_y,
            )
            # PDFium stores glyph rectangles as floats internally. Account for
            # their precision before rounding raster coverage outward; expanding
            # every advance by a whole pixel erases narrow, visible i/l stems.
            epsilon = max(1.0, *(abs(v) for v in (*tight, *loose))) * 2**-21
            ink_corners = [
                transform(x, y)
                for x in (tight[0] - epsilon, tight[2] + epsilon)
                for y in (tight[1] - epsilon, tight[3] + epsilon)
            ]
            ink = BBox(
                # Retain half a raster pixel for edge support, independently
                # from the larger font envelope used only for association.
                min(p[0] for p in ink_corners) - padding_x / 2,
                min(p[1] for p in ink_corners) - padding_y / 2,
                max(p[0] for p in ink_corners) + padding_x / 2,
                max(p[1] for p in ink_corners) + padding_y / 2,
            )
            codepoint = raw.FPDFText_GetUnicode(text.raw, index)
            character = chr(codepoint) if 0 < codepoint <= 0x10FFFF else ""
            result.append(GlyphEnvelope(character, box, ink))
    return result
