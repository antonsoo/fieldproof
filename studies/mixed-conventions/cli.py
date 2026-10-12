"""Exercise both installed CLI entry points and every fallback pair on the example."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bin", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
pdf = root / "examples/mixed-conventions.pdf"
original = json.loads((root / "examples/fixtures/mixed-conventions.json").read_text())
rows = []
with TemporaryDirectory(prefix="fieldproof-mixed-") as folder:
    scratch = Path(folder)
    for style in (None, "decimal", "thousands"):
        for order in (None, "mdy", "dmy"):
            for amount, date in [(60, "2026-03-04"), (60000, "2026-04-03")]:
                original["data"]["total"]["value"] = amount
                original["data"]["issue_date"]["value"] = date
                fixture, output = scratch / "fixture.json", scratch / "result.json"
                fixture.write_text(json.dumps(original))
                for entry in ("verify", "extract"):
                    command = [str(args.bin.resolve()), entry]
                    command += (
                        [str(fixture), str(pdf)]
                        if entry == "verify"
                        else [
                            str(pdf),
                            "--provider",
                            "fixture",
                            "--schema",
                            "invoice",
                            "--fixture",
                            str(fixture),
                        ]
                    )
                    command += ["--out", str(output)]
                    if style:
                        command += ["--number-style", style]
                    if order:
                        command += ["--date-order", order]
                    result = subprocess.run(
                        command, cwd=scratch, capture_output=True, text=True, check=True
                    )
                    report = json.loads(output.read_text())["report"]
                    assert report["counts"] == {"verified": 2, "needs_review": 2, "unsupported": 0}
                    for field in report["fields"]:
                        assert field["page"] == 1 and field["rects"]
                        if field["path"] in ("total", "issue_date"):
                            assert any(
                                "conflicting evidence" in reason for reason in field["reasons"]
                            )
                    rows.append(
                        {
                            "entryPoint": entry,
                            "numberDefault": style,
                            "dateDefault": order,
                            "amount": amount,
                            "date": date,
                            "exitCode": result.returncode,
                            "counts": report["counts"],
                            "reportSha256": hashlib.sha256(
                                json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
                            ).hexdigest(),
                        }
                    )
report = {
    "driverSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "pdfSha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    "cliCalls": len(rows),
    "rows": rows,
}
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(
    f"{len(rows)} CLI calls: every ambiguous field stays in review; all evidence locations retained"
)
