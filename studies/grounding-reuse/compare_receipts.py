"""Require identical complete rows from two fresh retained receipt-corpus replays."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

KEY = ("doc", "gi", "measure", "variant", "quote_style")


def read(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        key = tuple(row.get(name) for name in KEY)
        if key in result:
            raise ValueError(f"duplicate case: {key}")
        result[key] = row
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    before, after = read(args.before), read(args.after)
    assert before.keys() == after.keys()
    assert len(before) == 133722
    assert len({row["doc"] for row in before.values()}) == 1052
    changed = [key for key in before if before[key] != after[key]]
    assert not changed, f"changed complete rows: {changed[:20]}"
    rows = [before[key] for key in sorted(before)]
    result = {
        "cases": len(rows),
        "documents": len({row["doc"] for row in rows}),
        "complete_row_changes": len(changed),
        "before_file_sha256": hashlib.sha256(args.before.read_bytes()).hexdigest(),
        "after_file_sha256": hashlib.sha256(args.after.read_bytes()).hexdigest(),
        "canonical_complete_rows_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "counts": dict(Counter(row["status"] for row in rows)),
        "scope": "Compatibility with the retained corpus adapter; not a new accuracy estimate.",
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
