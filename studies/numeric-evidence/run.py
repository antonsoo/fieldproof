"""Exercise numeric evidence through real, deterministic PDFs, without a model.

    uv run --locked python -I studies/numeric-evidence/run.py --src src --out /tmp/numeric

`--observe-only` records the old checkout's incorrect verdicts without making that
baseline measurement fail. Omit it when checking the expected behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))

    import reportlab
    from pydantic import BaseModel
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)

    class Amount(BaseModel):
        total: Evidenced[float]

    class IntegerAmount(BaseModel):
        total: Evidenced[int]

    # Postponed annotations refer to imports local to main().
    Amount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    IntegerAmount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    font = Path(reportlab.__file__).parent / "fonts/Vera.ttf"
    pdfmetrics.registerFont(TTFont("NumericEvidence", str(font)))
    cases_path = HERE / "cases.json"
    cases = json.loads(cases_path.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        canvas.setFont("NumericEvidence", 12)
        canvas.drawString(36, 700, case["source"])
        canvas.save()
        pdf = stream.getvalue()
        (args.out / f"{case['id']}.pdf").write_bytes(pdf)
        document = load_pdf(pdf)
        assert document.pages[0].text == case["source"], case["id"]
        schema = IntegerAmount if case.get("type") == "int" else Amount
        data = schema.model_validate(
            {"total": {"value": case["value"], "evidence": [case["quote"]], "page": 1}}
        )
        report = verify(data, document)
        (result,) = report.fields
        rows.append(
            {
                **case,
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "pdf_text": document.pages[0].text,
                "result": result.to_dict(),
                "agrees": result.status.value == case["expect"],
            }
        )
    sources = {
        str(path.relative_to(src)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((src / "fieldproof").rglob("*.py"))
    }
    counts = Counter(row["result"]["status"] for row in rows)
    mismatches = [row["id"] for row in rows if not row["agrees"]]
    output = {
        "scope": "Hand-specified synthetic cases through the real PDF loader and verifier; no LLM.",
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("reportlab", "pdfplumber", "pydantic")},
        "font_sha256": hashlib.sha256(font.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "source_sha256": sources,
        "counts": dict(counts),
        "mismatches": mismatches,
        "cases": rows,
    }
    (args.out / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(rows)} PDFs: {dict(counts)}; {len(mismatches)} unexpected verdicts")
    for row in rows:
        if not row["agrees"]:
            print(f"  {row['id']}: {row['result']['status']} (expected {row['expect']})")
    if mismatches and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
