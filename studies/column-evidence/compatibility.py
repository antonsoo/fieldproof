"""Existing fixture verdicts and the cost of complete, constructed multi-page tables."""

import argparse
import hashlib
import json
import statistics
import sys
import time
from io import BytesIO
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--src", required=True, type=Path)
parser.add_argument("--examples", required=True, type=Path)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
# Select the pinned source before importing the package under observation.
sys.path.insert(0, str(args.src.resolve()))
from reportlab.pdfgen.canvas import Canvas  # noqa: E402

from fieldproof.document.loader import load_pdf  # noqa: E402
from fieldproof.schemas import Invoice, resolve_schema  # noqa: E402
from fieldproof.verify import verify  # noqa: E402

records = []
for fixture in sorted((args.examples / "fixtures").glob("*.json")):
    pdf = args.examples / f"{fixture.stem}.pdf"
    if fixture.stem == "column-evidence" or not pdf.exists():
        continue
    raw = json.loads(fixture.read_text())
    schema = resolve_schema(raw["schema"])
    assert schema is not None
    report = verify(schema.model_validate(raw["data"]), load_pdf(pdf)).to_dict()
    columns = report.pop("column_checks", [])
    records.append(
        {
            "fixture": fixture.name,
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "input_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "report_without_columns_sha256": hashlib.sha256(
                json.dumps(report, sort_keys=True).encode()
            ).hexdigest(),
            "counts": report["counts"],
            "column_statuses": [c["status"] for c in columns],
        }
    )


def e(value, quote):
    return {"value": value, "evidence": [quote]}


cost = []
for count in (10, 100, 300):
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
    items = []
    for i in range(count):
        if i % 30 == 0:
            if i:
                canvas.showPage()
            for x, text in [
                (40, "Description"),
                (310, "Qty"),
                (400, "Unit price"),
                (510, "Amount"),
            ]:
                canvas.drawString(x, 750, text)
        label = "Service " + chr(65 + i // 26) + chr(65 + i % 26)
        qty, price = 2 + i % 3, 10 + i + 0.25
        text = [label, str(qty), f"{price:.2f}", f"{qty * price:.2f}"]
        for x, token in zip((40, 310, 400, 510), text, strict=True):
            canvas.drawString(x, 730 - 22 * (i % 30), token)
        whole = " ".join(text)
        items.append(
            {
                "description": e(label, label),
                "quantity": e(qty, whole),
                "unit_price": e(price, whole),
                "amount": e(qty * price, whole),
            }
        )
    canvas.save()
    data = Invoice.model_validate(
        {
            "vendor_name": e("Example", "Example"),
            "invoice_number": e("COL", "COL"),
            "issue_date": e("2026-10-12", "2026-10-12"),
            "line_items": items,
            "total": e(0, "0"),
        }
    )
    document = load_pdf(stream.getvalue())
    times = []
    for _ in range(5):
        start = time.perf_counter()
        report = verify(data, document).to_dict()
        times.append((time.perf_counter() - start) * 1000)
    columns = report.pop("column_checks", [])
    assert all(
        f["status"] == "verified" for f in report["fields"] if f["path"].startswith("line_items")
    )
    assert all(c["status"] == "aligned" for c in columns)
    cost.append(
        {
            "rows": count,
            "pages": document.page_count,
            "times_ms": times,
            "median_ms": statistics.median(times),
            "column_checks": len(columns),
            "pdf_sha256": hashlib.sha256(stream.getvalue()).hexdigest(),
            "report_without_columns_sha256": hashlib.sha256(
                json.dumps(report, sort_keys=True).encode()
            ).hexdigest(),
        }
    )
result = {
    "scope": (
        "Existing fixtures and constructed table cost; 5 verifications each, "
        "parsed PDF reused, fresh verification caches."
    ),
    "python": sys.version.split()[0],
    "fixtures": records,
    "cost": cost,
}
args.out.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "fixtures": len(records),
            "cost": [{k: c[k] for k in ("rows", "median_ms", "column_checks")} for c in cost],
        }
    )
)
