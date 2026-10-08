"""Read CORD v2 and the SROIE mirror into gold fields and fieldproof Documents.

The study's adapter, not the library's: it builds a `fieldproof.document.model.Document`
from annotated words and boxes, the same structure `document/loader.py` builds from a PDF
text layer or Tesseract. It never reads the images.

Words are put in reading order by clustering their vertical centres into lines, then
sorting left to right inside a line, the way a text layer would present them. The order of
the dataset's own annotations is not used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pyarrow.parquet as pq

from fieldproof.document.model import BBox, Document, Page, Word


@dataclass
class RawWord:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    gold: str | None = None  # the field this word is a value of, if any
    gold_id: int | None = None  # which instance of that field


@dataclass
class Gold:
    """One annotated field instance: its text as written on the page, and the page words
    that carry it (indices into `Page.words`)."""

    kind: str  # total, subtotal, tax, item_amount, item_name, item_qty, company, date, address
    text: str
    word_idx: list[int]
    lines: list[str] = field(default_factory=list)  # the text as separate OCR lines, if known


@dataclass
class Case:
    doc_id: str
    dataset: str
    split: str  # "dev" or "heldout"
    document: Document
    golds: list[Gold] = field(default_factory=list)


def _order(words: list[RawWord]) -> list[RawWord]:
    """Group into lines by vertical centre, then left to right."""
    ordered = sorted(words, key=lambda w: (w.top + w.bottom) / 2)
    lines: list[list[RawWord]] = []
    for w in ordered:
        yc = (w.top + w.bottom) / 2
        if lines:
            last = lines[-1]
            ref = sum((x.top + x.bottom) / 2 for x in last) / len(last)
            h = sum(x.bottom - x.top for x in last) / len(last)
            if abs(yc - ref) <= 0.5 * h:
                last.append(w)
                continue
        lines.append([w])
    return [w for line in lines for w in sorted(line, key=lambda w: w.x0)]


def _build(
    source: str, raw: list[RawWord], width: float, height: float
) -> tuple[Document, list[RawWord]]:
    raw = _order([w for w in raw if w.text.strip()])
    words: list[Word] = []
    parts: list[str] = []
    pos = 0
    for w in raw:
        if parts:
            pos += 1
        words.append(
            Word(
                text=w.text,
                bbox=BBox(w.x0, w.top, w.x1, w.bottom),
                start=pos,
                end=pos + len(w.text),
            )
        )
        parts.append(w.text)
        pos += len(w.text)
    page = Page(number=1, width=width, height=height, text=" ".join(parts), words=words)
    return Document(source=source, pages=[page]), raw


def _quad_box(q: dict) -> tuple[float, float, float, float]:
    xs = [q[f"x{i}"] for i in range(1, 5)]
    ys = [q[f"y{i}"] for i in range(1, 5)]
    return min(xs), min(ys), max(xs), max(ys)


CORD_KINDS = {
    "total.total_price": "total",
    "sub_total.subtotal_price": "subtotal",
    "sub_total.tax_price": "tax",
    "menu.price": "item_amount",
    "menu.nm": "item_name",
    "menu.cnt": "item_qty",
}


def cord_cases(path: str, split: str) -> list[Case]:
    out: list[Case] = []
    pf = pq.ParquetFile(path)
    for rg in range(pf.num_row_groups):
        for row in pf.read_row_group(rg, columns=["ground_truth"]).to_pylist():
            g = json.loads(row["ground_truth"])
            size = g["meta"]["image_size"]
            doc_id = f"cord-{g['meta']['split']}-{g['meta']['image_id']}"
            raw: list[RawWord] = []
            for gid, line in enumerate(g["valid_line"], 1):  # "dontcare" holds boxes without text
                kind = CORD_KINDS.get(line.get("category", ""))
                for w in line["words"]:
                    x0, t, x1, b = _quad_box(w["quad"])
                    is_val = kind is not None and not w["is_key"]
                    raw.append(
                        RawWord(
                            w["text"],
                            x0,
                            t,
                            x1,
                            b,
                            kind if is_val else None,
                            gid if is_val else None,
                        )
                    )
            doc, ordered = _build(doc_id, raw, size["width"], size["height"])
            golds = _golds(ordered)
            out.append(Case(doc_id, "cord", split, doc, golds))
    return out


def _golds(ordered: list[RawWord]) -> list[Gold]:
    by: dict[int, list[int]] = {}
    kinds: dict[int, str] = {}
    for i, w in enumerate(ordered):
        if w.gold_id is not None and w.gold is not None:
            by.setdefault(w.gold_id, []).append(i)
            kinds[w.gold_id] = w.gold
    golds = []
    for gid, idx in by.items():
        text = " ".join(ordered[i].text for i in idx)
        golds.append(Gold(kinds[gid], text, idx))
    return golds


NARROW = {
    "date": re.compile(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"),
    "total": re.compile(r"-?\d[\d,]*\.\d{2}"),
}

SROIE_KINDS = {"company": "company", "date": "date", "address": "address", "total": "total"}


def sroie_cases(path: str) -> list[Case]:
    """SROIE gives OCR lines, not words. A line is split on whitespace and its box shared
    out in proportion to character count, which is what a whitespace-split text layer
    would give for a line of uniform type."""
    out: list[Case] = []
    pf = pq.ParquetFile(path)
    n = 0
    for rg in range(pf.num_row_groups):
        for row in pf.read_row_group(rg, columns=["ocr"]).to_pylist():
            doc_id = f"sroie-{n}"
            split = "dev" if n % 2 == 0 else "heldout"
            n += 1
            raw: list[RawWord] = []
            gid = 0
            maxx = maxy = 1.0
            for o in row["ocr"]:
                xs = [p[0] for p in o["box"]]
                ys = [p[1] for p in o["box"]]
                x0, x1, t, b = min(xs), max(xs), min(ys), max(ys)
                maxx, maxy = max(maxx, x1), max(maxy, b)
                kind = SROIE_KINDS.get(o["label"])
                gid += 1
                toks = o["text"].split()
                if not toks:
                    continue
                total_chars = sum(len(t_) for t_ in toks) + len(toks) - 1
                cur = x0
                for tok in toks:
                    w_ = (x1 - x0) * len(tok) / total_chars
                    raw.append(RawWord(tok, cur, t, cur + w_, b, kind, gid if kind else None))
                    cur += w_ + (x1 - x0) / total_chars
            doc, ordered = _build(doc_id, raw, maxx, maxy)
            # one gold per kind: an address or a company name can span several OCR lines
            byk: dict[str, list[int]] = {}
            for i, w in enumerate(ordered):
                if w.gold:
                    byk.setdefault(w.gold, []).append(i)
            golds = []
            for k, idx in byk.items():
                if k in NARROW:
                    # the labelled line can carry more than the value ("RM 33.90",
                    # "19/10/2018 20:49:59 #01"): the value is the first token of the right shape
                    idx = [i for i in idx if NARROW[k].fullmatch(ordered[i].text)][:1]
                    if not idx:
                        continue
                lines: dict[int, list[str]] = {}
                for i in idx:
                    lines.setdefault(ordered[i].gold_id or 0, []).append(ordered[i].text)
                golds.append(
                    Gold(
                        k,
                        " ".join(ordered[i].text for i in idx),
                        idx,
                        [" ".join(v) for v in lines.values()],
                    )
                )
            out.append(Case(doc_id, "sroie", split, doc, golds))
    return out
