"""Replay fraction claims through native PDF loading, verification and the CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.absolute()))
    from pydantic import BaseModel

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.document.model import Document
    from fieldproof.extract.fixture_provider import FixtureExtractor
    from fieldproof.schemas import Evidenced, Invoice
    from fieldproof.verify import verify
    from fieldproof.verify.value_checks import parse_all_numbers

    class Quantity(BaseModel):
        quantity: Evidenced[float]

    Quantity.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    package = Path(fieldproof.__file__).absolute().parent
    document = load_pdf(HERE / "fixtures/fractions.pdf")
    cases = json.loads((HERE / "fixtures/cases.json").read_text())
    rows = []
    for case, page in zip(cases, document.pages, strict=True):
        assert page.text == case["text"]
        isolated = Document("isolated authored fraction control", [page])
        for value in (1, 2):
            for quote in (case["text"], f"1{case['gap']}{case['slash']}{case['gap']}2", str(value)):
                result = verify(
                    Quantity(quantity=Evidenced(value=value, evidence=[quote])), isolated
                )
                field = result.fields[0]
                rows.append(
                    {
                        "page": page.number,
                        "text": case["text"],
                        "value": value,
                        "quote": quote,
                        "status": field.status.value,
                        "matched_text": field.matched_text,
                        "reasons": field.reasons,
                        "rects": field.rects,
                    }
                )
    review_doc = load_pdf(HERE / "fixtures/review.pdf")
    extraction = FixtureExtractor(fixture_path=HERE / "fixtures/review.json").extract(
        review_doc, Invoice
    )
    review = verify(extraction.data, review_doc).to_dict()
    quantity = next(f for f in review["fields"] if f["path"] == "line_items[0].quantity")
    args.artifacts.mkdir(parents=True, exist_ok=True)
    commands = []
    extracted = args.artifacts / "extracted.json"
    repeated = args.artifacts / "reverified.json"
    env = dict(os.environ)
    if args.src:
        env["PYTHONPATH"] = str(args.src.absolute())
    for command in [
        [
            "extract",
            str(HERE / "fixtures/review.pdf"),
            "--schema",
            "invoice",
            "--provider",
            "fixture",
            "--fixture",
            str(HERE / "fixtures/review.json"),
            "--out",
            str(extracted),
        ],
        ["verify", str(extracted), str(HERE / "fixtures/review.pdf"), "--out", str(repeated)],
    ]:
        run = subprocess.run(
            [sys.executable, "-m", "fieldproof.cli", *command],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stderr
        commands.append(
            {"command": command, "exit": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
        )
    a, b = [json.loads(p.read_text()) for p in (extracted, repeated)]
    assert a["data"] == b["data"] == extraction.to_dict()["data"]
    assert a["report"] == b["report"] == review
    lexical = {
        text: parse_all_numbers(text)
        for text in [
            "1/2",
            "1⁄2",
            "1∕2",
            "1 / 2",
            "1/ 2",
            "1 /2",
            "½",
            "1½",
            "(1 ⁄ 2)",
            "2026 / 10 / 17",
            "Qty 3; cut length 1⁄2 m; unit price $19.95",
        ]
    }
    false_approvals = sum(r["status"] == "verified" for r in rows)
    receipt = {
        "python": sys.version,
        "source": str(package),
        "synthetic": True,
        "scope": "Authored visible native-text PDFs; no model/OCR/production prevalence claim",
        "source_parser_sha256": hashlib.sha256(
            (package / "ground/values.py").read_bytes()
        ).hexdigest(),
        "files": {
            p.name: {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted((HERE / "fixtures").iterdir())
            if p.is_file()
        },
        "claims": rows,
        "false_fragment_approvals": false_approvals,
        "verdicts": dict(Counter(r["status"] for r in rows)),
        "invoice_quantity": quantity,
        "invoice_report": review,
        "lexical_controls": lexical,
        "cli": commands,
        "original_claims_preserved": True,
        "cli_reverification_matches_library": True,
    }
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    if not args.observe_only:
        assert false_approvals == 0
        assert quantity["status"] == "needs_review"
        assert all(f["status"] == "verified" for f in review["fields"] if f is not quantity)
        assert lexical["Qty 3; cut length 1⁄2 m; unit price $19.95"] == [3, 19.95]
    print(
        json.dumps(
            {
                "claims": len(rows),
                "false_approvals": false_approvals,
                "invoice_quantity": quantity["status"],
                "cli": 2,
            }
        )
    )


if __name__ == "__main__":
    main()
