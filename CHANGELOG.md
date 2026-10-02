# Changelog

All notable changes to this project are documented in this file.

## [0.2.2] - 2026-10-02

### Fixed

- A result or fixture JSON saved by a Windows editor or shell. Notepad's
  "UTF-8 with BOM" and PowerShell's `-Encoding utf8` put a byte-order mark
  first ("not valid JSON (line 1, column 1: Unexpected UTF-8 BOM ...)"), and
  PowerShell's `>` writes UTF-16 ("is not UTF-8 text"). All three are read, by
  the CLI and by the review server.
- Output written to a pipe or a file is UTF-8, so a document path outside the
  system's code page can be printed when stdout is redirected on Windows.

## [0.2.1] - 2026-10-02

### Added

- Published to PyPI: `pip install fieldproof`. The package includes the built
  review UI, so `fieldproof serve` works without a Node toolchain
  (`scripts/bundle_ui.py` builds it into the package before a release).
- `fieldproof --version`.

### Fixed

- A value quoted from inside a longer word could be marked `verified`. The
  exact matcher refused a quote that cuts a word, and the fuzzy fallback then
  scored the same fragment 100/100 as a perfect partial match. On the example
  invoice, a vendor name of `wind` (inside "Northwind") and an invoice number
  of `0214` (inside "NW-20260214") both verified. A match now has to cover
  whole words; when the best fuzzy window cuts one, the quote is scored
  against the whole words, so those two are `unsupported` and `458.00` is a
  weak match for `$2,458.00`. Punctuation glued to a word may be left out of
  a quote (`1` for `1,`, `2,458.00` for `$2,458.00`), and every such
  occurrence counts when deciding whether a quote is ambiguous.
- A string value one digit off verified: `NW-20260215` for a document reading
  `NW-20260214` is 96% similar, which passed both the grounding and the value
  check. Every run of digits in a string value now has to appear in the
  evidence as written.
- `--provider anthropic` against the real SDK. The provider had only met a
  mocked client, which returned `parsed_output=None` for a reply that isn't
  the schema. The SDK's `messages.parse` raises instead: an extraction cut
  off at `max_tokens` (a long invoice) or refused came out as a pydantic
  traceback, `Invalid JSON: EOF while parsing a string`. The provider now
  streams the reply, reads its `stop_reason` and says which it was in one
  line: `error: Claude's reply was cut off at 16000 output tokens, before the
  Invoice was complete; raise the limit (--max-tokens) or extract a shorter
  document`. New `--max-tokens` option. The tests run the real SDK over a
  mocked HTTP transport.
- The declared minimum `anthropic>=0.40` had no `messages.parse`:
  `AttributeError: 'Messages' object has no attribute 'parse'`. The minimum
  is 0.77, the first release with structured outputs on the Messages API,
  and the provider tests pass on it.
- Two more declared minimums did not work. With `typer` below 0.15.4 every
  command stopped (`Type not yet supported: pathlib.Path | None` on 0.12.0;
  `make_metavar() takes 1 positional argument` on `--help` with a current
  click), and with `pydantic` below 2.10 a typed result could not be built
  from `Evidenced` values. The minimums are `typer>=0.15.4` and
  `pydantic>=2.10`, and CI has a job that installs the oldest allowed version
  of every direct dependency on the oldest supported Python and runs the
  tests there.
- A match could begin or end inside a ligature (`inal` matched "ﬁnal").
- A result or fixture file that isn't valid JSON, isn't an object, or doesn't
  fit the schema printed a traceback from `extract` and `verify`, and was an
  unexplained 500 in the review UI. The CLI prints one line (`error:
  result.json does not match the Invoice schema: total.value: Input should be
  a valid number, unable to parse string as a number`) and the server answers
  422 with the same message. A file
  that isn't a PDF, a missing API key and a failed API request are one line
  too.

### Added

- Seeded fuzz tests for the promise above: an exact match always covers whole
  words, a piece of a longer word never verifies, a value with a number the
  document lacks never verifies, and a damaged result file ends in a report or
  a one-line error.

## [0.2.0] - 2026-09-30

### Fixed

- A numeric date with both parts 12 or under (`03/04/2026`) was always read
  month first, so a day-first document's correctly extracted date was flagged
  and a month-first misreading of it was marked verified. Such a date is now
  read in the order another date on the same document settles, and goes to
  review when none does.
- Boolean checks matched substrings: "no" inside "notice", "November" or
  "none" counted as a negation. They match whole words now.

### Changed

- The live demo opens on the invoice with its first flagged field selected,
  instead of a landing page with three buttons. A sample switcher in the top
  bar changes documents without a reload, and `#invoice` / `#receipt` /
  `#contract` link straight to one.
- `fieldproof serve`: a "New document" button returns to the upload screen.
- A short note in the demo's field pane says the documents are synthetic
  and the extractions are fixtures with planted errors.

### Fixed

- Opening a sample on a narrow screen no longer scrolls the top bar out of
  view.
- The Anthropic provider's docs no longer call Claude Opus 5.5 Anthropic's
  most capable model.

## [0.1.0] - 2026-09-24

Initial release.

### Added

- `fieldproof.document`: PDF text-layer loading (pdfplumber), page image
  rendering (pypdfium2), and an optional Tesseract OCR fallback for scanned
  documents.
- `fieldproof.schemas`: `Evidenced[T]` value wrapper, a generic
  `iter_evidenced_fields` walker, and built-in Invoice, Receipt, and
  ContractKeyTerms templates.
- `fieldproof.extract`: a provider-agnostic `Extractor` protocol, an
  Anthropic structured-output implementation, and a fixture provider for
  tests/offline use.
- `fieldproof.ground`: Unicode-aware text normalization and exact/fuzzy
  quote alignment (rapidfuzz) mapping evidence to page word bounding boxes.
- `fieldproof.verify`: value-vs-evidence consistency checks (numbers,
  dates, strings, booleans), cross-field rules for invoices and receipts,
  and the `verified` / `needs_review` / `unsupported` verdict engine.
- `fieldproof.server`: a FastAPI app for upload, extraction, review, and
  JSON/CSV export.
- `fieldproof` CLI: `extract`, `verify`, `serve`.
- A TypeScript review UI (Vite, no framework) with grounded highlight
  overlays, keyboard navigation, and a static demo mode for GitHub Pages.
- Synthetic sample documents (invoice, receipt, contract) and fixture
  extractions with planted errors for the test suite and the Pages demo.
