# Literal text in spreadsheet exports

A reviewed invoice number can survive CSV serialization and still change when
opened in a spreadsheet. This study uses synthetic text values in the bundled
invoice fixture and opens the actual API exports in LibreOffice Calc 7.4.7.2.
It does not send document content to an extraction service.

| Source text | CSV, standard columns | XLSX |
| --- | --- | --- |
| `00034` | Numeric `34` | Text `00034` |
| `1E10` | Numeric `10000000000` | Text `1E10` |
| `12345678901234567890` | Rounded numeric `1.23456789012346E+019` | Original text |
| `2026-01-02` | Date value `46024` | Original text |
| `=1+1` | Formula yielding `2` when formula import is enabled | Text `=1+1` |

The CSV importer was configured explicitly: UTF-8, comma separator, double-quote
text delimiter, standard columns, English (US), no trimming, and both enabled
and disabled formula import. With formula import disabled, the first four
conversions still occur. These are not claims about every spreadsheet's defaults.
The settings follow [LibreOffice's CSV filter documentation](https://help.libreoffice.org/latest/en-US/text/shared/guide/csv_params.html).

## Export contract

The API and both browser modes add XLSX alongside unchanged JSON and CSV.
The workbook contains the same seven columns, reviewed/all scope, rejected-field
omissions, effective values, original values, correction provenance and original
verification statuses. Browser exports snapshot the currently displayed review
and work offline after loading. Text is explicitly stored as an
[OOXML inline string](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.inlinestring).
Numeric and boolean values use their corresponding cell types. Null is blank.
No formula, hyperlink, macro or external relationship is generated.

The writer is deliberately limited to one worksheet: headers, frozen first row,
column widths, and an autofilter. Python uses its standard ZIP library; the
browser uses `fflate` for ZIP compression. There is no spreadsheet import engine
in the application. Both writers are exercised with the same 27 scalar cases.

Literal `_xHHHH_` text must be protected against
[OOXML escape decoding](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/bd0aa042-434a-4ca7-b25f-4e1fd25a954d).
Carriage returns are encoded rather than lost to XML newline normalization.
The workbook refuses strings over 32,767 UTF-16 units, unpaired surrogates,
XML-forbidden controls/noncharacters, and over 1,048,575 data rows. The error
names the cell and directs the user to JSON; no partial workbook is downloaded.
The length bound is conservative for supplementary Unicode characters relative
to [Excel's documented cell limit](https://support.microsoft.com/en-us/excel/excel-specifications-and-limits).

Spreadsheet applications can still change imported data. In this Calc version,
CRLF becomes LF when reading a workbook, though isolated CR and LF survive and
the XLSX stores the original sequence. Calc internally represents boolean cells
as `TRUE()`/`FALSE()` formulas; the file contains boolean cells, not formulas.
Ordinary spreadsheet numeric precision still applies to numeric values. Use JSON
when exact scalar serialization and line endings matter. Microsoft Excel was
not available for interactive verification.

## Reproduce

Run from the repository root after `uv sync --locked --extra dev` and `npm ci
--prefix web`. The optional Docker image supplies the spreadsheet engine, not a
runtime dependency of Fieldproof:

```sh
uv run python studies/spreadsheet-export/generate.py /tmp/fieldproof-xlsx --xlsx
node studies/spreadsheet-export/generate-browser.mjs /tmp/fieldproof-xlsx
docker build -t fieldproof-spreadsheet-check:local studies/spreadsheet-export
```

Use Node 24 for the direct browser-writer script. Copy `inspect_calc.py` to the
output directory, then open the exports in a network-disabled container:

```sh
cp studies/spreadsheet-export/inspect_calc.py /tmp/fieldproof-xlsx/
docker run --rm --network none -v /tmp/fieldproof-xlsx:/work \
  fieldproof-spreadsheet-check:local python3 /work/inspect_calc.py \
  /work/api.csv /work/api.xlsx /work/python-cases.xlsx /work/browser-cases.xlsx
```

The retained results record the exact engine, import settings and cell values.
These cases exercise transport into a spreadsheet, not extraction accuracy.
