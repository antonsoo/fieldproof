"""Workbook cell types are part of the export contract, not display guesses."""

import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from fieldproof.server.spreadsheet import COLUMNS, rows_to_xlsx

CASES = json.loads(
    (Path(__file__).parents[1] / "studies/spreadsheet-export/cases.json").read_text()
)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def workbook_rows(payload):
    with ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml",
        }
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        assert root.findall(".//s:f", NS) == []
        assert root.findall(".//s:hyperlink", NS) == []
        assert b"External" not in archive.read("xl/_rels/workbook.xml.rels")
        result = []
        for row in root.findall("s:sheetData/s:row", NS):
            values = []
            for cell in row:
                if cell.attrib.get("t") == "inlineStr":
                    text = cell.findtext("s:is/s:t", "", NS)
                    values.append(
                        re.sub(
                            r"_x005[Ff]_x[0-9a-fA-F]{4}_|_x([0-9a-fA-F]{4})_",
                            lambda m: "_" + m[0][7:] if m[1] is None else chr(int(m[1], 16)),
                            text,
                        )
                    )
                else:
                    value = cell.findtext("s:v", None, NS)
                    values.append(
                        None
                        if value is None
                        else value == "1"
                        if cell.attrib.get("t") == "b"
                        else float(value)
                    )
            result.append(values)
        return result


def test_workbook_preserves_text_scalars_and_provenance():
    assert workbook_rows(rows_to_xlsx(CASES)) == [list(COLUMNS), *[list(r.values()) for r in CASES]]


@pytest.mark.parametrize(
    "value", [9007199254740993, 10**400 + 1, 1.2345678901234567, 1e-309, 1e308]
)
def test_numeric_evidence_outside_spreadsheet_precision_is_literal_text(value):
    row = {**CASES[0], "value": value, "original_value": value}
    assert workbook_rows(rows_to_xlsx([row]))[1][1:3] == [str(value), str(value)]


@pytest.mark.parametrize("value", [999999999999999, -999999999999999, 123.456789012345, 1e-307])
def test_ordinary_numeric_boundary_keeps_its_scalar_type(value):
    assert workbook_rows(rows_to_xlsx([{**CASES[0], "value": value}]))[1][1] == value


@pytest.mark.parametrize("column", COLUMNS)
@pytest.mark.parametrize(
    "value",
    ["\x00", "\x0b", "\ud800", "\udfff", "\ufffe", "a" * 32768, "😀" * 16384, float("inf"), {}],
)
def test_export_refuses_unrepresentable_cells_in_every_column(column, value):
    row = {**CASES[0], column: value}
    with pytest.raises(ValueError, match=r"Cell [A-G]2 .*Export JSON"):
        rows_to_xlsx([row])


@pytest.mark.parametrize("value", ["a" * 32767, "😀" * 16383 + "a"])
def test_text_length_boundary_is_preserved(value):
    assert workbook_rows(rows_to_xlsx([{**CASES[0], "value": value}]))[1][1] == value


def test_header_only_export_and_row_limit():
    assert workbook_rows(rows_to_xlsx([])) == [list(COLUMNS)]

    class TooManyRows(list):
        def __len__(self):
            return 1048576

    with pytest.raises(ValueError, match="1,048,575 data rows"):
        rows_to_xlsx(TooManyRows())
