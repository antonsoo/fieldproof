"""Seeded fuzz of grounding and of the command line.

The promise under test is the one the README makes: a field is `verified` only
if its evidence is really on the page and really says the value. So a quote
that exists only as a piece of a longer word must never be an exact match, a
value with digits the document doesn't contain must never verify, and a result
file of any shape must end in a report or a one-line error.
"""

from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.document.loader import load_pdf
from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.ground.align import find_candidates
from fieldproof.ground.normalize import normalize
from fieldproof.schemas import BUILTIN_SCHEMAS
from fieldproof.verify.engine import FieldStatus, verify

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
_NAMES = ("invoice", "receipt", "contract")
_TOKENS = [
    "Northwind", "Freight", "&", "Supply", "Co.", "Invoice", "Number:", "NW-20260214", "INV-1001",
    "4821", "Harbor", "Road,", "Suite", "400", "Total:", "$2,458.00", "$58.00", "1,", "(2)", "1",
    "12", "2026-02-14", "February", "14,", "2026", "the", "ﬁnal", "oﬃce", "“quoted”",
    "café", "Qty", "x3", "A", "a", "-", "8.5%", "No.", "7", "77", "777",
]  # fmt: skip
runner = CliRunner()


def _page(rng: random.Random) -> Page:
    words: list[Word] = []
    parts: list[str] = []
    offset = 0
    for i in range(rng.randint(1, 40)):
        token = rng.choice(_TOKENS)
        box = BBox(x0=float(offset), top=10.0 + 14 * (i // 8), x1=float(offset + 1), bottom=20.0)
        words.append(Word(text=token, bbox=box, start=offset, end=offset + len(token)))
        parts.append(token)
        offset += len(token) + 1
    return Page(number=1, width=600.0, height=800.0, text=" ".join(parts), words=words)


def _left_out(page: Page, start: int, end: int) -> str:
    """What a span leaves uncovered in the words it touches."""
    touched = [w for w in page.words if w.start < end and w.end > start]
    return page.text[touched[0].start : start] + page.text[end : touched[-1].end]


@pytest.mark.parametrize("block", range(5))
def test_an_exact_match_always_covers_whole_words(block: int) -> None:
    exact_matches = 0
    for seed in range(block * 200, (block + 1) * 200):
        rng = random.Random(seed)
        page = _page(rng)

        # Any run of whole words is found, exactly, where it is.
        first = rng.randrange(len(page.words))
        last = rng.randrange(first, min(len(page.words), first + 5))
        quote = page.text[page.words[first].start : page.words[last].end]
        found = find_candidates(quote, page)
        assert found, f"seed {seed}: {quote!r} not found in {page.text!r}"
        assert all(m.score == 100.0 for m in found), f"seed {seed}: {quote!r}"
        assert any(m.start == page.words[first].start for m in found), f"seed {seed}"

        # Any other slice of the page is either not an exact match, or covers whole words.
        for _ in range(8):
            a = rng.randrange(len(page.text))
            b = rng.randrange(a + 1, min(len(page.text), a + 30) + 1)
            piece = page.text[a:b]
            for match in find_candidates(piece, page):
                if not match.is_exact:
                    continue
                exact_matches += 1
                context = f"seed {seed}: {piece!r} matched {match.matched_text!r} in {page.text!r}"
                assert not any(c.isalnum() for c in _left_out(page, match.start, match.end)), (
                    context
                )
                assert normalize(match.matched_text) == normalize(piece), context
    assert exact_matches > 100, "the generated slices almost never match: the property is untested"


def _example(name: str) -> tuple[dict[str, Any], Document]:
    raw = json.loads((EXAMPLES_DIR / "fixtures" / f"{name}.json").read_text())["data"]
    return raw, load_pdf(EXAMPLES_DIR / f"{name}.pdf")


def _first_text_field(raw: dict[str, Any]) -> str:
    return next(
        key
        for key, field in raw.items()
        if isinstance(field, dict) and isinstance(field.get("value"), str)
    )


@pytest.mark.parametrize("name", _NAMES)
def test_a_piece_of_a_longer_word_never_verifies(name: str) -> None:
    raw, document = _example(name)
    text = document.full_text()
    field = _first_text_field(raw)
    rng = random.Random(name)
    long_words = sorted({w for w in re.findall(r"[A-Za-z0-9]{6,}", text)})
    tried = 0
    for word in rng.sample(long_words, min(40, len(long_words))):
        size = rng.randint(2, max(2, int(len(word) * 0.6)))
        at = rng.randint(0, len(word) - size)
        fragment = word[at : at + size]
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(fragment)}(?![A-Za-z0-9])", text):
            continue  # the fragment is also a word of its own somewhere
        data = copy.deepcopy(raw)
        data[field] = {"value": fragment, "evidence": [fragment], "page": 1}
        report = verify(BUILTIN_SCHEMAS[name].model_validate(data), document)
        result = next(f for f in report.fields if f.path == field)
        assert result.status is not FieldStatus.VERIFIED, f"{fragment!r} (from {word!r})"
        tried += 1
    assert tried >= 10


@pytest.mark.parametrize("name", _NAMES)
def test_a_value_with_a_number_the_document_lacks_never_verifies(name: str) -> None:
    raw, document = _example(name)
    numbers_on_the_page = set(re.findall(r"\d+", normalize(document.full_text())))
    rng = random.Random(name)
    tried = 0
    for key, field in raw.items():
        if not (isinstance(field, dict) and isinstance(field.get("value"), str)):
            continue
        if "date" in key or not re.search(r"\d", field["value"]):
            continue
        for _ in range(10):
            # Change one digit of the value, in the value and in the quote that backs it.
            positions = [i for i, ch in enumerate(field["value"]) if ch.isdigit()]
            at = rng.choice(positions)
            digit = rng.choice([d for d in "0123456789" if d != field["value"][at]])
            wrong = field["value"][:at] + digit + field["value"][at + 1 :]
            if set(re.findall(r"\d+", wrong)) <= numbers_on_the_page:
                continue
            quotes = [q.replace(field["value"], wrong) for q in field["evidence"]]
            data = copy.deepcopy(raw)
            data[key] = {"value": wrong, "evidence": quotes, "page": field.get("page", 1)}
            report = verify(BUILTIN_SCHEMAS[name].model_validate(data), document)
            result = next(f for f in report.fields if f.path == key)
            assert result.status is not FieldStatus.VERIFIED, (
                f"{key}: {wrong!r} for {field['value']!r}"
            )
            tried += 1
    if name == "invoice":
        assert tried >= 10  # the invoice has an invoice number and a PO number to get wrong


_JUNK: list[Any] = [
    None, True, 0, -1, 1.5, "", "x", "2026-13-45", [], {}, [1, 2], {"value": None},
    {"value": {"a": 1}, "evidence": 5, "page": "x"}, "9" * 400, "(1,234.56)", "N/A",
    {"value": "x", "evidence": ["x" * 3000], "page": 10**9},
    {"value": 1e308, "evidence": ["1"], "page": 1},
    {"value": "2024-02-30", "evidence": ["x"], "page": 0},
]  # fmt: skip


def _paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    found = [prefix] if prefix else []
    if isinstance(node, dict):
        for key, value in node.items():
            found += _paths(value, (*prefix, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _paths(value, (*prefix, index))
    return found


def _damaged(rng: random.Random, original: dict[str, Any]) -> Any:
    result: Any = copy.deepcopy(original)
    for _ in range(rng.choice([1, 1, 1, 2, 3, 6])):
        path = rng.choice(_paths(result))
        parent = result
        for key in path[:-1]:
            parent = parent[key]
        action = rng.choice(["junk", "junk", "delete", "repeat", "rename"])
        if action == "junk":
            parent[path[-1]] = copy.deepcopy(rng.choice(_JUNK))
        elif action == "delete":
            del parent[path[-1]]
        elif action == "repeat" and isinstance(parent, list):
            parent.extend(copy.deepcopy(parent) * rng.choice([1, 10]))
        elif action == "rename" and isinstance(parent, dict):
            parent[f"{path[-1]}_x"] = parent.pop(path[-1])
    if rng.random() < 0.04:
        result = rng.choice([[], None, 5, "x", {"schema": "invoice"}, {"data": {}}])
    return result


@pytest.mark.parametrize("block", range(4))
def test_any_result_file_gives_a_report_or_a_one_line_error(tmp_path: Path, block: int) -> None:
    fixtures = {
        n: json.loads((EXAMPLES_DIR / "fixtures" / f"{n}.json").read_text()) for n in _NAMES
    }
    reports = 0
    for seed in range(block * 60, (block + 1) * 60):
        rng = random.Random(seed)
        name = rng.choice(_NAMES)
        text = json.dumps(_damaged(rng, fixtures[name]))
        if rng.random() < 0.03:
            text = text[: rng.randint(0, len(text))]
        result_path = tmp_path / "result.json"
        result_path.write_text(text)
        pdf = str(EXAMPLES_DIR / f"{name}.pdf")
        out = str(tmp_path / "out.json")
        if rng.random() < 0.5:
            argv = ["verify", str(result_path), pdf, "--out", out]
        else:
            argv = ["extract", pdf, "--schema", name, "--fixture", str(result_path), "--out", out]
        result = runner.invoke(app, argv)
        context = f"seed {seed}: {argv[0]}"
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"{context} raised {result.exception!r}"
        )
        if result.exit_code == 0:
            reports += 1
            counts = json.loads(Path(out).read_text())["report"]["counts"]
            assert set(counts) == {"verified", "needs_review", "unsupported"}, context
        else:
            message = result.output.strip()
            assert message.startswith("error: ") and "\n" not in message, f"{context}: {message}"
    assert reports >= 10, "nearly every damaged file is rejected: the engine goes untested"
