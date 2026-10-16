"""Conservative outer bounds of native clipping paths, in device coordinates.

These bounds can identify text crossing a clip's outer boundary. They cannot
prove visibility inside a nonrectangular path, a hole, or a text clipping mask.
Bezier control points bound their curve, so no curve flattening is required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pdfminer.utils import Matrix, Rect, apply_matrix_pt

EMPTY: Rect = (0, 0, 0, 0)


def intersect(first: Rect | None, second: Rect) -> Rect:
    if first is None:
        return second
    left, bottom = max(first[0], second[0]), max(first[1], second[1])
    right, top = min(first[2], second[2]), min(first[3], second[3])
    return (left, bottom, right, top) if right > left and top > bottom else EMPTY


def transformed_rect(rect: Any, ctm: Matrix) -> Rect | None:
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        return None
    if any(type(value) not in (int, float) for value in rect):
        return None
    try:
        left, bottom, right, top = (float(value) for value in rect)
    except OverflowError:
        return None
    if not all(math.isfinite(value) for value in (left, bottom, right, top)):
        return None
    path = ClipPath()
    path.include([(left, bottom), (left, top), (right, bottom), (right, top)], ctm)
    return None if path.unknown else path.bounds


def crosses_clip(bounds: Rect, clip: Rect | None) -> bool:
    if clip is None:
        return False
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        return True
    # Avoid review reasons caused only by arithmetic at the shared boundary.
    epsilon = 1e-6
    return (bounds[0] < clip[0] - epsilon or bounds[1] < clip[1] - epsilon
            or bounds[2] > clip[2] + epsilon or bounds[3] > clip[3] + epsilon)


@dataclass
class ClipPath:
    bounds: Rect | None = None
    pending: bool = False
    unknown: bool = False

    def include(self, points: list[tuple[float, float]], ctm: Matrix) -> None:
        for point in points:
            x, y = apply_matrix_pt(ctm, point)
            if not math.isfinite(x) or not math.isfinite(y):
                self.unknown = True
                continue
            if self.bounds is None:
                self.bounds = (x, y, x, y)
            else:
                left, bottom, right, top = self.bounds
                self.bounds = min(left, x), min(bottom, y), max(right, x), max(top, y)

    def record(self, segments: Any, ctm: Matrix) -> None:
        if not segments:
            # The upstream parser rejected an operand; do not tighten a clip
            # from an incomplete reconstruction of that path.
            self.unknown = True
        for segment in segments:
            coordinates = segment[1:]
            self.include(list(zip(coordinates[::2], coordinates[1::2], strict=True)), ctm)

    def finish(self, clip: Rect | None) -> Rect | None:
        if self.pending and not self.unknown and self.bounds is not None:
            clip = intersect(clip, self.bounds)
        self.bounds, self.pending, self.unknown = None, False, False
        return clip
