"""Pair complete receipt replays and retain every changed decision plus remaining errors."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

IDENTITY = ("doc", "description_line", "target_line", "kind")
INPUT = (*IDENTITY, "claimed_line", "category", "repeated", "value", "quote", "expected_boxes")


def read(directory: Path) -> tuple[dict, dict]:
    summary = json.loads((directory / "summary.json").read_text())
    raw = (directory / "rows.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == summary["rows_sha256"]
    rows = {}
    for line in raw.splitlines():
        row = json.loads(line)
        key = tuple(row[k] for k in IDENTITY)
        assert key not in rows
        rows[key] = row
    assert len(rows) == summary["cases"]
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--before-ref", default="c7f7cbc")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    before_summary, before = read(args.before)
    after_summary, after = read(args.after)
    assert before.keys() == after.keys()
    assert before_summary["sources"] == after_summary["sources"]
    transitions: Counter = Counter()
    changes = []
    remaining = []
    remaining_all = []
    for key, left in before.items():
        right = after[key]
        assert all(left[k] == right[k] for k in INPUT)
        transitions[(left["outcome"], right["outcome"])] += 1
        if left["outcome"] != right["outcome"]:
            changes.append(
                {
                    **{k: left[k] for k in INPUT},
                    "before": left["outcome"],
                    "after": right["outcome"],
                    "before_rects": left["result"]["rects"],
                    "after_rects": right["result"]["rects"],
                    "reasons": right["result"]["reasons"],
                    "row_checks": right.get("row_checks", []),
                }
            )
        if right["repeated"] and right["outcome"] == "verified_wrong":
            remaining.append(right)
        if right["outcome"] == "verified_wrong":
            remaining_all.append(right)
    result = {
        "baseline_commit": args.before_ref,
        "before": before_summary,
        "after": after_summary,
        "transitions": [
            {"before": b, "after": a, "n": n} for (b, a), n in sorted(transitions.items())
        ],
        "changes": changes,
        "remaining_repeated_quote_errors": remaining,
        "remaining_verified_errors": remaining_all,
    }
    args.out.write_text(
        json.dumps(result, indent=None if args.compact else 2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({"paired_cases": len(before), "transitions": result["transitions"]}, indent=2))
    assert transitions[("verified_correct", "verified_wrong")] == 0


if __name__ == "__main__":
    main()
