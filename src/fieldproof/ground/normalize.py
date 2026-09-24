"""Text normalization for grounding.

The model's evidence quotes and the page's own text layer rarely agree on
byte-for-byte punctuation: curly vs. straight quotes, ligatures a PDF font
substitutes for "fi"/"fl", and runs of whitespace where the original had a
line break or a tab. `normalize_with_map` normalizes while keeping a
character-by-character map back to the original string, so a match found in
normalized text can still be located in the original page text (and from
there, in `Page.words`).
"""

from __future__ import annotations

import unicodedata

_QUOTE_MAP = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "«": '"',
    "»": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
}


def _map_char(ch: str) -> str:
    if ch in _QUOTE_MAP:
        return _QUOTE_MAP[ch]
    return unicodedata.normalize("NFKC", ch)


def normalize(text: str) -> str:
    """Normalize text for comparison: NFKC, ligature expansion, straight
    quotes/dashes, collapsed whitespace. Loses position information - use
    `normalize_with_map` when you need to locate the result in `text`."""
    return normalize_with_map(text)[0]


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Like `normalize`, but also returns `index_map` where
    `index_map[i]` is the offset in `text` that normalized character `i`
    came from. `len(normalized) == len(index_map)`, always."""
    out: list[str] = []
    index_map: list[int] = []
    in_whitespace_run = False

    for i, ch in enumerate(text):
        mapped = _map_char(ch)
        if not mapped:
            continue
        if mapped.isspace():
            if in_whitespace_run:
                continue
            out.append(" ")
            index_map.append(i)
            in_whitespace_run = True
            continue
        in_whitespace_run = False
        for c in mapped:
            out.append(c)
            index_map.append(i)

    start = 0
    end = len(out)
    while start < end and out[start] == " ":
        start += 1
    while end > start and out[end - 1] == " ":
        end -= 1

    return "".join(out[start:end]), index_map[start:end]
