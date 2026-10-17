"""Current example PDFs: preserve their source, text, geometry and reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import BUILTIN_SCHEMAS
from fieldproof.verify import verify

ROOT = Path(__file__).resolve().parents[2]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = []
    for source in sorted((ROOT / "examples").glob("*.pdf")):
        fixture = json.loads((ROOT / "examples/fixtures" / f"{source.stem}.json").read_text())
        document = load_pdf(source.read_bytes(), label=source.name)
        schemas = {**BUILTIN_SCHEMAS, **{s.__name__: s for s in BUILTIN_SCHEMAS.values()}}
        data = schemas[fixture["schema"]].model_validate(fixture["data"])
        report = verify(data, document).to_dict()
        frames = [{"text": p.text, "width": p.width, "height": p.height,
                   "words": [[w.text, w.start, w.end, w.bbox.to_dict()] for w in p.words]}
                  for p in document.pages]
        rows.append({"pdf": source.name, "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                     "geometrySha256": digest(frames), "reportSha256": digest(report),
                     "counts": report["counts"]})
    result = {"documents": len(rows), "rows": rows}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Recorded {len(rows)} example sources, text/geometry and complete reports")


if __name__ == "__main__":
    main()
