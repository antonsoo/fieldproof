"""Aggregate `run.py` rows into results.json and print the markdown tables.

    python3 -I analyze.py released=cache/rows-released.jsonl checkout=cache/rows-checkout.jsonl

Outcome of a case, from the status `verify` gave it:

  right    verified, and the highlighted words are the annotated ones
  wrong    verified, but the highlight is somewhere else on the page
  review   needs_review (ambiguous quote, weak match, or the value check disagreed)
  nothing  unsupported (the quote was not found)

For cases where the value is NOT on the page (measurement 3) any `right` or `wrong` is a
false accept; the tables report `right + wrong` as "accepted".
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

KEYS = (
    "split",
    "dataset",
    "measure",
    "ftype",
    "quote_style",
    "variant",
    "present_elsewhere",
    "locale_ambiguous",
)
COUNTS = ("n", "right", "wrong", "review", "nothing", "grounded_any", "candidate_at_gold")


def outcome(r: dict) -> str:
    if r["status"] == "verified":
        return "right" if r["place_ok"] else "wrong"
    return "review" if r["status"] == "needs_review" else "nothing"


def aggregate(path: str) -> list[dict]:
    acc: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            a = acc[tuple(r.get(k, False) for k in KEYS)]
            a["n"] += 1
            a[outcome(r)] += 1
            a["grounded_any"] += r["n_cands"] > 0
            a["candidate_at_gold"] += bool(r["cand_right"])
    return [
        dict(zip(KEYS, k, strict=True)) | {c: v.get(c, 0) for c in COUNTS}
        for k, v in sorted(acc.items(), key=lambda kv: str(kv[0]))
    ]


def total(rows: list[dict], **where) -> dict:
    """Sum the counts of the rows matching every `key=value` (a value may be a set)."""
    t = dict.fromkeys(COUNTS, 0)
    for r in rows:
        if all(
            (r[k] in v) if isinstance(v, set | frozenset) else r[k] == v for k, v in where.items()
        ):
            for c in COUNTS:
                t[c] += r[c]
    return t


def pct(a: int, n: int) -> str:
    return f"{100 * a / n:.1f}%" if n else "-"


FTYPES = ("amount", "count", "date", "text")


def present_table(rows: dict[str, list[dict]], split: str, measure: str, style: str) -> list[str]:
    out = [
        "| field type | n | released: right place | wrong place | review | not found "
        "| this checkout: right place | wrong place | review | not found |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ft in (*FTYPES, "all"):
        w = {"split": split, "measure": measure, "quote_style": style}
        if ft != "all":
            w["ftype"] = ft
        a, b = total(rows["released"], **w), total(rows["checkout"], **w)
        n = a["n"]
        out.append(
            f"| {ft} | {n} | "
            + " | ".join(pct(a[k], n) for k in ("right", "wrong", "review", "nothing"))
            + " | "
            + " | ".join(pct(b[k], b["n"]) for k in ("right", "wrong", "review", "nothing"))
            + " |"
        )
    return out


def absent_table(
    rows: dict[str, list[dict]], split: str, style: str, by: str = "ftype"
) -> list[str]:
    out = [
        f"| {by} | n | released: accepted | unsupported | this checkout: accepted | unsupported |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    if by == "ftype":
        groups = [((ft,), {"ftype": ft}) for ft in FTYPES]
    else:
        pairs = sorted(
            {(r["ftype"], r["variant"]) for r in rows["released"] if r["measure"] == "absent"}
        )
        groups = [(p, {"ftype": p[0], "variant": p[1]}) for p in pairs]
    for label, extra in groups:
        w = {
            "split": split,
            "measure": "absent",
            "quote_style": style,
            "present_elsewhere": False,
            **extra,
        }
        a, b = total(rows["released"], **w), total(rows["checkout"], **w)
        if not a["n"]:
            continue
        out.append(
            f"| {' / '.join(label)} | {a['n']} | {pct(a['right'] + a['wrong'], a['n'])}"
            f" | {pct(a['nothing'], a['n'])}"
            f" | {pct(b['right'] + b['wrong'], b['n'])} | {pct(b['nothing'], b['n'])} |"
        )
    return out


def reason_class(reason: str) -> str:
    for needle, name in (
        ("ambiguous (appears", "quote occurs more than once"),
        ("the evidence date", "numeric date could be day-first or month-first"),
        ("matches neither reading", "numeric date matches neither reading"),
        ("could not parse a date", "date format not read"),
        ("does not match", "value differs from the number in the evidence"),
        ("could not parse a number", "number not read"),
        ("the quote is", "letters or digits differ from the page"),
        ("evidence match quality", "weak fuzzy match"),
        ("none of the evidence quotes", "quote not found"),
        ("not a parseable", "value not parseable"),
        ("only", "string value not similar enough"),
    ):
        if needle in reason:
            return name
    return reason[:50] or "other"


def data_summary(path: str) -> dict:
    """Documents and annotated fields, and the cases of measurement 3, counted from raw rows."""
    docs: dict[str, set] = defaultdict(set)
    fields: dict[str, int] = defaultdict(int)
    dup: dict[str, int] = defaultdict(int)
    absent = {"cases": 0, "value_also_on_page": 0}
    reasons: dict[str, int] = defaultdict(int)
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            docs[f"{r['dataset']}/{r['split']}"].add(r["doc"])
            if r["measure"] == "present_written" and r["quote_style"] == "page":
                fields[f"{r['dataset']}/{r['split']}/{r['ftype']}"] += 1
                # the bare value as written, offered with nothing around it
                if r["dup_on_page"] > 1:
                    dup["fields_whose_value_is_written_more_than_once"] += 1
                    dup[outcome(r)] += 1
            if (
                r["measure"] == "present_written"
                and r["quote_style"] == "page_context"
                and r["status"] != "verified"
            ):
                reasons[f"{r['ftype']}: {reason_class(r['reason'])}"] += 1
            if r["measure"] == "absent" and r["quote_style"] == "true_quote":
                absent["cases"] += 1
                absent["value_also_on_page"] += bool(r["present_elsewhere"])
    return {
        "documents": {k: len(v) for k, v in sorted(docs.items())},
        "annotated_fields": dict(sorted(fields.items())),
        "bare_value_written_more_than_once": dict(dup),
        "not_verified_with_label_as_written": dict(sorted(reasons.items())),
        "measurement_3_cases_before_exclusion": absent,
    }


def main() -> None:
    versions = dict(a.split("=", 1) for a in sys.argv[1:])
    rows = {v: aggregate(p) for v, p in versions.items()}
    summary = {v: data_summary(p) for v, p in versions.items()}
    Path(__file__).with_name("results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n"
    )
    print("written results.json\n")
    for split in ("heldout", "dev"):
        print(f"### {split}: value on the page, quoted as written with its label (measurement 1)")
        print("\n".join(present_table(rows, split, "present_written", "page_context")))
        print(
            f"\n### {split}: value rewritten by a model, quote verbatim with label (measurement 2a)"
        )
        print("\n".join(present_table(rows, split, "present_model", "page_context")))
        print(f"\n### {split}: value and quote both rewritten, bare (measurement 2b)")
        print("\n".join(present_table(rows, split, "present_model", "model")))
        for style in ("fabricated_context", "fabricated", "true_quote"):
            print(f"\n### {split}: value NOT on the page, {style} (measurement 3), by field type")
            print("\n".join(absent_table(rows, split, style)))
            print(f"\n### {split}: value NOT on the page, {style}, by kind of error")
            print("\n".join(absent_table(rows, split, style, by="variant")))
        print()


if __name__ == "__main__":
    main()
