"""Actual CLI/native controls and per-page Tesseract transport; no model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "studies/mixed-page-ocr/inputs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # Keep the virtualenv's executable path; resolving its symlink loses site-packages.
    interpreter = str(args.python.absolute())
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if args.source:
        env["PYTHONPATH"] = str(args.source.resolve())
    runtime = json.loads(
        subprocess.check_output(
            [
                interpreter,
                "-c",
                "import platform,hashlib,json;from pathlib import Path;"
                "import fieldproof.cli as cli;from fieldproof.document import ocr,model;"
                "print(json.dumps({'python':platform.python_version(),"
                "'sourceSha256':{m.__name__:hashlib.sha256("
                "Path(m.__file__).read_bytes()).hexdigest() "
                "for m in [cli,ocr,model]}}))",
            ],
            env=env,
            text=True,
        )
    )
    records = []
    for name in ["native", "mixed", "scan-first", "blank-middle", "all-scanned"]:
        for enabled in [False] if args.baseline else [False, True]:
            for operation in ["extract", "verify"]:
                source = INPUTS / f"{name}.pdf"
                fixture = INPUTS / f"{name}.json"
                destination = (
                    args.out / f"{name}-{'page-ocr' if enabled else 'default'}-{operation}.json"
                )
                parameters = (
                    ["extract", str(source), "--fixture", str(fixture)]
                    if operation == "extract"
                    else ["verify", str(fixture), str(source)]
                )
                command = [
                    interpreter,
                    "-m",
                    "fieldproof.cli",
                    *parameters,
                    "--out",
                    str(destination.resolve()),
                ]
                if enabled:
                    command.append("--ocr-missing-pages")
                result = subprocess.run(
                    command, env=env, capture_output=True, text=True, timeout=60, check=False
                )
                assert result.returncode == 0, (name, enabled, operation, result.stderr)
                payload = json.loads(destination.read_text())
                report = payload["report"]
                expected = 6 if name == "native" or (enabled and name != "all-scanned") else 3
                assert report["counts"] == {
                    "verified": expected,
                    "needs_review": 0,
                    "unsupported": 6 - expected,
                }
                provenance = report.get("ocr")
                expected_pages = {"mixed": [2], "scan-first": [1], "blank-middle": [2, 3]}
                if enabled and name in expected_pages:
                    assert provenance["processed_pages"] == expected_pages[name]
                    assert provenance["empty_pages"] == ([2] if name == "blank-middle" else [])
                    assert "OCR:" in result.stderr
                elif name == "all-scanned":
                    assert provenance and "processed_pages" not in provenance
                else:
                    assert provenance is None and "OCR:" not in result.stderr

                def portable(text: str) -> str:
                    return text.replace(str(ROOT), "<repo>").replace(
                        str(args.out.resolve()), "<output>"
                    )

                records.append(
                    {
                        "case": name,
                        "pageOcr": enabled,
                        "operation": operation,
                        "exit": result.returncode,
                        "stdout": portable(result.stdout),
                        "stderr": portable(result.stderr),
                        "counts": report["counts"],
                        "ocr": provenance,
                        "output": destination.name,
                        "outputSha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    }
                )

    if not args.baseline:
        for missing in ["engine", "language-data"]:
            broken = dict(env)
            broken["PATH" if missing == "engine" else "TESSDATA_PREFIX"] = str(args.out.resolve())
            for operation in ["extract", "verify"]:
                name = f"missing-{missing}-{operation}"
                destination = args.out / f"{name}.json"
                destination.write_text("previous result\n")
                source, fixture = INPUTS / "mixed.pdf", INPUTS / "mixed.json"
                parameters = (
                    ["extract", str(source), "--fixture", str(fixture)]
                    if operation == "extract"
                    else ["verify", str(fixture), str(source)]
                )
                result = subprocess.run(
                    [
                        interpreter,
                        "-m",
                        "fieldproof.cli",
                        *parameters,
                        "--ocr-missing-pages",
                        "--out",
                        str(destination.resolve()),
                    ],
                    env=broken,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                assert result.returncode == 1 and "Traceback" not in result.stderr
                assert destination.read_text() == "previous result\n"
                portable = result.stderr.replace(str(ROOT), "<repo>").replace(
                    str(args.out.resolve()), "<output>"
                )
                records.append(
                    {
                        "case": name,
                        "exit": result.returncode,
                        "stderr": portable,
                        "previousOutputPreserved": True,
                    }
                )
                destination.unlink()

    result = {
        "runtime": runtime,
        "baseline": args.baseline,
        "population": "Synthetic header/totals PDFs, actual subprocess CLI and local Tesseract; "
        "no scanner or live model",
        "commands": len(records),
        "records": records,
    }
    (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"{len(records)} actual CLI workflows passed; "
        f"{'baseline defaults' if args.baseline else 'explicit mixed-page OCR checked'}"
    )


if __name__ == "__main__":
    main()
