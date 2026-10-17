"""Replay native font bounds through the actual PDF loader, worker JSON and verifier."""

import argparse
import hashlib
import json
import platform
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

HERE = Path(__file__).resolve().parent


class Amount(BaseModel):
    total: Evidenced[float]


def replay() -> dict:
    started = perf_counter()
    data = Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"]))
    rows = []
    for case in json.loads((HERE / "cases.json").read_text()):
        path = HERE / "fixtures" / f"{case['id']}.pdf"
        raw = path.read_bytes()
        document = load_pdf(raw, label=path.name)
        transported = document_from_dict(json.loads(json.dumps(asdict(document))))
        assert document == transported
        field = verify(data, transported).fields[0].to_dict()
        geometry = [
            {"text": w.text, "bbox": asdict(w.bbox), "start": w.start, "end": w.end}
            for p in document.pages
            for w in p.words
        ]
        rows.append(
            {
                "case": case["id"],
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "hidden": case.get("hidden", False),
                "expected": "needs_review"
                if case.get("hidden") or case.get("review")
                else "verified",
                "field": field,
                "text": document.full_text(),
                "geometry_sha256": hashlib.sha256(
                    json.dumps(geometry, sort_keys=True).encode()
                ).hexdigest(),
                "quoted_words": [
                    asdict(w)
                    for p in document.pages
                    for w in p.words
                    if "$" in w.text or w.text == "7"
                ],
                "wire_identical": True,
            }
        )
    return {
        "python": platform.python_version(),
        "versions": {p: version(p) for p in ("pdfplumber", "pdfminer.six", "pypdfium2", "Pillow")},
        "cases": len(rows),
        "seconds": round(perf_counter() - started, 4),
        "mismatches": sum(r["expected"] != r["field"]["status"] for r in rows),
        "observations": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print({key: value for key, value in result.items() if key != "observations"})
    if args.check:
        assert result["mismatches"] == 0
