"""Replay authored native-text overlap cases through the actual loader and verifier."""

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
    observations = []
    for case in json.loads((HERE / "cases.json").read_text()):
        source = HERE / "fixtures" / f"{case['id']}.pdf"
        document = load_pdf(source.read_bytes(), label=source.name)
        wire = json.loads(json.dumps(asdict(document)))
        transported = document_from_dict(wire)
        result = verify(data, transported).fields[0].to_dict()
        geometry = [
            {"text": w.text, "bbox": asdict(w.bbox), "start": w.start, "end": w.end}
            for p in document.pages for w in p.words
        ]
        observations.append({
            "case": case["id"],
            "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "expected": "needs_review" if case["review"] else "verified",
            "field": result,
            "geometrySha256": hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest(),
            "text": document.full_text(),
            "words": [asdict(w) for p in document.pages for w in p.words],
            "wireIdentical": document == transported,
        })
    return {
        "python": platform.python_version(),
        "versions": {p: version(p) for p in ("pdfplumber", "pdfminer.six", "pypdfium2", "Pillow")},
        "cases": len(observations),
        "mismatches": sum(row["expected"] != row["field"]["status"] for row in observations),
        "seconds": round(perf_counter() - started, 4),
        "observations": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({key: value for key, value in result.items() if key != "observations"})
    if args.check:
        assert result["mismatches"] == 0
