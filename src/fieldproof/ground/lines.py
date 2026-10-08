"""Retain line boundaries when reading numeric modifiers from flattened page text."""

from collections.abc import Sequence
from itertools import pairwise

from fieldproof.document.model import Word


def separate_lines(text: str, words: Sequence[Word], *, start: int = 0) -> str:
    """Replace separating spaces with newlines when neighboring boxes do not share a row.

    The length and offsets stay unchanged. A receipt footer's dash must not become
    the preceding total's trailing minus just because Page.text joins every word
    with spaces. Half-height vertical overlap tolerates skew in OCR word boxes.
    """
    chars = list(text)
    for before, after in pairwise(words):
        overlap = min(before.bbox.bottom, after.bbox.bottom) - max(before.bbox.top, after.bbox.top)
        same_row = overlap > 0 and overlap >= min(before.bbox.height, after.bbox.height) / 2
        boundary = before.end - start
        if not same_row and 0 <= boundary < len(chars) and chars[boundary].isspace():
            chars[boundary] = "\n"
    return "".join(chars)
