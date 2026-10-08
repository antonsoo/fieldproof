"""Pair two complete receipt runs; retain verdict changes and aggregate every row.

    python3 studies/numeric-evidence/compare_receipts.py BEFORE.jsonl AFTER.jsonl OUT.json \
        --before-ref BEFORE_COMMIT --after-ref AFTER_COMMIT

The original study's adapter and ground-truth rules are unchanged. Its labels are
not an independent oracle for every spelling (see README's audit of changed cases).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

KEY = ("doc", "gi", "measure", "variant", "quote_style")
INPUT = KEY + ("ftype", "kind", "quote", "value", "present_elsewhere", "locale_ambiguous")


def read(path: Path) -> dict:
    rows = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            key = tuple(row.get(name) for name in KEY)
            if key in rows:
                raise ValueError(f"duplicate case: {key}")
            rows[key] = row
    if not rows:
        raise ValueError("empty receipt run")
    return rows


def aggregate(rows: dict) -> list[dict]:
    counts = Counter()
    groups = ("measure", "ftype", "quote_style", "present_elsewhere")
    for row in rows.values():
        where = tuple(row.get(name) for name in groups)
        outcome = (
            ("right" if row["place_ok"] else "wrong")
            if row["status"] == "verified"
            else row["status"]
        )
        counts[(*where, outcome)] += 1
    return [
        dict(zip((*groups, "outcome"), key, strict=True)) | {"n": n}
        for key, n in sorted(counts.items(), key=lambda item: str(item[0]))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--before-ref", required=True, help="source revision used for BEFORE")
    parser.add_argument("--after-ref", required=True, help="source revision used for AFTER")
    parser.add_argument("--expected-cases", type=int, default=133722)
    parser.add_argument("--expected-documents", type=int, default=1052)
    args = parser.parse_args()
    before_path, after_path, out = args.before, args.after, args.out
    before, after = read(before_path), read(after_path)
    if before.keys() != after.keys():
        raise ValueError("the runs contain different cases")
    documents = len({row["doc"] for row in before.values()})
    if len(before) != args.expected_cases or documents != args.expected_documents:
        raise ValueError("the runs do not contain the expected complete corpus")
    changes = []
    for key in sorted(before):
        left, right = before[key], after[key]
        if any(left.get(name) != right.get(name) for name in INPUT):
            raise ValueError(f"the input changed for {key}")
        if (left["status"], left["place_ok"]) != (right["status"], right["place_ok"]):
            changes.append({"before": left, "after": right})
    result = {
        "before_commit": args.before_ref,
        "after_commit": args.after_ref,
        "before_rows_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
        "after_rows_sha256": hashlib.sha256(after_path.read_bytes()).hexdigest(),
        "cases": len(before),
        "documents": documents,
        "same_inputs": True,
        "before": aggregate(before),
        "after": aggregate(after),
        "verdict_or_location_changes": changes,
    }
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        f"{result['cases']} paired cases on {result['documents']} receipts; "
        f"{len(changes)} verdict/location changes"
    )
    print(
        Counter(
            (c["before"]["ftype"], c["before"]["status"], c["after"]["status"]) for c in changes
        )
    )
    for side in ("before", "after"):
        print(side)
        for ftype in ("amount", "count", "date", "text"):
            present = Counter()
            absent = Counter()
            for cell in result[side]:
                if cell["ftype"] != ftype:
                    continue
                if cell["measure"] == "present_written" and cell["quote_style"] == "page_context":
                    present[cell["outcome"]] += cell["n"]
                if cell["measure"] == "absent" and not cell["present_elsewhere"]:
                    absent[cell["outcome"]] += cell["n"]
            print(ftype, "present with context:", dict(present), "absent:", dict(absent))


if __name__ == "__main__":
    main()
