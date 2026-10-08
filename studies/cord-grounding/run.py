"""Ground and verify annotated receipts with a given fieldproof source tree.

    python3 -I run.py --src ../../src --out cache/rows-checkout.jsonl [--workers 4]

Every case is one field offered to `fieldproof.verify.verify` as a one-field model, with
the document built by `adapt.py`. The library under test is whatever `--src` points at, so
the released tag (a git worktree) and this checkout are measured by the same code on the
same documents. Nothing here calls a model: the "extraction" is the gold value, rewritten
or corrupted by the fixed rules below.

Three measurements, one JSON row per case:

  present_written   the gold value, quoted as the page writes it
  present_model     the gold value rewritten the way a model returns it (rules in
                    `model_variants`), quoted either as the page writes it ("page") or as
                    the rewritten value itself ("model")
  absent            a wrong value (rules in `mutants`), either with a made-up quote of the
                    wrong value ("fabricated") or attached to the true quote ("true_quote")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------- value rules

_AMOUNT_TOKEN = re.compile(r"-?\d[\d.,]*")
_THOUSANDS = re.compile(r"^-?\d{1,3}([.,]\d{3})+$")
_DATE_PARTS = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})\2(\d{2}|\d{4})$")


def amount_value(text: str) -> float | None:
    """Locale-aware reading of an amount as written: separators followed by exactly three
    digits (and nothing else) are thousands separators, a single trailing separator with
    one or two digits is a decimal point."""
    m = _AMOUNT_TOKEN.search(text)
    if not m:
        return None
    tok = m.group(0).rstrip(".,")
    if _THOUSANDS.match(tok):
        return float(re.sub(r"[.,]", "", tok))
    if "." in tok and "," in tok:
        dec = max(tok.rfind("."), tok.rfind(","))
        return float(re.sub(r"[.,]", "", tok[:dec]) + "." + tok[dec + 1 :])
    if "," in tok:
        head, _, tail = tok.rpartition(",")
        if len(tail) <= 2:
            return float(head.replace(",", "") + "." + tail)
        return float(tok.replace(",", ""))
    return float(tok)


def locale_ambiguous(text: str) -> bool:
    """A dot (or comma) followed by exactly three digits: thousands in Indonesian or
    German writing, a three-decimal quantity elsewhere."""
    return bool(re.search(r"\d[.,]\d{3}\b", text))


def canonical_amount(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0")


def parse_written_date(text: str) -> date | None:
    """Day-first, which is how Malaysian receipts write numeric dates."""
    m = _DATE_PARTS.match(text.strip())
    if not m:
        return None
    d, _, mo, y = m.groups()
    year = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return date(year, int(mo), int(d))
    except ValueError:
        return None


def format_like(template: str, d: date) -> str:
    m = _DATE_PARTS.match(template.strip())
    assert m
    ds, sep, ms, ys = m.groups()
    day = f"{d.day:0{len(ds)}d}" if len(ds) == 2 else str(d.day)
    mon = f"{d.month:0{len(ms)}d}" if len(ms) == 2 else str(d.month)
    year = f"{d.year}" if len(ys) == 4 else f"{d.year % 100:02d}"
    return f"{day}{sep}{mon}{sep}{year}"


FIELD_TYPE = {
    "total": "amount",
    "subtotal": "amount",
    "tax": "amount",
    "item_amount": "amount",
    "item_qty": "count",
    "item_name": "text",
    "company": "text",
    "address": "text",
    "date": "date",
}


def rng_for(*parts: object) -> random.Random:
    return random.Random(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest())


def gold_value(kind: str, text: str):
    t = FIELD_TYPE[kind]
    if t in ("amount", "count"):
        return amount_value(text)
    if t == "date":
        d = parse_written_date(text)
        return d.isoformat() if d else None
    return text


ONLY_TRUE = "\0only-true-quote"  # marks a wrong value that has no wrong text of its own


# ---------------------------------------------------------------- variants (measurement 2)


def model_variants(kind: str, gold) -> list[tuple[str, str, object]]:
    """(name, quote-as-model-writes-it, value) for a gold field."""
    t = FIELD_TYPE[kind]
    text, value = gold.text, gold_value(kind, gold.text)
    out: list[tuple[str, str, object]] = []
    if t == "amount":
        out.append(("plain", canonical_amount(value), value))
        out.append(("two_decimals", f"{value:.2f}", value))
        out.append(("grouped", f"{value:,.2f}", value))
    elif t == "count":
        out.append(("plain", canonical_amount(value), value))
    elif t == "date":
        d = date.fromisoformat(value)
        out.append(("iso", value, value))
        out.append(("long", f"{d.day} {d.strftime('%B %Y')}", value))
    else:
        out.append(("lower", text.lower(), text.lower()))
        out.append(("title", text.title(), text.title()))
        out.append(("no_punct", re.sub(r"[^\w\s]", "", text), re.sub(r"[^\w\s]", "", text)))
        stripped = re.sub(r"\s+", " ", text.strip(" ,."))
        out.append(("trim_trailing", stripped, stripped))
        toks = text.split()
        if len(toks) >= 3:
            out.append(("drop_first_word", " ".join(toks[1:]), " ".join(toks[1:])))
            out.append(("drop_last_word", " ".join(toks[:-1]), " ".join(toks[:-1])))
        if kind == "address" and len(gold.lines) > 1:
            joined = ", ".join(line.strip(" ,.") for line in gold.lines)
            out.append(("comma_joined", joined, joined))
    return [v for v in out if v[1].strip()]


# ---------------------------------------------------------------- mutants (measurement 3)


def _change_digit(s: str, rng: random.Random) -> str | None:
    pos = [i for i, c in enumerate(s) if c.isdigit()]
    if not pos:
        return None
    i = rng.choice(pos)
    choices = [
        c for c in "0123456789" if c != s[i] and not (i == pos[0] and c == "0" and len(pos) > 1)
    ]
    return s[:i] + rng.choice(choices) + s[i + 1 :]


def _transpose(s: str, rng: random.Random) -> str | None:
    pos = [
        i for i in range(len(s) - 1) if s[i].isdigit() and s[i + 1].isdigit() and s[i] != s[i + 1]
    ]
    pos = [i for i in pos if not (i == 0 and s[1] == "0")]
    if not pos:
        return None
    i = rng.choice(pos)
    return s[:i] + s[i + 1] + s[i] + s[i + 2 :]


def _change_char(s: str, rng: random.Random) -> str | None:
    pos = [i for i, c in enumerate(s) if c.isalnum()]
    if not pos:
        return None
    i = rng.choice(pos)
    c = s[i]
    pool = (
        "0123456789"
        if c.isdigit()
        else ("ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c.isupper() else "abcdefghijklmnopqrstuvwxyz")
    )
    return s[:i] + rng.choice([x for x in pool if x != c]) + s[i + 1 :]


def mutants(kind: str, gold, others: list[str], seed: tuple) -> list[tuple[str, str, str, object]]:
    """(name, quote-in-page-style, quote-in-model-style, wrong value)."""
    t = FIELD_TYPE[kind]
    text = gold.text
    base = gold_value(kind, text)
    out: list[tuple[str, str, str, object]] = []
    rng = rng_for(*seed, "m")

    def other_doc() -> str | None:
        pool = [o for o in others if o != text]
        return rng.choice(pool) if pool else None

    if t in ("amount", "count"):
        for name, fn in (("digit_changed", _change_digit), ("digits_transposed", _transpose)):
            if t == "count" and name == "digits_transposed":
                continue
            m = fn(text, rng_for(*seed, name))
            if m is None:
                continue
            v = amount_value(m)
            if v is None or v == base:
                continue
            out.append((name, m, canonical_amount(v) if t == "amount" else canonical_amount(v), v))
        o = other_doc()
        if o is not None:
            v = amount_value(o)
            if v is not None and v != base:
                out.append(("other_document", o, canonical_amount(v), v))
        if t == "amount":
            m = re.sub(
                r"(\d)(?=\D*$)",
                lambda mm: str(int(mm.group(1)) + (1 if mm.group(1) != "9" else -1)),
                text,
            )
            v = amount_value(m)
            if (
                v is not None
                and abs(v - base) < 0.0105
                and v != base
                and re.search(r"[.,]\d{2}\D*$", text)
            ):
                out.append(("last_digit_off_by_one", m, canonical_amount(v), v))
            wrong = base / 1000 if locale_ambiguous(text) else base * 10
            out.append(("scaled_wrong", ONLY_TRUE, ONLY_TRUE, wrong))
    elif t == "date":
        d = date.fromisoformat(base)
        variants: list[tuple[str, date]] = [
            ("day_plus_1", d + timedelta(days=1)),
            ("day_minus_1", d - timedelta(days=1)),
        ]
        if d.day <= 12 and d.day != d.month:
            variants.append(("day_month_swapped", date(d.year, d.day, d.month)))
        for name, nd in variants:
            out.append((name, format_like(text, nd), nd.isoformat(), nd.isoformat()))
        o = other_doc()
        if o is not None:
            od = parse_written_date(o)
            if od is not None and od.isoformat() != base:
                out.append(("other_document", o, od.isoformat(), od.isoformat()))
    else:
        m = _change_char(text, rng_for(*seed, "char"))
        if m is not None and m != text:
            out.append(("one_char_changed", m, m, m))
        o = other_doc()
        if o is not None:
            out.append(("other_document", o, o, o))
    return out


# ---------------------------------------------------------------- page presence


def values_on_page(doc, t: str) -> set:
    page = doc.pages[0]
    found: set = set()
    for w in page.words:
        if t in ("amount", "count"):
            if re.fullmatch(r"[^\d-]*-?\d[\d.,]*[^\d]*", w.text):
                try:
                    v = amount_value(w.text)
                except ValueError:
                    continue
                if v is not None:
                    found.add(v)
                    # "5.000" is five or five thousand; the page is not wrong either way
                    m3 = re.search(r"(\d+)\.(\d{3})(?![\d.])", w.text)
                    if m3:
                        found.add(float(f"{m3.group(1)}.{m3.group(2)}"))
        elif t == "date":
            d = parse_written_date(w.text)
            if d:
                found.add(d.isoformat())
    return found


def text_on_page(doc, s: str) -> bool:
    norm = lambda x: re.sub(r"\s+", " ", x.lower()).strip()  # noqa: E731
    return norm(s) in norm(doc.pages[0].text)


def label_before(doc, idx: list[int], k: int = 2) -> str:
    """Up to `k` words immediately before the gold words on the same printed line: the
    label a model would normally quote with a value ("TOTAL", "Subtotal", the item name)."""
    words = doc.pages[0].words
    first = min(idx)
    h = words[first].bbox.height or 1.0
    yc = (words[first].bbox.top + words[first].bbox.bottom) / 2
    got: list[str] = []
    for j in range(first - 1, max(first - 1 - k, -1), -1):
        w = words[j]
        if abs((w.bbox.top + w.bbox.bottom) / 2 - yc) > 0.5 * h:
            break
        got.append(w.text)
    return " ".join(reversed(got))


# ---------------------------------------------------------------- running fieldproof


def _modelclass():
    from pydantic import BaseModel

    from fieldproof.schemas.base import Evidenced

    class OneNumber(BaseModel):
        amount: Evidenced[float]

    class OneText(BaseModel):
        text: Evidenced[str]

    class OneDate(BaseModel):
        transaction_date: Evidenced[str]

    return OneNumber, OneText, OneDate


#: `text_edit_tolerance` handed to `verify` (0: the default; needs a checkout that has it)
TOLERANCE = 0

#: What a caller who knows where the receipts come from tells `verify` (`--stated`; needs a
#: checkout that has the arguments). CORD is Indonesian: a dot separates thousands. SROIE is
#: Malaysian: the dot is the decimal point. Both write the day before the month.
STATED = {
    "cord": {"default_number_style": "thousands", "default_date_order": "dmy"},
    "sroie": {"default_number_style": "decimal", "default_date_order": "dmy"},
}

#: keyword arguments for the `verify` call of the case being judged
VERIFY_KW: dict = {}

#: a grounding is at the gold words if it covers at least half of them and takes in at most
#: this many other words (the label a quote carries: up to two, and slack for one more)
EXTRA_WORDS = 3


def judge(doc, gold_idx: set[int], quote: str, value, ftype: str, models):
    from fieldproof.ground import find_candidates_in_document
    from fieldproof.verify import verify

    OneNumber, OneText, OneDate = models
    if ftype in ("amount", "count"):
        data = OneNumber(amount={"value": float(value), "evidence": [quote], "page": 1})
    elif ftype == "date":
        data = OneDate(transaction_date={"value": value, "evidence": [quote], "page": 1})
    else:
        data = OneText(text={"value": value, "evidence": [quote], "page": 1})
    rep = verify(data, doc, **VERIFY_KW)
    f = rep.fields[0]
    page = doc.pages[0]

    def in_rects(w, rects):
        cx, cy = (w.bbox.x0 + w.bbox.x1) / 2, (w.bbox.top + w.bbox.bottom) / 2
        return any(
            r["x0"] - 0.5 <= cx <= r["x1"] + 0.5 and r["top"] - 0.5 <= cy <= r["bottom"] + 0.5
            for r in rects
        )

    place = None
    if f.rects:
        ids = {i for i, w in enumerate(page.words) if in_rects(w, f.rects)}
        inter = len(ids & gold_idx)
        place = bool(ids) and inter / len(gold_idx) >= 0.5 and len(ids) - inter <= EXTRA_WORDS

    cands = find_candidates_in_document(quote, doc, hint_page=1)
    starts = {w.start: i for i, w in enumerate(page.words)}
    cand_right = False
    for c in cands:
        ids = {starts[w.start] for w in c.words if w.start in starts}
        inter = len(ids & gold_idx)
        if ids and inter / len(gold_idx) >= 0.5 and len(ids) - inter <= EXTRA_WORDS:
            cand_right = True
    return {
        "status": f.status.value,
        "place_ok": place,
        "n_cands": len(cands),
        "cand_right": cand_right,
        "score": f.match_score,
        "reason": (f.reasons[0][:90] if f.reasons else ""),
        "quote": quote[:60],
        "value": value if isinstance(value, str) else float(value),
        "matched": (f.matched_text or "")[:60],
    }


def process(args):
    global TOLERANCE, VERIFY_KW
    src, tolerance, cases_spec, mode, stated = args
    TOLERANCE = tolerance
    VERIFY_KW = {"text_edit_tolerance": tolerance} if tolerance else {}
    sys.path.insert(0, src)

    models = _modelclass()
    out = []
    if mode == "ocr":
        return ocr_rows(cases_spec, models)
    for spec in cases_spec:
        case = spec
        if stated:
            VERIFY_KW = {**VERIFY_KW, **STATED[case["dataset"]]}
        by_kind: dict[str, list] = {}
        for g in case["golds"]:
            by_kind.setdefault(g.kind, []).append(g)
        for gi, g in enumerate(case["golds"]):
            kind, ftype = g.kind, FIELD_TYPE[g.kind]
            value = gold_value(kind, g.text)
            if value is None or (ftype in ("amount", "count") and value < 0):
                continue
            idx = set(g.word_idx)
            doc = case["doc"]
            row0 = {
                "doc": case["id"],
                "dataset": case["dataset"],
                "split": case["split"],
                "kind": kind,
                "ftype": ftype,
                "gi": gi,
                "locale_ambiguous": locale_ambiguous(g.text)
                if ftype in ("amount", "count")
                else False,
                "dup_on_page": len([w for w in doc.pages[0].words if w.text == g.text])
                if len(g.word_idx) == 1
                else 0,
            }
            label = label_before(doc, g.word_idx)

            def ctx(q: str, label: str = label) -> str:
                return (label + " " + q).strip()

            res = judge(doc, idx, g.text, value, ftype, models)
            out.append(
                {
                    **row0,
                    "measure": "present_written",
                    "variant": "as_written",
                    "quote_style": "page",
                    **res,
                }
            )
            res = judge(doc, idx, ctx(g.text), value, ftype, models)
            out.append(
                {
                    **row0,
                    "measure": "present_written",
                    "variant": "as_written",
                    "quote_style": "page_context",
                    **res,
                }
            )
            for name, quote, val in model_variants(kind, g):
                for qs, q in (
                    ("page_context", ctx(g.text)),
                    ("model", quote),
                    ("model_context", ctx(quote)),
                ):
                    res = judge(doc, idx, q, val, ftype, models)
                    out.append(
                        {
                            **row0,
                            "measure": "present_model",
                            "variant": name,
                            "quote_style": qs,
                            **res,
                        }
                    )
            others = [o.text for o in case["others"].get(kind, [])]
            present_vals = values_on_page(doc, ftype)
            for name, page_q, model_q, wrong in mutants(kind, g, others, (case["id"], kind, gi)):
                if ftype in ("amount", "count", "date"):
                    there = wrong in present_vals or (
                        page_q != ONLY_TRUE
                        and any(w.text.strip(".,:;*") == page_q for w in doc.pages[0].words)
                    )
                else:
                    there = text_on_page(doc, str(wrong))
                m_row = {**row0, "measure": "absent", "variant": name, "present_elsewhere": there}
                val = float(wrong) if ftype in ("amount", "count") else wrong
                styles = [("fabricated", page_q), ("fabricated_context", ctx(page_q))]
                if ftype != "text" and model_q != page_q:
                    styles.append(("fabricated_model_style", model_q))
                if page_q == ONLY_TRUE:
                    styles = []
                for style, q in styles:
                    res = judge(doc, idx, q, val, ftype, models)
                    out.append({**m_row, "quote_style": style, **res})
                res = judge(doc, idx, ctx(g.text), val, ftype, models)
                out.append({**m_row, "quote_style": "true_quote", **res})
    return out


#: Characters an OCR engine confuses, and what it reads instead. A page is garbled by
#: replacing one such character in one annotated word; the table is the study's own choice
#: (the usual look-alikes), not measured from an OCR engine.
OCR_CONFUSIONS = {
    "O": "0", "0": "O", "l": "1", "1": "l", "I": "l", "S": "5", "5": "S",
    "B": "8", "8": "B", "o": "0", "e": "c", "a": "o", "D": "O", "Q": "O",
}  # fmt: skip


def _garble(doc, idx: list[int], rng: random.Random):
    """The document with one look-alike character replaced in one of the gold words."""
    from fieldproof.document.model import Document, Page, Word

    page = doc.pages[0]
    options = [(i, j) for i in idx for j, c in enumerate(page.words[i].text) if c in OCR_CONFUSIONS]
    if not options:
        return None
    i, j = rng.choice(options)
    text = page.words[i].text
    bad = text[:j] + OCR_CONFUSIONS[text[j]] + text[j + 1 :]
    words, parts, pos = [], [], 0
    for k, w in enumerate(page.words):
        t = bad if k == i else w.text
        if parts:
            pos += 1
        words.append(Word(text=t, bbox=w.bbox, start=pos, end=pos + len(t)))
        parts.append(t)
        pos += len(t)
    garbled = Document(
        source=doc.source,
        pages=[
            Page(number=1, width=page.width, height=page.height, text=" ".join(parts), words=words)
        ],
    )
    return garbled


def ocr_rows(specs, models):
    """Measurement 4: the page text has one OCR-garbled character in the name. Three things a
    model can do with it: copy the garbled text as the quote and repair it in the value (A);
    repair both (B); copy it into both, so the value says what the page says (C)."""
    out = []
    for case in specs:
        for gi, g in enumerate(case["golds"]):
            if FIELD_TYPE[g.kind] != "text":
                continue
            doc = _garble(case["doc"], g.word_idx, rng_for(case["id"], g.kind, gi, "ocr"))
            if doc is None:
                continue
            label = label_before(doc, g.word_idx)
            garbled_text = " ".join(doc.pages[0].words[i].text for i in g.word_idx)
            base = {
                "doc": case["id"], "dataset": case["dataset"], "split": case["split"],
                "kind": g.kind, "ftype": "text", "gi": gi, "measure": "ocr_garble",
                "present_elsewhere": False, "locale_ambiguous": False,
            }  # fmt: skip
            for variant, quote, value in (
                ("A_quote_copied_value_repaired", f"{label} {garbled_text}".strip(), g.text),
                ("B_quote_and_value_repaired", f"{label} {g.text}".strip(), g.text),
                ("C_quote_and_value_copied", f"{label} {garbled_text}".strip(), garbled_text),
            ):
                res = judge(doc, set(g.word_idx), quote, value, "text", models)
                out.append({**base, "variant": variant, "quote_style": "page_context", **res})
    return out


def load_cases():
    import adapt

    cache = HERE / "cache"
    cases = []
    cases += adapt.cord_cases(str(next(cache.glob("train-00000-of-00004-*.parquet"))), "A")
    cases += adapt.cord_cases(str(next(cache.glob("validation-*.parquet"))), "B")
    cases += adapt.cord_cases(str(next(cache.glob("test-*.parquet"))), "B")
    cases += adapt.sroie_cases(str(next(cache.glob("train-00000-of-00001-*.parquet"))))
    return cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="fieldproof src directory to measure")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tolerance", type=int, default=0, help="text_edit_tolerance for verify")
    ap.add_argument("--ocr", action="store_true", help="measure OCR-garbled pages instead")
    ap.add_argument(
        "--stated",
        action="store_true",
        help="tell verify each dataset's number and date conventions (see STATED)",
    )
    a = ap.parse_args()
    src = str(Path(a.src).resolve())
    sys.path.insert(0, src)
    import fieldproof

    print("measuring", fieldproof.__file__, file=sys.stderr)
    cases = load_cases()
    if a.limit:
        cases = cases[: a.limit] + [c for c in cases if c.dataset == "sroie"][: a.limit]
    # "other document" pools: the same kind of field from the other documents of the dataset
    pools: dict[tuple[str, str], list] = {}
    for c in cases:
        for g in c.golds:
            pools.setdefault((c.dataset, g.kind), []).append((c.doc_id, g))
    specs = []
    for c in cases:
        others = {}
        for g in c.golds:
            pool = [p for d, p in pools[(c.dataset, g.kind)] if d != c.doc_id]
            others[g.kind] = pool[:: max(1, len(pool) // 200)]  # at most ~200, spread over the set
        specs.append(
            {
                "id": c.doc_id,
                "dataset": c.dataset,
                "split": c.split,
                "doc": c.document,
                "golds": c.golds,
                "others": others,
            }
        )
    mode = "ocr" if a.ocr else "main"
    chunks = [
        (src, a.tolerance, specs[i :: a.workers * 8], mode, a.stated) for i in range(a.workers * 8)
    ]
    with Pool(a.workers) as pool, open(a.out, "w") as fh:
        for rows in pool.imap_unordered(process, chunks):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    print("done", file=sys.stderr)


if __name__ == "__main__":
    main()
