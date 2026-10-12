"""Run real CLI commands from a checkout or isolated installed wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expect", choices=["before", "after"], required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    probe_env = dict(os.environ)
    probe_env.pop("PYTHONPATH", None)
    if args.source:
        probe_env["PYTHONPATH"] = str(args.source.resolve())
    probe = subprocess.run(
        [
            args.python,
            "-c",
            "import json,platform,pytesseract,fieldproof; "
            "from fieldproof.document.ocr import is_available; "
            "print(json.dumps({'python':platform.python_version(), "
            "'package':fieldproof.__version__, "
            "'pytesseract':pytesseract.__version__, 'ocrAvailable':is_available(), "
            "'engine':str(pytesseract.get_tesseract_version())}))",
        ],
        env=probe_env,
        capture_output=True,
        text=True,
        check=True,
    )
    runtime = json.loads(probe.stdout)
    assert runtime["ocrAvailable"]
    manifest = json.loads((STUDY / "inputs.json").read_text())
    for item in manifest:
        assert (
            hashlib.sha256((STUDY / "inputs" / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    cases = []
    for name in ("invoice", "receipt", "contract"):
        cases.extend(
            [
                (f"native-{name}", ROOT / f"examples/{name}.pdf", name, "normal", True),
                (
                    f"scanned-{name}",
                    STUDY / f"inputs/scanned-{name}.pdf",
                    name,
                    "normal",
                    args.expect == "after",
                ),
            ]
        )
    scan = STUDY / "inputs/scanned-invoice.pdf"
    cases.extend(
        [
            (
                "blank-first-page",
                STUDY / "inputs/blank-then-invoice.pdf",
                "invoice",
                "normal",
                args.expect == "after",
            ),
            ("blank", STUDY / "inputs/blank.pdf", "invoice", "normal", False),
            ("missing-engine", scan, "invoice", "no-engine", False),
            ("missing-language-data", scan, "invoice", "no-data", False),
            ("native-without-engine", ROOT / "examples/invoice.pdf", "invoice", "no-engine", True),
        ]
    )
    records = []
    with tempfile.TemporaryDirectory(prefix="ocr-replay-") as scratch:
        for name, document, schema, environment, success in cases:
            fixture = ROOT / f"examples/fixtures/{schema}.json"
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            if args.source:
                env["PYTHONPATH"] = str(args.source.resolve())
            if environment == "no-engine":
                env["PATH"] = scratch
            elif environment == "no-data":
                env["TESSDATA_PREFIX"] = scratch
            commands = [
                (
                    "extract",
                    ["extract", str(document), "--schema", schema, "--fixture", str(fixture)],
                ),
                ("verify", ["verify", str(fixture), str(document)]),
            ]
            for command, parameters in commands:
                destination = args.out.resolve() / f"{name}-{command}.json"
                # An existing output must survive any recognition failure.
                destination.write_text("previous result\n")
                run = subprocess.run(
                    [args.python, "-m", "fieldproof.cli", *parameters, "--out", str(destination)],
                    env=env,
                    cwd=scratch,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                assert run.returncode == (0 if success else 1), (name, command, run.stderr)
                assert "Traceback" not in run.stderr
                result = json.loads(destination.read_text()) if success else None
                if not success:
                    assert destination.read_text() == "previous result\n"
                    destination.unlink()
                else:
                    is_scan = name.startswith("scanned-") or name == "blank-first-page"
                    assert ("ocr" in result["report"]) == is_scan
                    if is_scan:
                        assert "OCR:" in run.stderr
                        assert result["report"]["ocr"]["engine"] == "tesseract"
                        assert result["report"]["counts"]["verified"] > 0
                    if name == "blank-first-page":
                        assert result["report"]["ocr"]["empty_pages"] == [1]
                        assert all(f["page"] in (None, 2) for f in result["report"]["fields"])

                # Retain diagnostics without this machine's absolute paths.
                def portable(text: str) -> str:
                    return (
                        text.replace(str(ROOT), "<repo>")
                        .replace(str(args.out.resolve()), "<output>")
                        .replace(scratch, "<empty-runtime>")
                    )

                records.append(
                    {
                        "case": name,
                        "command": command,
                        "exitCode": run.returncode,
                        "stdout": portable(run.stdout),
                        "stderr": portable(run.stderr),
                        "counts": result["report"]["counts"] if result else None,
                        "outputPreservedOnFailure": None if success else True,
                        "outputSha256": hashlib.sha256(destination.read_bytes()).hexdigest()
                        if success
                        else None,
                    }
                )
    (args.out / "replay.json").write_text(
        json.dumps({"expected": args.expect, "runtime": runtime, "commands": records}, indent=2)
        + "\n"
    )
    print(
        f"{len(records)} CLI commands passed ({args.expect}); "
        "failed commands preserved prior outputs"
    )


if __name__ == "__main__":
    main()
