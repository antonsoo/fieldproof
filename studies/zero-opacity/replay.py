"""Replay the committed PDFs through the invoking Fieldproof installation."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

ROOT = Path(__file__).resolve().parent


class Claim(BaseModel):
    total: Evidenced[float]
    visible: Evidenced[float]


def replay():
    observations = []
    started = perf_counter()
    for case in json.loads((ROOT / "cases.json").read_text()):
        content = (ROOT / "fixtures" / f"{case['id']}.pdf").read_bytes()
        document = document_from_dict(json.loads(json.dumps(asdict(load_pdf(content)))))
        data = Claim(total=Evidenced(value=900, evidence=["Authorized total: $900.00"]),
                     visible=Evidenced(value=90, evidence=["Visible total: $90.00"]))
        for result in verify(data, document).fields:
            expected = "needs_review" if case["hidden"] and result.path == "total" else "verified"
            observations.append({"case": case["id"], "sha256": hashlib.sha256(content).hexdigest(),
                                 "expected": expected, "field": result.to_dict()})
    return {
        "synthetic": True, "pdfs": len(observations) // 2, "claims": len(observations),
        "mismatches": sum(o["expected"] != o["field"]["status"] for o in observations),
        "unexpected_verified": sum(o["expected"] == "needs_review" and o["field"]["status"] == "verified"
                                   for o in observations),
        "seconds": round(perf_counter() - started, 4), "observations": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({key: value for key, value in result.items() if key != "observations"})
    if args.check:
        assert result["mismatches"] == 0
