"""Core document model: pages, words, and character-offset text.

Every downstream stage (grounding, verification, the review UI) refers back
to a document by page number and character offset, so this is the one place
that owns the coordinate system. A `Document` is deliberately dumb data: no
provider calls, no rendering, just what was actually on the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BBox:
    """A rectangle in PDF points, origin top-left, y growing downward.

    This matches pdfplumber's convention (not the PDF spec's bottom-left
    origin) so bounding boxes can be drawn directly onto a top-left-origin
    page image without a flip.
    """

    x0: float
    top: float
    x1: float
    bottom: float

    def union(self, other: BBox) -> BBox:
        return BBox(
            x0=min(self.x0, other.x0),
            top=min(self.top, other.top),
            x1=max(self.x1, other.x1),
            bottom=max(self.bottom, other.bottom),
        )

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "top": self.top, "x1": self.x1, "bottom": self.bottom}


@dataclass(frozen=True, slots=True)
class Word:
    """A single word on a page, with its bounding box and offset into the
    page's flattened text (`Page.text`)."""

    text: str
    bbox: BBox
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Page:
    """One page of a document.

    `text` is the words joined by single spaces, in reading order; `words[i]`
    corresponds to the exact span `text[words[i].start:words[i].end]`. This
    is the text that grounding aligns quotes against.
    """

    number: int
    width: float
    height: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass(slots=True)
class Document:
    """A loaded document: one or more pages with extracted text layers.

    `source` is a human-readable label for provenance (filename), not a
    filesystem path guarantee - callers may load from bytes.
    """

    source: str
    pages: list[Page] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page(self, number: int) -> Page:
        for p in self.pages:
            if p.number == number:
                return p
        raise IndexError(f"document {self.source!r} has no page {number}")

    def full_text(self) -> str:
        """All pages concatenated, one page per line - used only for
        provider prompts, never for grounding (which is per-page)."""
        return "\n".join(p.text for p in self.pages)
