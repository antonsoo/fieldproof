"""Replay actual PDF layouts against any source tree or installed package.

uv run --locked --extra dev python -I studies/row-locality/run.py --src src --out DIR
Add --observe-only to record the old behavior without asserting corrected results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))

    from pydantic import BaseModel
    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)

    class Row(BaseModel):
        description: Evidenced[str]
        quantity: Evidenced[float]

    Row.model_rebuild(_types_namespace={"Evidenced": Evidenced})

    class Form(BaseModel):
        items: list[Row]

    Form.model_rebuild(_types_namespace={"Row": Row})
    args.out.mkdir(parents=True, exist_ok=True)
    observations = []
    started = perf_counter()
    for case in CASES:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        for page in case.pages:
            canvas.setFont("Helvetica", 12)
            for x, y, text in page:
                canvas.drawString(x, y, text)
            canvas.showPage()
        canvas.save()
        pdf = stream.getvalue()
        (args.out / f"{case.name}.pdf").write_bytes(pdf)
        document = load_pdf(pdf)
        data = Form(
            items=[
                Row(
                    description=Evidenced(value=case.description, evidence=[case.quote]),
                    quantity=Evidenced(value=1, evidence=["1"]),
                )
            ]
        )
        report = verify(data, document, text_edit_tolerance=case.text_edit_tolerance)
        result = report.fields[1]
        agrees = result.status == case.expected
        if case.expected_xy is not None:
            x, y = case.expected_xy
            agrees = (
                agrees
                and result.page == 1
                and any(
                    abs(rect["x0"] - x) < 0.1 and rect["top"] < 792 - y < rect["bottom"]
                    for rect in result.rects
                )
            )
        elif result.status == "needs_review":
            agrees = agrees and result.page is None and result.rects == []
        observations.append(
            {
                **asdict(case),
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "report": report.to_dict(),
                "agrees": agrees,
            }
        )
    summary = {
        "scope": "Synthetic PDF layouts through the real loader and verifier; no model calls.",
        "python": platform.python_version(),
        "seconds": perf_counter() - started,
        "source_sha256": {
            str(path.relative_to(src)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((src / "fieldproof").rglob("*.py"))
        },
        "cases": len(observations),
        "disagreements": [row["name"] for row in observations if not row["agrees"]],
        "observations": observations,
    }
    (args.out / "observations.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("cases", "disagreements", "seconds")}))
    if not args.observe_only:
        assert not summary["disagreements"]


if __name__ == "__main__":
    main()
