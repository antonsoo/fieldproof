# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] - 2026-09-30

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
