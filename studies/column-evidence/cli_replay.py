"""Run documented extraction and re-verification through an installed console entry point."""

import argparse
import json
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--repo", required=True, type=Path)
p.add_argument("env", type=Path)
p.add_argument("out", type=Path)
a = p.parse_args()
r = a.repo.resolve()
a.env = a.env.absolute()
a.out.mkdir(parents=True, exist_ok=True)
for f in sorted((r / "examples/fixtures").glob("*.json")):
    pdf = r / "examples" / f"{f.stem}.pdf"
    if not pdf.exists():
        continue
    raw = json.loads(f.read_text())
    schema = {"Invoice": "invoice", "Receipt": "receipt", "ContractKeyTerms": "contract"}.get(
        raw["schema"], raw["schema"]
    )
    out = a.out / f"{f.stem}.json"
    verified = a.out / f"{f.stem}.verified.json"
    for mode, args in [
        (
            "extract",
            [
                "extract",
                str(pdf),
                "--schema",
                schema,
                "--provider",
                "fixture",
                "--fixture",
                str(f),
                "--out",
                str(out),
            ],
        ),
        ("verify", ["verify", str(out), str(pdf), "--out", str(verified)]),
    ]:
        proc = subprocess.run(
            [str(a.env / "bin/fieldproof"), *args], text=True, capture_output=True
        )
        (a.out / f"{f.stem}.{mode}.txt").write_text(proc.stdout + proc.stderr)
        assert proc.returncode == 0, (f.name, mode, proc.stderr)
    before = json.loads(out.read_text())
    after = json.loads(verified.read_text())
    assert before["report"] == after["report"], f.name
print("10 installed CLI extract/verify pairs passed")
