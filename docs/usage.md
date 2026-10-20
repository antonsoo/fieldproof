# Usage

## CLI

```bash
fieldproof extract doc.pdf --schema invoice --provider anthropic --out result.json
fieldproof verify result.json doc.pdf   # re-ground/re-verify an existing extraction
fieldproof serve --port 8000            # API + review UI
```

**Report protection (source checkout, unreleased).** CLI output cannot replace
the source PDF or consumed fixture, including through path aliases. `verify`
still updates its result in place, but a failed write preserves the previous
report. Output symlinks are refused; successful reports are private (0600 on
POSIX). The [actual CLI replay](../studies/report-files/README.md) retains source
overwrite and kernel-enforced short-write reproductions, plus unchanged normal
report bytes.

For image-only PDFs, install this source checkout with `pip install '.[ocr]'`
and install Tesseract with its English language data through your system's
package manager. The same `extract` and `verify` commands then use the fallback
automatically; no remote OCR service is called. The CLI uses English at 144 DPI,
with a 30-second Tesseract timeout per page and the document limits described in
the [OCR study](../studies/ocr-fallback/README.md). The library's `load_scanned_pdf`
also accepts `language`, `timeout` and `limits`. PDFs containing some native text
still use the native loader by default. In the source checkout, opt in for a
mixed document with:

```bash
fieldproof extract mixed.pdf --schema invoice --fixture extraction.json --ocr-missing-pages --out result.json
fieldproof verify result.json mixed.pdf --ocr-missing-pages
```

The library equivalent is `fieldproof.document.ocr.load_pdf_with_ocr`, with the
same language, timeout and combined document budgets. `report.ocr.processed_pages`
names attempted OCR pages, including blank results; other pages retain native
text and boxes. That mode leaves pages with any native words alone. For a
partial text layer or visible form values on those pages, select all-page OCR:

```bash
fieldproof extract form.pdf --schema invoice --fixture extraction.json --ocr-all-pages --out result.json
fieldproof verify result.json form.pdf --ocr-all-pages
```

`--ocr-all-pages` uses text recognized from every rendered page as the sole
word evidence. Native words are replaced, including hidden text; they are not
merged with OCR words. This can recover visible form values, and can introduce
OCR errors into text that native extraction read correctly. The report records
the engine, language, DPI, every attempted page and any empty pages. Failed or
unavailable OCR leaves earlier reports intact and does not fall back to native
text. Choose one of `--ocr-missing-pages` and `--ocr-all-pages`.

| CLI choice | Word evidence |
| --- | --- |
| Default | Native text; OCR fallback if the whole PDF has no native words |
| `--ocr-missing-pages` | Native pages plus OCR of pages without native words |
| `--ocr-all-pages` | OCR of every rendered page |

The library equivalent is `load_pdf_with_ocr(source, mode="all")`, with the
same language, timeout and document budgets. The review server uses its
native-text path; these choices are for the CLI and library. See the
[visible form replay](../studies/visible-form-ocr/README.md).

**PDF forms (current source, unreleased).** Review images and OCR input include
saved static AcroForm appearances. Native extraction still reads page text,
not widget values; a form-only PDF requires the OCR extra. Use all-page OCR
to recognize rendered form values on pages that also contain native text.
JavaScript and XFA are not run, and XFA PDFs are rejected with a diagnostic.
Save a static PDF from a form viewer to use such a document. See the
[native form replay](../studies/form-appearances/README.md).

A number written `60.000` is sixty or sixty thousand, and `03/04/2026` is 4
March or 3 April. When nothing else in the document settles which, the field
is `needs_review`. `--number-style thousands` (or `decimal`) and `--date-order
dmy` (or `mdy`) on either command supply a fallback when no decisive convention
is found (source checkout, unreleased). A unique convention inferred from the
document takes precedence. If the document shows conflicting conventions,
ambiguous values stay in review even with a supplied fallback. Explicit amounts
and unambiguous dates remain usable. The [mixed-convention study](../studies/mixed-conventions/README.md)
retains actual PDF and CLI before/after reports and explains the heuristic limits.

The source also reads Arabic decimal U+066B and grouping U+066C with
ASCII, Arabic-Indic or Extended Arabic-Indic decimal digits. Their explicit
roles do not decide how an ambiguous Latin `.` is used elsewhere. Arabic rate
signs remain part of the evidence and cannot verify an ordinary amount. Mixed
Latin/Arabic separator spellings require review. See the
[native locale and PDF replay](../studies/arabic-numbers/README.md). This
correction is included in the README's pinned source install, but not in PyPI 0.2.7.

Adjacent groups such as `1 234,56` require review: treating the second group as
234.56 is unsafe, and the verifier does not guess the combined amount. It retains
the whole source span. Clearly separated numeric cells keep their individual
values using page geometry; tightly spaced rows remain uncertain. Plain string
callers should preserve actual cell boundaries with tabs/newlines. See the
[paired PDF layout study](../studies/spaced-numbers/README.md) for the heuristic
and its limits (source checkout, unreleased).

Only a complete, calendar-valid numeric date can settle the date order. An
unrelated `99/01/2026`, a phone-number fragment or `ABC14/03/2026XYZ` cannot
override your `--date-order` default or verify an ambiguous issue date. The
[date evidence study](../studies/date-conventions/README.md) includes a runnable
PDF example, before/after results and the cost of rejecting fused OCR tokens
(source checkout, unreleased).

Extracted date **values** must be one calendar-valid `YYYY-MM-DD` date, as the
built-in schemas request. Evidence can still say `March 4, 2026` or use a numeric
local format. A value such as `not 2026-03-04`, `03/04/2026`, or two alternative
dates needs review; the verifier no longer selects a convenient substring or
assumes the claim's day/month order. Invoice date ordering remains `not_checked`
until both claims meet this format. [Actual PDF and CLI captures](../studies/date-claims/README.md)
retain the original values, evidence and page highlights. This is a source
correction, not a PyPI release.

Written date **evidence** must keep its complete day and year too. The source
checkout sends `May 1, 20260` to review instead of verifying May 1, 2026 by
dropping a digit. Grounding and value checks share the same written-date
boundaries and supported month abbreviations. The [PDF replay](../studies/written-dates/README.md)
retains the false verification, corrected report and supported-date controls.

`--provider anthropic` defaults to `claude-opus-5-5` (Claude Opus 5.5); pass
`--model claude-sonnet-5-5` or any other model id to override it.

Real output, captured from this repo's sample documents:

![fieldproof extract and verify, real terminal output](assets/cli-extract-verify.png)

## As a library

```python
from fieldproof.document import load_pdf
from fieldproof.schemas import Invoice
from fieldproof.extract import FixtureExtractor
from fieldproof.verify import verify

document = load_pdf("examples/invoice.pdf")
result = FixtureExtractor(fixture_path="examples/fixtures/invoice.json").extract(document, Invoice)
report = verify(result.data, document)

for field in report.fields:
    if field.status != "verified":
        print(field.path, field.status, field.reasons)
# po_number unsupported ["none of the evidence quotes (...) could be located in the document"]
# subtotal needs_review ['subtotal + tax = 2666.93 but total is 2600.00']
# tax needs_review ['subtotal + tax = 2666.93 but total is 2600.00']
# total needs_review ['value 2600 does not match 2666.93 parsed from the evidence', ...]
```

## Review decisions and exports

Saving a correction records a human decision; it does not rerun grounding,
arithmetic or date checks. The UI retains the originally extracted value,
its evidence and its verification status. Approve and Reject retain a saved
correction; Reset clears it and restores the original value. A rejected field
is omitted from either export scope.

The UI defaults to **Reviewed only** (approved or edited fields). **All except
rejected** also includes pending fields, with their review status attached.
Exports are disabled during a save and snapshot the displayed decisions when
clicked. The local server's `/api/documents/{id}/export.json`, `.csv` and `.xlsx` routes
accept `?scope=reviewed`; their default remains `all` for existing API clients.

**XLSX is the spreadsheet option:** text identifiers such as `00034`, `1E10`
and `=1+1` are stored as text cells. Ordinary numbers and booleans retain their
types. In the source checkout, numbers outside a conservative spreadsheet
precision range are also stored as literal text: integers with 16 or more
digits, longer fractional spellings and subnormal floats cannot silently
change through numeric-cell rounding. JSON retains the original scalar type.
No formulas or hyperlinks are generated. CSV remains a raw data export: a
spreadsheet importer can reinterpret its text as numbers, dates or formulas.
XLSX refuses oversized or unsupported text with a JSON fallback instead of
truncating it. Spreadsheet programs still have their own numeric precision
and newline behavior; see the [spreadsheet export study](../studies/spreadsheet-export/README.md)
and [numeric-cell reproduction](../studies/numeric-xlsx/README.md). Text cannot
recover rounding that already occurred in a caller's float or JSON conversion.

All three formats include these columns, with `original_value` and `value_source`
added in the current unreleased work:

| Column | Meaning |
| --- | --- |
| `field` | Extraction field path, including nested list indices |
| `value` | Effective value, preserving scalar types in JSON |
| `original_value` | Value from the original extraction |
| `value_source` | `extraction` or `correction` |
| `verification_status` | Automated verdict on the original extracted value |
| `review_status` | Human decision: pending, approved or edited |
| `page` | Original evidence page, or null if no page was grounded |

## Document sessions and limits

The local UI's **Sessions** dialog reopens uploaded PDFs and their saved
decisions, including after a tab reload. **New document** keeps the previous
session on the server. **Remove** requires confirmation and frees its PDF,
text, extraction and decisions; export anything you need first. Sessions
remain in memory until removal or server restart. They are not a durable
archive. An open correction must be saved or cancelled before navigating away.

**OCR in the local UI (source checkout, unreleased).** Enable the `ocr` extra
and install Tesseract plus English language data on the server. Choose Text
source before uploading: Native PDF text, OCR scanned pages, or OCR every page.
Scanned-page mode only replaces pages without native words; all-page mode
replaces every page's word evidence with OCR of its rendered image. Both OCR
choices limit the whole document to 8 pages. A missing engine returns an error
without adding a session; choosing OCR is never silently replaced by native text.

The source notice appears before extraction and during review. Mixed documents
identify whether the current page uses native or OCR words. OCR verdicts apply
to recognized text, so inspect the image as well. JSON, CSV and XLSX exports
from either OCR choice add `text_mode` and `text_source`; each row states OCR
engine/version/language/render resolution, Native PDF text, or Unlocated evidence.
These describe the original evidence even after a human correction. Native
exports keep the original seven columns. The hosted CORD example is precomputed;
it cannot recognize a new upload in the static demo.

**Save archive** (source checkout, unreleased) downloads the PDF, original
extracted claims and **all** saved decisions, including pending and rejected
fields. After restarting `fieldproof serve`, choose **Open review archive**
on the upload screen to continue. No model call or API key is needed.
The archive is separate from the Reviewed/All value-export scope.

Opening an archive creates a new session and reruns grounding and verification
on the original claims, using the saved text-source choice. OCR archives rerun
recognition and need the OCR tools on the restoring server. Human corrections
stay separate. Automated verdicts
can change with a different verifier version; the old report is not archived.
This is an explicit save, not autosave: changes after downloading are not in
that file. The ZIP includes the document's full contents, is unencrypted and
editable, and does not authenticate who made its decisions. See the
[format, limits and recovery instructions](review-archives.md).

The server refuses new work when a limit is reached and preserves the previous
document and review. It never evicts a session to make room.

| Resource | Local server limit |
| --- | --- |
| Uploaded PDF | 25 MiB; native text: 64 pages; either OCR mode: 8 pages |
| Rendered page | 16 million pixels at 144 DPI |
| Extracted document text | 100,000 words and 2 million characters |
| Retained sessions | 8 documents; 100 MiB of PDFs; 200,000 words total |
| Fixture / review | 2 MiB fixture JSON; 2,000 fields; 1 MiB of saved corrections per session |
| Review archive | 30 MiB ZIP; 25 MiB PDF; 2 MiB each for serialized claims and decisions; 8 KiB manifest |
| Pending work | 4 intake requests; 2 PDF uploads or archive restores; 4 queued/running PDF or verification operations |

PDF loading, page rendering and extraction verification run one at a time in disposable processes.
Each operation has a 30-second execution timeout and a bounded queue wait.
On Linux, each worker also has a 768 MiB address-space limit, 20 seconds of
CPU time, and a 64 MiB output-file limit. Windows receives the timeout and
application limits without the Unix process resource limits. These budgets
contain PDF processing and verification; they do not measure extraction accuracy or guarantee
that every valid PDF will fit. Scanned PDFs can be processed through the
CLI's OCR fallback or the review server's explicit Text source choice.

API clients can list sessions with `GET /api/documents`, reopen metadata and
the saved report with the existing document/report routes, and remove one
with `DELETE /api/documents/{id}`. Removal or concurrent extraction is
refused while extraction owns that session.

## Bring your own schema

Extraction validation requires Pydantic 2.12 or later and forbids unexpected
members, including inside nested models and `Evidenced` wrappers. Declare an
additional claim in the schema instead of depending on Pydantic's default
extra-field omission. Declared aliases and optional defaults still work.
These checks apply before Fieldproof creates a schema instance; they cannot
recover fields a caller already discarded while constructing its own model.

Models built from `Evidenced[T]` leaves are walked generically by
`iter_evidenced_fields`; source grounding and value checks do not need a
schema-specific implementation:

```python
from pydantic import BaseModel
from fieldproof.schemas import Evidenced

class PurchaseOrder(BaseModel):
    po_number: Evidenced[str]
    approved: Evidenced[bool]
    amount: Evidenced[float]
```

Each present `Evidenced` wrapper must hold a string, integer, float or boolean.
The unreleased verifier checks actual values before grounding and raises a
field-specific `ValueError` for other types, without changing the model or
returning a partial report. Pydantic's generic type constraints alone do not
enforce this boundary: an object or null value with an unrelated real quote
previously passed verification. Explicit string kinds also require a string
if the model was mutated after construction.

Put containers outside the wrapper: `dict[str, Evidenced[str]]` gives each
claim its own evidence; `Evidenced[dict[str, str]]` has no verification rule.
For an absent optional claim, use `Evidenced[str] | None`; a present wrapper
with `value=None` is an error. Python `date`, `Decimal`, bytes and arbitrary
objects are not silently converted to supported scalar values. Represent
calendar dates as ISO strings with `EvidencedDate`. The
[claim-type PDF replay](../studies/claim-types/README.md) retains before/after
results, including an object that previously supplied a false row-location hint.

The unreleased source also traverses nested models, lists, tuples and
string-keyed mappings, such as `checks: dict[str, Evidenced[bool]]`. Mapping
keys use JSON-quoted paths (`checks["loading-bay"]`); model members use dots
and positions use numeric brackets. A literal field named `a.b` is `["a.b"]`,
distinct from a nested `a.b`. Non-string mapping keys raise an explicit error.
The [custom-container PDF replay](../studies/container-claims/README.md) shows
previously omitted unsupported claims and a field-path collision. Literal
mapping keys cannot create row-location hints by containing index-like text.
Custom models are a Python-library integration; the CLI and server schema
selector still offer the built-in invoice, receipt and contract models.

For custom string fields, the unreleased source provides explicit kinds:

```python
from pydantic import BaseModel
from fieldproof.schemas import EvidencedDate, EvidencedText

class Application(BaseModel):
    candidate_name: EvidencedText
    available_from: EvidencedDate
    date_label: EvidencedText
```

Both retain the usual `{value, evidence, page}` JSON shape. `EvidencedDate`
keeps the supplied string and asks verification to check one calendar-valid
`YYYY-MM-DD` claim against its quote; invalid claims remain visible for review.
`EvidencedText` checks literal text regardless of its name. Reports record the
explicit `declared_kind`, separately from tolerance notes, so a correctly
grounded text field can still supply a row-location hint.

For generic `Evidenced[str]`, the final field name or mapping key supplies a
naming hint: complete `date`, `dates`, `birthdate` or `birthdates` words,
including snake_case/camelCase forms. Numeric indices retain the collection's
name. Ancestors and incidental substrings in `candidate_name`, `updated_by`
or `validate_status` no longer turn text into a date. Unseparated custom names
such as `issuedate` should declare `EvidencedDate` explicitly; the convention
cannot infer business meaning. For date-valued mappings, use
`dict[str, EvidencedDate]`: arbitrary keys do not inherit a date kind from
the mapping's name. This matters when migrating a custom schema that relied
on the previous whole-path substring guess.
The [real-PDF replay](../studies/string-kinds/README.md)
checks these distinctions, preserved calendar safeguards and explicit kinds
through fixture extraction and JSON roundtrips.

In the source checkout, Boolean leaves need one explicit `yes`/`no` or
`true`/`false` answer, optionally labelled (`Approval: yes`, `Renewal = false`).
Prose and checkbox choices need review: a real quote saying "approved, not
denied" must not verify `approved=False` just because it contains "not".
The [Boolean evidence replay](../studies/boolean-evidence/README.md) retains the
PDFs, both claimed values, and their unchanged source highlights. This checks
the written answer, not whether its label belongs to the chosen schema field.

Cross-field rules (line-item sums, date ordering) are schema-specific and
currently only implemented for the built-in Invoice/Receipt templates - see
[Limitations](#accuracy-and-limitations).

## Bring your own extractor

`Extractor` is a structural protocol (`def extract(self, document, schema) ->
ExtractionResult`) - implement it against any provider and
`fieldproof.ground` / `fieldproof.verify` work unchanged, since they only
depend on the `Evidenced` shape, not on Anthropic.
