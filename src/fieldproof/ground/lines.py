"""Retain source layout boundaries when reading numeric spellings."""

from collections.abc import Sequence
from itertools import pairwise
from math import isfinite

from fieldproof.document.model import Word


def separate_numeric_regions(text: str, words: Sequence[Word], *, start: int = 0) -> str:
    """Retain row boundaries and clearly separated numeric cells at fixed offsets.

    Page.text discards horizontal spacing. Between numeric groups, a same-row
    gap at least 1.5 times the taller word's height is a layout boundary. A
    smaller gap stays unresolved; this does not assign a column role or infer
    a number by joining cells. Invalid/absent geometry cannot settle spacing.
    The replacement newlines are numeric boundaries, not reconstructed prose.
    Half-height vertical overlap tolerates skew in OCR word boxes, and keeps
    a footer's dash from negating the total on the preceding line.
    """
    chars = list(text)
    for before, after in pairwise(words):
        boxes = (before.bbox, after.bbox)
        if not all(
            isfinite(v) for box in boxes for v in (box.x0, box.x1, box.top, box.bottom)
        ) or any(box.width <= 0 or box.height <= 0 for box in boxes):
            continue
        gap = after.bbox.x0 - before.bbox.x1
        overlap = min(before.bbox.bottom, after.bbox.bottom) - max(before.bbox.top, after.bbox.top)
        same_row = overlap > 0 and overlap >= min(box.height for box in boxes) / 2
        numeric_gap = (
            before.text[-1:].isdecimal()
            and after.text[:1].isdecimal()
            and gap >= 1.5 * max(box.height for box in boxes)
        )
        boundary = before.end - start
        if (
            (not same_row or numeric_gap)
            and 0 <= boundary < len(chars)
            and chars[boundary].isspace()
        ):
            chars[boundary] = "\n"
    return "".join(chars)
