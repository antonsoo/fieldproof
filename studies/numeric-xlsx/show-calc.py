"""Print captured native spreadsheet outcomes; no calculator or simulated reader."""

import json
from pathlib import Path
import sys

calc = json.loads(Path(sys.argv[1]).read_text())
before = json.loads(Path(sys.argv[2]).read_text())
print(calc["engine"])
print(f"Actual workbooks: {calc['workbooks']}; observed rows: {calc['observations']}")
print()
print(f"{'Source integer':<32} {'Before: numeric value':<24} After: literal text")
for case in calc["beforeChangedIntegerCases"]:
    old = next(row for row in calc["records"] if row["case"] == case and row["phase"] == "before" and row["file"].endswith("writer-all.xlsx"))
    new = next(row for row in calc["records"] if row["case"] == case and row["phase"] == "after" and row["file"].endswith("writer-all.xlsx"))
    assert new["agrees"]
    print(f"{old['sourceSpelling']:<32} {old['value']['number']:<24} {new['value']['text']}")
error = next(row for row in before["records"] if row.get("error") == "OverflowError")
retained = next(row for row in calc["records"] if row["case"] == error["case"] and row["phase"] == "after")
assert retained["agrees"]
print()
print(f"{len(retained['value']['text'])}-digit integer: before {error['error']}; after exact text retained.")
print(f"Corrected native-reader disagreements: {calc['afterDisagreements']}")
