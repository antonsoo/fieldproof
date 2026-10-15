"""Replay authored controls with the Python installation invoking this script."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, create_model

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import RowEvidenceRule, verify

ROOT = Path(__file__).resolve().parent


class Item(BaseModel):
    description: Evidenced[str]
    quantity: Evidenced[float]


class Rows(BaseModel):
    items: list[Item]


def replay() -> dict:
    observations = []
    started = perf_counter()
    for case in json.loads((ROOT / "cases.json").read_text()):
        content = (ROOT / "fixtures" / f"{case['id']}.pdf").read_bytes()
        document = load_pdf(content)
        # Match the subprocess boundary used by the installed review server.
        document = document_from_dict(json.loads(json.dumps(asdict(document))))
        for check in case["checks"]:
            if case["id"].startswith("row-anchor-"):
                data = Rows(items=[Item(
                    description=Evidenced(value="Delivery", evidence=["Delivery"]),
                    quantity=Evidenced(value=2, evidence=["2"]),
                )])
                report = verify(data, document, row_rules=[
                    RowEvidenceRule("items", "description", ("quantity",))
                ])
            else:
                path, value = check["path"], check["value"]
                model = create_model("Claim", **{path: (Evidenced[type(value)], ...)})
                data = model(**{path: {"value": value, "evidence": [check["quote"]]}})
                report = verify(data, document)
            result = next(field for field in report.fields if field.path == check["path"])
            observations.append({
                "case": case["id"], "sha256": hashlib.sha256(content).hexdigest(),
                "expected": check["expected"], "field": result.to_dict(),
            })
    return {
        "python_module": "fieldproof", "synthetic": True,
        "pdfs": len({o["case"] for o in observations}), "claims": len(observations),
        "mismatches": sum(o["expected"] != o["field"]["status"] for o in observations),
        "unexpected_verified": sum(
            o["expected"] == "needs_review" and o["field"]["status"] == "verified"
            for o in observations
        ),
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
