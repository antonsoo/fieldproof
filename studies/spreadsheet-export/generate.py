"""Generate synthetic exports through the actual upload/extract/review API.

Run from the checkout to inspect: python path/to/generate.py OUTPUT [--xlsx].
The fixture deliberately uses date-, number-, and formula-like *text* values.
"""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from fieldproof.server.app import app

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--xlsx", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
payload = json.loads(Path("examples/fixtures/invoice.json").read_text())
for field, value in {
    "vendor_name": "00034",
    "invoice_number": "=1+1",
    "issue_date": "2026-01-02",
    "po_number": "1E10",
}.items():
    payload["data"][field]["value"] = value
payload["data"]["line_items"][0]["description"]["value"] = "12345678901234567890"
with TestClient(app) as client:
    upload = client.post(
        "/api/documents",
        files={
            "file": ("synthetic.pdf", Path("examples/invoice.pdf").read_bytes(), "application/pdf")
        },
    )
    upload.raise_for_status()
    url = f"/api/documents/{upload.json()['id']}"
    response = client.post(
        f"{url}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={"fixture": ("synthetic.json", json.dumps(payload), "application/json")},
    )
    response.raise_for_status()
    for suffix in ["json", "csv"] + (["xlsx"] if args.xlsx else []):
        export = client.get(f"{url}/export.{suffix}")
        export.raise_for_status()
        (args.output / f"api.{suffix}").write_bytes(export.content)
if args.xlsx:
    from fieldproof.server.spreadsheet import rows_to_xlsx

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    (args.output / "python-cases.xlsx").write_bytes(rows_to_xlsx(cases))
print(f"Synthetic API exports written to {args.output}")
