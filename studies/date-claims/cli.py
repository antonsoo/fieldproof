"""Exercise actual extraction CLI calls against the retained synthetic PDF."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from run import CASES, fixture

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--src", type=Path)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--scratch", type=Path, required=True)
parser.add_argument("--observe-only", action="store_true")
args = parser.parse_args()
args.scratch.mkdir(parents=True, exist_ok=True)
environment = os.environ.copy()
if args.src:
    environment["PYTHONPATH"] = str(args.src.resolve())
else:
    environment.pop("PYTHONPATH", None)
cli = Path(sys.executable).parent / "fieldproof"
pdf = Path(__file__).resolve().parent / "date-claims.pdf"
results = []
for name, issue, due, issue_status, due_status, chronology in CASES:
    input_path = args.scratch / f"{name}.json"
    input_path.write_text(json.dumps(fixture(issue, due)))
    output = args.scratch / f"{name}-report.json"
    process = subprocess.run(
        [
            str(cli),
            "extract",
            str(pdf),
            "--schema",
            "invoice",
            "--fixture",
            str(input_path),
            "--out",
            str(output),
            "--date-order",
            "dmy",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(output.read_text())
    fields = {
        f["path"]: f for f in report["report"]["fields"] if f["path"] in ("issue_date", "due_date")
    }
    check = next(
        c for c in report["report"]["cross_field_checks"] if c["rule"] == "invoice.due_date_order"
    )
    actual = [fields["issue_date"]["status"], fields["due_date"]["status"], check["status"]]
    expected = [issue_status, due_status, chronology]
    results.append(
        {
            "case": name,
            "exit_code": process.returncode,
            "expected": expected,
            "actual": actual,
            "agrees": actual == expected,
            "fields": fields,
            "date_check": check,
        }
    )
receipt = {
    "python": platform.python_version(),
    "scope": "Actual fixture-provider CLI calls on synthetic PDF; no model calls.",
    "cases": len(results),
    "disagreements": sum(not r["agrees"] for r in results),
    "results": results,
}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(receipt, indent=2) + "\n")
print(f"{receipt['cases']} CLI cases, {receipt['disagreements']} disagreements")
if not args.observe_only and receipt["disagreements"]:
    raise SystemExit(1)
