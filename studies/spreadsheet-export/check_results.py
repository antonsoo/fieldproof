"""Compare actual Calc cells with exported JSON, retaining every deviation."""

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("calc_report", type=Path)
args = parser.parse_args()
root = args.directory
engine = json.loads(args.calc_report.read_text())
columns = [
    "field",
    "value",
    "original_value",
    "value_source",
    "verification_status",
    "review_status",
    "page",
]
ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
results = []
for run in engine["results"]:
    relative = run["file"].removeprefix("/work/")
    path = root / relative
    if path.suffix != ".xlsx":
        interesting = {
            "vendor_name",
            "invoice_number",
            "issue_date",
            "po_number",
            "line_items[0].description",
        }
        results.append(
            {
                "file": relative,
                "mode": run["mode"],
                "cells": {
                    r[0]["text"]: r[1] for r in run["rows"][1:] if r[0]["text"] in interesting
                },
            }
        )
        continue
    expected = json.loads(
        (
            Path(__file__).parent / "cases.json"
            if "cases" in path.name
            else path.with_suffix(".json")
        ).read_text()
    )
    expected_rows = [columns, *[[r[c] for c in columns] for r in expected]]
    assert len(run["rows"]) == len(expected_rows), relative
    normalized, text_cells, numeric_cells = [], 0, 0
    for i, (actual, values) in enumerate(zip(run["rows"], expected_rows, strict=True), 1):
        for j, (cell, value) in enumerate(zip(actual, values, strict=True)):
            location = f"{chr(65 + j)}{i}"
            if isinstance(value, str):
                text_cells += 1
                assert cell["type"] == "TEXT" or (value == "" and cell["type"] == "EMPTY"), (
                    relative,
                    location,
                    cell,
                )
                if cell["text"] != value:
                    assert "\r\n" in value and cell["text"] == value.replace("\r\n", "\n"), (
                        relative,
                        location,
                        value,
                        cell,
                    )
                    normalized.append({"cell": location, "source": value, "calc": cell["text"]})
            elif value is None:
                assert cell["type"] == "EMPTY", (relative, location, cell)
            else:
                numeric_cells += 1
                assert cell["number"] == value, (relative, location, value, cell)
                assert cell["type"] == ("FORMULA" if isinstance(value, bool) else "VALUE"), (
                    relative,
                    location,
                    cell,
                )
    with ZipFile(path) as z:
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        assert not sheet.findall(".//s:f", ns)
        assert not sheet.findall(".//s:hyperlink", ns)
        for name in z.namelist():
            if name.endswith(".rels"):
                assert all(r.get("TargetMode") != "External" for r in ET.fromstring(z.read(name)))
    results.append(
        {
            "file": relative,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(expected),
            "text_cells": text_cells,
            "numeric_or_boolean_cells": numeric_cells,
            "text_cells_interpreted_as_formulas": 0,
            "generated_formulas_or_hyperlinks": 0,
            "newline_normalizations": normalized,
        }
    )
print(json.dumps({"engine": engine["version"], "results": results}, ensure_ascii=True, indent=2))
