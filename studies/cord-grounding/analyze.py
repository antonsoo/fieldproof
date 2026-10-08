"""Aggregate `run.py` rows into results.json and print the markdown tables.

    python3 -I analyze.py released=a.jsonl,b.jsonl checkout=c.jsonl,d.jsonl \
        tol1=e.jsonl,f.jsonl stated=g.jsonl

Each version is a comma-separated list of row files (the main run and the `--ocr` run). The
versions are the released 0.2.7, this checkout with its default settings, this checkout
with `text_edit_tolerance=1`, and this checkout told each dataset's number and date
conventions (`run.py --stated`).

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
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = (
    "split",
    "dataset",
    "measure",
    "ftype",
    "kind",
    "quote_style",
    "variant",
    "present_elsewhere",
    "locale_ambiguous",
)
COUNTS = ("n", "right", "wrong", "review", "nothing", "grounded_any", "candidate_at_gold")
FTYPES = ("amount", "count", "date", "text")
NAME = {"count": "quantity"}
BOTH = {"A", "B"}


def outcome(r: dict) -> str:
    if r["status"] == "verified":
        return "right" if r["place_ok"] else "wrong"
    return "review" if r["status"] == "needs_review" else "nothing"


def read_rows(paths: str):
    for path in paths.split(","):
        with open(path) as fh:
            for line in fh:
                yield json.loads(line)


def aggregate(paths: str) -> list[dict]:
    acc: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    for r in read_rows(paths):
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


def acc_of(t: dict) -> int:
    return t["right"] + t["wrong"]


def reason_class(reason: str) -> str:
    for needle, name in (
        ("ambiguous (appears", "quote occurs more than once"),
        ("the evidence date", "numeric date could be day-first or month-first"),
        ("the evidence number", "number could have a decimal point or a thousands separator"),
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


def data_summary(paths: str) -> dict:
    """Documents and annotated fields, and the cases of measurement 3, counted from raw rows."""
    docs: dict[str, set] = defaultdict(set)
    fields: dict[str, int] = defaultdict(int)
    dup: dict[str, int] = defaultdict(int)
    absent = {"cases": 0, "value_also_on_page": 0}
    reasons: dict[str, int] = defaultdict(int)
    for r in read_rows(paths):
        if r["measure"] == "ocr_garble":
            continue
        docs[f"{r['dataset']}/{r['split']}"].add(r["doc"])
        if r["measure"] == "present_written" and r["quote_style"] == "page":
            fields[f"{r['dataset']}/{r['split']}/{r['ftype']}"] += 1
            if r["dup_on_page"] > 1:  # the bare value as written, offered with nothing around it
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


# ------------------------------------------------------------------ intervals


def cell_intervals(paths: str, cells: dict[str, dict]) -> dict:
    """For each named cell of measurement 3, the accepted share with a 95% interval that
    treats a receipt as the unit (receipts hold up to ~15 cases that move together).

    With five or more accepts: percentile bootstrap over receipts, 2,000 resamples, seed 1.
    With fewer: an upper bound of (3.0, 4.74, 6.30, 7.75, 9.15)[accepts] / (receipts in the
    cell), the exact Poisson 95% limit (the rule of three for none) applied to receipts, which
    also bounds the share of cases."""
    per_doc: dict[str, dict[str, list[int]]] = {name: defaultdict(lambda: [0, 0]) for name in cells}
    for r in read_rows(paths):
        if r["measure"] != "absent" or r["present_elsewhere"]:
            continue
        for name, where in cells.items():
            if all(
                r.get(k) in v if isinstance(v, set) else r.get(k) == v for k, v in where.items()
            ):
                c = per_doc[name][r["doc"]]
                c[0] += 1
                c[1] += r["status"] == "verified"
    out = {}
    rng = random.Random(1)
    for name, docs in per_doc.items():
        ns = [v[0] for v in docs.values()]
        ks = [v[1] for v in docs.values()]
        n, k, m = sum(ns), sum(ks), len(ns)
        if not m:
            continue
        entry = {"cases": n, "accepted": k, "receipts": m, "share": k / n}
        if k < 5:
            # exact Poisson 95% upper limit on the number of receipts with an accept
            entry["upper_95"] = min(1.0, (3.0, 4.74, 6.30, 7.75, 9.15)[k] / m)
        else:
            shares = []
            for _ in range(2000):
                idx = [rng.randrange(m) for _ in range(m)]
                sn = sum(ns[i] for i in idx)
                shares.append(sum(ks[i] for i in idx) / sn if sn else 0.0)
            shares.sort()
            entry["lower_95"], entry["upper_95"] = shares[50], shares[1949]
        out[name] = entry
    return out


CELLS = {
    "amount, last digit off by one, label + wrong value": {
        "ftype": "amount", "variant": "last_digit_off_by_one", "quote_style": "fabricated_context",
    },
    "amount, last digit off by one, SROIE totals": {
        "ftype": "amount", "variant": "last_digit_off_by_one", "quote_style": "fabricated_context",
        "dataset": "sroie",
    },
    "text, one letter changed, label + wrong value": {
        "ftype": "text", "variant": "one_char_changed", "quote_style": "fabricated_context",
    },
    "amount, any wrong value (not scaled), label + wrong value": {
        "ftype": "amount", "quote_style": "fabricated_context",
    },
    "amount, any wrong value (not scaled), true quote": {
        "ftype": "amount", "quote_style": "true_quote",
    },
    "date, any wrong value, label + wrong value": {
        "ftype": "date", "quote_style": "fabricated_context",
    },
    "text, any wrong value, label + wrong value": {
        "ftype": "text", "quote_style": "fabricated_context",
    },
}  # fmt: skip


# ------------------------------------------------------------------ tables


def versions_cols(names: list[str], fn) -> str:
    return " | ".join(fn(n) for n in names)


def main_table(rows: dict, names: list[str], split) -> list[str]:
    out = []
    cols = [
        ("right place, value as written", "present_written", "page_context", "right"),
        ("right place, value rewritten", "present_model", "page_context", "right"),
        ("right place, value and quote rewritten (bare)", "present_model", "model", "right"),
    ]
    for title, measure, style, key in cols:
        out.append(f"\n{title} (split {sorted(split)})")
        out.append("| field type | n | " + " | ".join(names) + " |")
        out.append("|---|---:|" + "---:|" * len(names))
        for ft in FTYPES:
            w = {"split": split, "measure": measure, "quote_style": style, "ftype": ft}
            t = {n: total(rows[n], **w) for n in names}
            n0 = t[names[0]]["n"]
            out.append(
                f"| {NAME.get(ft, ft)} | {n0} | "
                + " | ".join(pct(t[n][key], t[n]["n"]) for n in names)
                + " |"
            )
    for style in ("fabricated_context", "true_quote"):
        out.append(
            f"\naccepted although the value is not on the page, {style} (split {sorted(split)})"
        )
        out.append("| field type | n | " + " | ".join(names) + " |")
        out.append("|---|---:|" + "---:|" * len(names))
        for ft in FTYPES:
            parts = []
            for n in names:
                t = {"n": 0, "right": 0, "wrong": 0}
                for r in rows[n]:
                    if (
                        r["measure"] == "absent"
                        and r["split"] in split
                        and r["ftype"] == ft
                        and r["quote_style"] == style
                        and not r["present_elsewhere"]
                        and r["variant"] != "scaled_wrong"
                    ):
                        for c in t:
                            t[c] += r[c]
                parts.append((t["n"], pct(t["right"] + t["wrong"], t["n"])))
            out.append(
                f"| {NAME.get(ft, ft)} | {parts[0][0]} | " + " | ".join(p[1] for p in parts) + " |"
            )
    return out


def dataset_table(rows: dict, names: list[str]) -> list[str]:
    cases = [
        ("SROIE total", "last_digit_off_by_one", {"dataset": "sroie", "kind": "total"}),
        ("CORD amounts", "last_digit_off_by_one", {"dataset": "cord", "ftype": "amount"}),
        ("SROIE total", "digit_changed", {"dataset": "sroie", "kind": "total"}),
        ("CORD amounts", "digit_changed", {"dataset": "cord", "ftype": "amount"}),
        ("CORD item name", "one_char_changed", {"dataset": "cord", "kind": "item_name"}),
        ("SROIE company", "one_char_changed", {"dataset": "sroie", "kind": "company"}),
        ("SROIE address", "one_char_changed", {"dataset": "sroie", "kind": "address"}),
        ("SROIE date", "day_plus_1", {"dataset": "sroie", "kind": "date"}),
        ("SROIE date", "day_month_swapped", {"dataset": "sroie", "kind": "date"}),
    ]
    out = [
        "| field | wrong value | n | " + " | ".join(names) + " |",
        "|---|---|---:|" + "---:|" * len(names),
    ]
    for label, variant, where in cases:
        w = {"split": BOTH, "measure": "absent", "quote_style": "fabricated_context",
             "variant": variant, "present_elsewhere": False, **where}  # fmt: skip
        t = {n: total(rows[n], **w) for n in names}
        out.append(
            f"| {label} | {variant} | {t[names[0]]['n']} | "
            + " | ".join(f"{acc_of(t[n])} ({pct(acc_of(t[n]), t[n]['n'])})" for n in names)
            + " |"
        )
    return out


def ocr_table(rows: dict, names: list[str]) -> list[str]:
    out = [
        "| names with one garbled character | dataset | n | "
        + " | ".join(f"{n}: right place / review" for n in names)
        + " |",
        "|---|---|---:|" + "---:|" * len(names),
    ]
    for variant in (
        "A_quote_copied_value_repaired",
        "B_quote_and_value_repaired",
        "C_quote_and_value_copied",
    ):
        for ds in ("cord", "sroie", {"cord", "sroie"}):
            w = {"measure": "ocr_garble", "variant": variant, "dataset": ds}
            t = {n: total(rows[n], **w) for n in names}
            label = ds if isinstance(ds, str) else "both"
            out.append(
                f"| {variant} | {label} | {t[names[0]]['n']} | "
                + " | ".join(
                    f"{t[n]['right']} ({pct(t[n]['right'], t[n]['n'])}) / {t[n]['review']}"
                    for n in names
                )
                + " |"
            )
    return out


def thousands_table(paths: dict[str, str]) -> dict:
    """Wrong-by-a-thousand (or by ten) values offered with the true quote, on amounts whose
    value is written d.ddd or d,ddd. These are left out of the other tables because the
    wrong value is also a reading of a token on the page. An amount of zero is counted apart:
    a thousandth of it, or ten times it, is the same value, so accepting it is not an error."""
    out: dict[str, dict] = {}
    for name, path in paths.items():
        c: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in read_rows(path):
            if (
                r["measure"] != "absent"
                or r["variant"] != "scaled_wrong"
                or r["quote_style"] != "true_quote"
            ):
                continue
            form = (
                "amounts of zero (the scaled value is the true value)"
                if r["value"] == 0
                else "dot_thousands (60.000 offered as 60)"
                if r["locale_ambiguous"] and "," not in r["quote"].split()[-1]
                else "comma_thousands (60,000 offered as 60)"
                if r["locale_ambiguous"]
                else "other_amounts (offered as ten times the value)"
            )
            c[form][0] += 1
            c[form][1] += r["status"] == "verified"
        out[name] = {k: {"cases": v[0], "accepted": v[1]} for k, v in sorted(c.items())}
    return out


def unsettled_table(paths: dict[str, str]) -> dict:
    """The fields a document can leave unsettled, with the true value and the true quote:
    amounts written d.ddd, and dates whose day and month are both 12 or under. How many each
    version verifies, and how many it accepts when the value is the other reading (a thousand
    times too small, or day and month swapped)."""
    out: dict[str, dict] = {}
    for name, path in paths.items():
        c: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in read_rows(path):
            if r["quote_style"] not in ("page_context", "true_quote"):
                continue
            true = r["measure"] == "present_written"
            if r["ftype"] == "amount" and r["locale_ambiguous"]:
                if not true and (r["measure"] != "absent" or r["variant"] != "scaled_wrong"):
                    continue
                form = "amount d,ddd" if "," in r["quote"].split()[-1] else "amount d.ddd"
            elif r["ftype"] == "date":
                if not true and (r["measure"] != "absent" or r["variant"] != "day_month_swapped"):
                    continue
                form = "date"
            else:
                continue
            key = f"{r['dataset']} {form}, {'true value' if true else 'other reading'}"
            c[key]["cases"] += 1
            c[key]["verified"] += r["status"] == "verified"
            c[key]["verified_at_the_right_place"] += r["status"] == "verified" and bool(
                r["place_ok"]
            )
        out[name] = {k: dict(v) for k, v in sorted(c.items())}
    return out


def main() -> None:
    versions = dict(a.split("=", 1) for a in sys.argv[1:])
    names = list(versions)
    rows = {v: aggregate(p) for v, p in versions.items()}
    summary = {v: data_summary(p) for v, p in versions.items()}
    intervals = {v: cell_intervals(p, CELLS) for v, p in versions.items()}
    thousands = thousands_table(versions)
    unsettled = unsettled_table(versions)
    extra = HERE / "thousands.json"
    out = {
        "summary": summary,
        "intervals": intervals,
        "scaled_wrong_true_quote": thousands,
        "unsettled_numbers_and_dates": unsettled,
        "dot_thousands_settled_by_document": json.loads(extra.read_text())
        if extra.exists()
        else None,
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    print("written results.json\n")
    for split in (BOTH, {"A"}, {"B"}):
        print("\n".join(main_table(rows, names, split)))
        print()
    print("### by dataset and field, label + wrong value, both halves")
    print("\n".join(dataset_table(rows, names)))
    print("\n### OCR-garbled name, both halves")
    print("\n".join(ocr_table(rows, names)))
    print("\n### intervals")
    for v in names:
        for k, e in intervals[v].items():
            print(v, k, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in e.items()})
    print("\n### scaled_wrong true quote")
    print(json.dumps(thousands, indent=1))
    print("\n### unsettled numbers and dates: cases / verified / verified at the right place")
    for key in sorted({k for v in unsettled.values() for k in v}):
        cells = []
        for v in names:
            e = unsettled[v].get(key, {})
            cells.append(
                f"{v} {e.get('cases', 0)}/{e.get('verified', 0)}"
                f"/{e.get('verified_at_the_right_place', 0)}"
            )
        print(f"{key}: " + "  ".join(cells))


if __name__ == "__main__":
    main()
