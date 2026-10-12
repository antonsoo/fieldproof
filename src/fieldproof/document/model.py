"""Core document model: pages, words, and character-offset text.

Every downstream stage (grounding, verification, the review UI) refers back
to a document by page number and character offset, so this is the one place
that owns the coordinate system. A `Document` is deliberately dumb data: no
provider calls, no rendering, just what was actually on the page.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BBox:
    """A rectangle in PDF points, origin top-left, y growing downward.

    Native text coordinates are translated from pdfplumber's page frame to
    the rendered visible canvas, including its crop and rotation. Boxes can
    be drawn directly onto a top-left-origin page image without a flip.
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
class OcrProvenance:
    """How the text was recognized; this is not an OCR accuracy estimate."""

    engine: str
    version: str
    language: str
    render_dpi: int
    page_count: int
    empty_pages: list[int]
    note: str = (
        "Grounding checks the text recognized by OCR, not the printed original. "
        "Review the scanned page, especially numbers, dates and word boxes."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Document:
    """A loaded document: one or more pages with extracted text layers.

    `source` is a human-readable label for provenance (filename), not a
    filesystem path guarantee - callers may load from bytes.
    """

    source: str
    pages: list[Page] = field(default_factory=list)
    ocr: OcrProvenance | None = None

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


def document_from_dict(raw: dict[str, Any]) -> Document:
    """Rebuild the trusted worker wire format, without pickle deserialization."""
    return Document(
        source=raw["source"],
        ocr=OcrProvenance(**raw["ocr"]) if raw.get("ocr") is not None else None,
        pages=[
            Page(
                number=page["number"],
                width=page["width"],
                height=page["height"],
                text=page["text"],
                words=[
                    Word(
                        text=word["text"],
                        bbox=BBox(**word["bbox"]),
                        start=word["start"],
                        end=word["end"],
                    )
                    for word in page["words"]
                ],
            )
            for page in raw["pages"]
        ],
    )
