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

The current source additionally stores numeric spellings outside its conservative
spreadsheet precision range as literal text; see the
[native numeric-cell study](../numeric-xlsx/README.md). The ordinary numeric
controls in this earlier study fit that range. Its retained measurements describe
the original text-export correction.

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

Run from the repository root after `uv sync --locked --extra dev` and
`npm ci --prefix web`. The optional Docker image supplies the spreadsheet engine, not a
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

Microsoft's Open XML SDK validator is a second, independent structure check:

```sh
docker build -t fieldproof-openxml-check:local studies/spreadsheet-export/openxml
docker run --rm --network none -v /tmp/fieldproof-xlsx:/work:ro \
  fieldproof-openxml-check:local /work/api.xlsx /work/python-cases.xlsx /work/browser-cases.xlsx
```

The validator uses `DocumentFormat.OpenXml` 3.3.0. Passing it is not a claim that
Microsoft Excel's interactive import was tested.

## Retained verification

The final implementation is `a0f04159d77f27ed911ed7bf169cd105a424e573`;
the CSV baseline is `0e2b6825c9de53854b84e935c9cfb34a6e02c0e9`.
A fresh archive passes lint/type checks, 505 Python checks (one real-Tesseract
check skipped), 62 web unit checks and 82 browser workflows. The first complete
browser run caught insufficient review space at 320 x 568 after adding a third
export format. Compact visible format labels keep the existing accessible
names and restore the usable field list; the final run passes in both engines.

Fresh wheel installs on Python 3.11.13 and 3.14.7 run the documented fixture CLI
and upload/extract/export API. Their JSON and CSV are byte-identical to the
baseline. All 23 UI files match between the tested build, wheel and HTTP service.
The added writer/compression code increases the live JavaScript bundle from
12,456 to 18,253 gzip bytes. No Python runtime dependency was added.

[Calc results](results/calc-summary.json) cover 15 actual workbooks: source API,
both installed APIs, both writers' scalar cases, and reviewed/all downloads from
Chromium and Firefox in both browser modes. All 299 rows match the expected
scalar values, with the explicitly recorded CRLF normalization in eight cells
across the four copies of the scalar workbook. None of the 1,649 text cells
became a formula. [Open XML validation](results/openxml-validation.json) reports
zero errors for every workbook. Byte-identical copies share one retained file.

Representative files are directly inspectable:

- [CSV baseline](results/baseline.csv) and [its JSON values](results/baseline.json).
- [API workbook](results/api.xlsx), [reviewed browser download](results/browser-reviewed.xlsx)
  and [all-fields browser download](results/browser-all.xlsx).
- [Python scalar workbook](results/cases-python.xlsx) and
  [browser scalar workbook](results/cases-browser.xlsx), from [the shared cases](cases.json).
- [Desktop](../../docs/assets/spreadsheet-export/chromium-demo-1440.png) and
  [phone](../../docs/assets/spreadsheet-export/firefox-live-375.png) screenshots.
  All eight screenshots were viewed.
- [Artifact receipt](verification.json), including source/archive, package,
  served-file, container-image and retained-file hashes.

This is source work with a locally built package. It does not publish a registry
release or update the hosted demo.
