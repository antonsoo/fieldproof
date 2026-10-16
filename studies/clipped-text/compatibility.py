"""Compare existing example text, geometry and verification without new word flags."""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import resolve_schema
from fieldproof.verify import verify

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    observations = []
    started = perf_counter()
    for path in sorted(EXAMPLES.glob("*.pdf")):
        document = load_pdf(path)
        raw = json.loads((EXAMPLES / "fixtures" / f"{path.stem}.json").read_text())
        schema = resolve_schema(raw["schema"].lower())
        report = verify(schema.model_validate(raw["data"]), document).to_dict()
        geometry = [{
            "text": page.text, "width": page.width, "height": page.height,
            "words": [{"text": word.text, "bbox": word.bbox.to_dict(),
                       "start": word.start, "end": word.end} for word in page.words],
        } for page in document.pages]
        observations.append({"pdf": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "text_and_geometry_sha256": digest(geometry),
                             "report_sha256": digest(report), "counts": report["counts"]})
    result = {"documents": len(observations), "seconds": round(perf_counter() - started, 4),
              "observations": observations}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({key: value for key, value in result.items() if key != "observations"})


if __name__ == "__main__":
    main()
