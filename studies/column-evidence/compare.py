"""Pair identical PDF/input cases; distinguish a verdict change from changed evidence."""

import argparse
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("before", type=Path)
parser.add_argument("after", type=Path)
parser.add_argument("out", type=Path)
args = parser.parse_args()
before = json.loads(args.before.read_text())
after = json.loads(args.after.read_text())
changed = []
for a, b in zip(before, after, strict=True):
    for key in ("id", "pdf_sha256", "input_sha256", "arithmetic_sha256", "line_extension"):
        assert a[key] == b[key], (a["id"], key)
    for name, field in a["fields"].items():
        actual = b["fields"][name]
        assert field["matched_text"] == actual["matched_text"] and field["rects"] == actual["rects"]
        if field["status"] != actual["status"]:
            assert field["status"] == "verified" and actual["status"] == "needs_review"
            assert "swapped" in a["id"]
            changed.append({"case": a["id"], "field": name})
summary = {
    "cases": len(after),
    "identical_pdf_and_input_pairs": len(after),
    "unchanged_arithmetic_ledgers": len(after),
    "unchanged_item_source_locations": sum(len(r["fields"]) for r in after),
    "column_checks": dict(Counter(c for r in after for c in r["column_statuses"])),
    "changed_fields": len(changed),
    "changes": changed,
    "scope": "Constructed PDFs and scripted claims; not an extraction accuracy estimate.",
}
args.out.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "changes"}))
