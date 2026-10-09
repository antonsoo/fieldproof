"""Measure equal work in separate processes for the old and current source."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))
    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas.invoice import Invoice
    from fieldproof.verify.engine import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)
    examples = Path(__file__).resolve().parents[2] / "examples"
    measurements = []
    for name in ["invoice", "line-arithmetic"]:
        pdf = examples / f"{name}.pdf"
        raw = json.loads((examples / "fixtures" / f"{name}.json").read_text())
        data = Invoice.model_validate(raw.get("data", raw))
        doc = load_pdf(pdf)
        report = verify(data, doc)
        for load_each_time in [False, True]:
            durations = []
            for _ in range(9):
                start = time.perf_counter()
                for _ in range(10):
                    verify(data, load_pdf(pdf) if load_each_time else doc)
                durations.append((time.perf_counter() - start) * 100)
            measurements.append(
                {
                    "document": pdf.name,
                    "pdfSha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    "operation": "load + verify" if load_each_time else "verify parsed PDF",
                    "millisecondsPerDocument": durations,
                    "medianMilliseconds": statistics.median(durations),
                    "counts": report.counts,
                    "reportJsonBytes": len(json.dumps(report.to_dict()).encode()),
                }
            )
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementationSha256": hashlib.sha256(
            (src / "fieldproof/verify/cross_field.py").read_bytes()
        ).hexdigest(),
        "method": "9 batches of 10 documents per operation, after one warm-up; no model calls",
        "measurements": measurements,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            [{k: v for k, v in m.items() if k != "millisecondsPerDocument"} for m in measurements]
        )
    )


if __name__ == "__main__":
    main()
