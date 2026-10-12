"""Small, single-sheet XLSX export with literal text and typed scalar values.

No formula, hyperlink, or external relationship is inferred from document text.
Keep the browser writer in web/src/spreadsheet.ts and its contract in sync.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNS = (
    "field",
    "value",
    "original_value",
    "value_source",
    "verification_status",
    "review_status",
    "page",
)
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_BAD_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
_ESCAPED_TEXT = re.compile(r"_x[0-9a-fA-F]{4}_")


def _cell(value: Any, address: str) -> str:
    problem = None
    if value is None:
        return f'<c r="{address}"/>'
    if isinstance(value, bool):
        return f'<c r="{address}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)) and math.isfinite(value):
        return f'<c r="{address}" t="n"><v>{value}</v></c>'
    if not isinstance(value, str):
        problem = "is not a finite scalar"
    elif _BAD_TEXT.search(value):
        problem = "contains text that XLSX cannot safely represent"
    elif len(value) > 32767 or len(value.encode("utf-16-le")) // 2 > 32767:
        problem = "exceeds the XLSX limit of 32,767 UTF-16 units"
    if problem:
        raise ValueError(f"Cell {address} {problem}. Export JSON to keep the complete data.")
    # OOXML escape sequences in source text must stay literal. Escape CR after
    # protecting source underscores so XML line-ending normalization cannot eat it.
    text = _ESCAPED_TEXT.sub(lambda m: "_x005F_" + m.group()[1:], value)
    text = escape(text).replace("\r", "_x000D_")
    return f'<c r="{address}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def rows_to_xlsx(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Export the same rows as JSON/CSV, refusing partial or truncated output."""
    if len(rows) > 1048575:
        raise ValueError("XLSX supports 1,048,575 data rows. Export JSON to keep all rows.")
    cells = [
        '<row r="1">'
        + "".join(_cell(k, f"{chr(65 + i)}1") for i, k in enumerate(COLUMNS))
        + "</row>"
    ]
    for index, row in enumerate(rows, 2):
        cells.append(
            f'<row r="{index}">'
            + "".join(_cell(row[key], f"{chr(65 + i)}{index}") for i, key in enumerate(COLUMNS))
            + "</row>"
        )
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            f'<Relationships xmlns="{_PACKAGE_REL}">'
            f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            f'<workbook xmlns="{_NS}" xmlns:r="{_REL}">'
            '<sheets><sheet name="Fields" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{_PACKAGE_REL}">'
            f'<Relationship Id="rId1" Type="{_REL}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{_NS}">'
            f'<dimension ref="A1:G{len(rows) + 1}"/>'
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            "</sheetView></sheetViews>"
            '<cols><col min="1" max="3" width="32" customWidth="1"/>'
            '<col min="4" max="6" width="22" customWidth="1"/></cols>'
            "<sheetData>" + "".join(cells) + "</sheetData>"
            f'<autoFilter ref="A1:G{len(rows) + 1}"/></worksheet>'
        ),
    }
    buf = io.BytesIO()
    with ZipFile(buf, "w") as archive:
        for name, xml in parts.items():
            info = ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml)
    return buf.getvalue()
