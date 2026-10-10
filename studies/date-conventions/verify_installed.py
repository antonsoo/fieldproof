"""Replay PDF evidence and real CLI invocations using an installed wheel."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

import fieldproof
from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import verify


class Claim(BaseModel):
    issue_date: Evidenced[str]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    package = Path(fieldproof.__file__).resolve()
    assert package.is_relative_to(Path(sys.prefix).resolve())
    assert not package.is_relative_to(root / "src"), package
    cases = json.loads(args.cases.read_text())["results"]
    documents = {}
    for case in cases:
        if case["case"] not in documents:
            raw = (args.cases.parent / f"{case['case']}.pdf").read_bytes()
            assert hashlib.sha256(raw).hexdigest() == case["pdf_sha256"]
            documents[case["case"]] = load_pdf(raw)
        claim = Claim(issue_date=Evidenced(value=case["value"], evidence=[case["quote"]], page=1))
        result = verify(claim, documents[case["case"]], default_date_order=case["default"]).fields[
            0
        ]
        assert result.to_dict() == case["result"], case
        assert result.status.value == case["expected"], case
    cli = Path(sys.executable).parent / "fieldproof"
    cli_results = []
    original = json.loads((root / "examples/fixtures/date-convention.json").read_text())
    with TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        for default in (None, "mdy", "dmy"):
            for value in ("2026-03-04", "2026-04-03"):
                original["data"]["issue_date"]["value"] = value
                fixture, report = scratch / "fixture.json", scratch / "report.json"
                fixture.write_text(json.dumps(original))
                command = [
                    str(cli),
                    "extract",
                    str(root / "examples/date-convention.pdf"),
                    "--schema",
                    "invoice",
                    "--fixture",
                    str(fixture),
                    "--out",
                    str(report),
                ]
                if default:
                    command += ["--date-order", default]
                completed = subprocess.run(
                    command, cwd=scratch, capture_output=True, text=True, check=True
                )
                output = json.loads(report.read_text())
                date = next(f for f in output["report"]["fields"] if f["path"] == "issue_date")
                expected = (
                    "verified"
                    if (default, value) in (("mdy", "2026-03-04"), ("dmy", "2026-04-03"))
                    else "needs_review"
                )
                assert date["status"] == expected, completed.stdout
                assert date["page"] == 1 and date["rects"]
                assert date["matched_text"] == "Issue Date: 03/04/2026"
                cli_results.append(
                    {
                        "default": default,
                        "value": value,
                        "field": date,
                        "counts": output["report"]["counts"],
                    }
                )
    result = {
        "python": platform.python_version(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "fieldproof",
                "pydantic",
                "pdfplumber",
                "pypdfium2",
                "rapidfuzz",
                "fastapi",
            )
        },
        "imported_installed_package": True,
        "pdf_checks": len(cases),
        "pdf_result_dicts_match_source": True,
        "cli_checks": cli_results,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Installed wheel: {len(cases)} PDF checks and {len(cli_results)} CLI scenarios passed")


if __name__ == "__main__":
    main()
