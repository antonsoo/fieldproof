"""Capture the actual Python XLSX writer and upload/extract/review/export API.

Supply an explicit fixture root when running with an installed wheel outside
the checkout. The optional observation flag retains baseline disagreements.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from fastapi.testclient import TestClient

import fieldproof
from fieldproof.server.app import app
from fieldproof.server.spreadsheet import COLUMNS, rows_to_xlsx

HERE = Path(__file__).resolve().parent
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def value_of(case):
    if "integer" in case:
        return int(case["integer"])
    if "powerPlusOne" in case:
        return 10 ** case["powerPlusOne"] + 1
    return case["value"]


def cells(payload):
    with ZipFile(io.BytesIO(payload)) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(xml)
        assert not root.findall(".//s:f", NS)
        assert not root.findall(".//s:hyperlink", NS)
        assert b"External" not in archive.read("xl/_rels/workbook.xml.rels")
    return [[{"type": cell.get("t", "blank"),
              "text": cell.findtext("s:is/s:t", None, NS),
              "number": cell.findtext("s:v", None, NS)} for cell in row]
            for row in root.findall("s:sheetData/s:row", NS)]


def agrees(cell, case, value):
    expected = case["cell"]
    return cell["type"] == expected and (
        cell["text"] == str(value) if expected == "inlineStr"
        else cell["number"] == str(int(value)) if expected == "b"
        else cell["number"] is None if expected == "blank"
        else float(cell["number"]) == value
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--fixture-root", type=Path, default=HERE.parents[1])
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fixtures = args.fixture_root.resolve()
    cases = json.loads((HERE / "cases.json").read_text())
    records, combined = [], []
    for case in cases:
        value = value_of(case)
        row = dict(zip(COLUMNS, [case["id"], value, value, "extracted", "verified", "approved", 1], strict=True))
        try:
            payload = rows_to_xlsx([row])
            parsed = cells(payload)[1]
            passed = agrees(parsed[1], case, value) and agrees(parsed[2], case, value)
            name = f"writer-{case['id']}.xlsx"
            (args.out / name).write_bytes(payload)
            records.append({"case": case["id"], "kind": "writer", "agrees": passed,
                            "sourceSpelling": str(value), "cells": parsed,
                            "file": name, "sha256": hashlib.sha256(payload).hexdigest()})
            combined.append(row)
        except (ValueError, OverflowError) as error:
            records.append({"case": case["id"], "kind": "writer", "agrees": False,
                            "sourceSpelling": str(value), "error": type(error).__name__, "message": str(error)})
    (args.out / "writer-all.xlsx").write_bytes(rows_to_xlsx(combined))

    with TestClient(app) as client:
        upload = client.post("/api/documents", files={"file": ("synthetic.pdf", (fixtures / "examples/invoice.pdf").read_bytes(), "application/pdf")})
        upload.raise_for_status()
        url = f"/api/documents/{upload.json()['id']}"
        fixture = (fixtures / "examples/fixtures/invoice.json").read_bytes()
        extraction = client.post(f"{url}/extract", data={"schema": "invoice", "provider": "fixture"},
                                 files={"fixture": ("synthetic.json", fixture, "application/json")})
        extraction.raise_for_status()
        original_report = client.get(f"{url}/report").json()["report"]
        for case in cases:
            value = value_of(case)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or "powerPlusOne" in case:
                continue
            review = client.post(f"{url}/review", json={"path": "total", "action": "edit", "value": value})
            review.raise_for_status()
            assert review.json()["edited_value"] == value
            for scope in ("reviewed", "all"):
                report = client.get(f"{url}/export.json?scope={scope}")
                report.raise_for_status()
                rows = report.json()
                index = next(i for i, row in enumerate(rows) if row["field"] == "total")
                row = rows[index]
                assert row["value"] == value and row["value_source"] == "correction" and row["review_status"] == "edited"
                workbook = client.get(f"{url}/export.xlsx?scope={scope}")
                workbook.raise_for_status()
                parsed = cells(workbook.content)[index + 1]
                name = f"api-{case['id']}-{scope}.xlsx"
                (args.out / name).write_bytes(workbook.content)
                records.append({"case": case["id"], "kind": f"api-{scope}", "agrees": agrees(parsed[1], case, value),
                                "sourceSpelling": str(value), "row": row, "cells": parsed,
                                "file": name, "sha256": hashlib.sha256(workbook.content).hexdigest()})
            assert client.get(f"{url}/report").json()["report"] == original_report
        # Large finite integers remain subject to the review API's existing bounds.
        rejected = client.post(f"{url}/review", json={"path": "total", "action": "edit", "value": 10**400 + 1})
        assert rejected.status_code == 422

    package_root = Path(fieldproof.__file__).parent
    result = {"label": args.label, "python": platform.python_version(),
              "fixtureScope": "Constructed scalar cases and the bundled synthetic invoice; no model or external extraction service.",
              "runtimeSha256": hashlib.sha256((package_root / "server/spreadsheet.py").read_bytes()).hexdigest(),
              "workflows": len(records), "disagreements": sum(not row["agrees"] for row in records),
              "oversizedApiCorrectionStillRejected": True, "records": records}
    (args.out / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("label", "python", "workflows", "disagreements")}))
    assert args.observe_only or result["disagreements"] == 0


if __name__ == "__main__":
    main()
