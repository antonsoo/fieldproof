# Changelog

All notable changes to this project are documented in this file.

## [0.2.1] - 2026-10-01

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
