# Changelog

All notable changes to this project are documented in this file.

## Unreleased

- Add explicit native, missing-page OCR and all-page OCR choices to the local
  review UI and upload API. Show per-page word provenance, retain it in JSON,
  CSV and XLSX, and reopen OCR reviews from version-2 archives. Preserve native
  export formats and version-1 archives. Bound OCR documents to 8 pages and
  stop recognizer descendants on worker timeout.
- Add a credited CORD receipt photograph with authored claims to the static
  demo, plus real API, native-recognizer and archive replays. The hosted example
  is precomputed; OCR for new PDFs runs on the local server.

- Add `--ocr-all-pages` to extract/verify and `load_pdf_with_ocr(..., mode="all")`.
  Recognize every rendered page, including visible form values on pages with
  native text, with explicit OCR provenance. Keep the native and missing-page
  choices, reject conflicting flags, and preserve prior reports on OCR failure.

### Saved PDF form appearances

- Render static AcroForm values, checked boxes and choices in review PNGs and
  optional OCR input. Initialize PDFium's form environment before page handles,
  consistently for the original and paint-suppressed reference.
- Keep native page-text extraction distinct from widget values. Retain hidden
  field behavior, original PDF bytes and existing covered-text reviews. Reject
  unsupported XFA forms with a worker-safe diagnostic; do not run JavaScript.
- Retain 14 authored controls, two pinned native producer documents and one
  invented public-form fill. Actual local OCR of the form-only control changes
  from no words to `$100.00`. [Evidence](studies/form-appearances/README.md).

### Fraction evidence boundaries

- Keep numeric slash fractions whole, including U+2044 fraction slash,
  U+2215 division slash and spaces around ASCII slashes. A PDF printing
  `1⁄2 m` previously verified both 1 and 2 as the quantity. Fractions remain
  unsupported numeric evidence and require review rather than approving a
  component or guessing a value.
- Preserve source characters, spans and page geometry; clipped component
  quotes retain the complete unsupported context. Keep existing date syntax
  under the date lexer so a preceding receipt dash is not borrowed.
- Retain six authored PDF controls and a complete invoice/CLI reproduction.
  Replaying 133,722 existing CORD/SROIE claims preserves every verdict,
  candidate count and location classification. Two already-reviewed mutated
  quantity claims retain a wider slash-containing source span. Review exports
  and archive restoration keep original claims and automated verdicts separate
  from a human correction. [Evidence](studies/fraction-evidence/README.md).

### Space-separated numeric evidence

- Keep uncertain adjacent numeric groups in one source span. A PDF printing
  `1 234,56` previously verified the fragment 234.56. Neither a component nor a
  guessed combined amount now verifies from uncertain spacing.
- Retain line boundaries and clear gaps between numeric cells from page geometry,
  preserving quantity/price rows without joining columns. Tight/invalid geometry
  stays unresolved. Signs remain attached across same-row gaps.
- Retain native French/Russian/Swedish formatter output and 134 claims through
  23 authored PDF pages, including paired layouts with identical flattened text.
  The current source changes the older tight-row quantity expectation to review;
  historical numeric study receipts are retained unchanged.
- Keep unresolved normalized value matches weak instead of dropping them: a
  rejected spaced occurrence must not make another location falsely unique.
  Date/time syntax remains distinct from space-separated amount groups.

### Arabic numeric evidence

- Read Arabic decimal U+066B and grouping U+066C as part of a complete amount,
  including Arabic-Indic, Extended Arabic-Indic and ASCII digits. A page
  printing 1234.56 with these separators previously verified a claim of 234
  while rejecting the correct amount.
- Keep Arabic percentage, per-mille and per-ten-thousand signs inside numeric
  evidence; rates cannot supply ordinary amounts. Malformed or mixed separator
  spellings stay unsupported as whole tokens. Preserve source spans, signs,
  precision and existing comma/dot convention choices.
- Retain native Intl.NumberFormat output, 21 authored PDF controls, 87 before/after
  claims and real API/worker evidence in `studies/arabic-numbers`. This is a local
  source correction, without a registry release or hosted update.

### Renderer glyph bounds

- Associate native source characters with PDFium font envelopes and restrict
  observed support to native ink bounds. Advance rectangles alone miss ordinary
  italic overhangs: a covered nine still borrowed a nearby seven's ink and
  verified `$900.00`. Retain 25 authored covered controls and 11 visible ones;
  all covered claims now require review and nine visible controls verify.
- Retain unavailable attribution when native character geometry cannot be
  established or APIs fail. Bound miter corners using the maximum declared
  page/Form miter limit, including ExtGState ML; unknown limits leave attribution
  unavailable. Stroke bounds include the recorded width and character transform.
  Two visible controls conservatively require review: nearby potential miter
  overlap and an unreadable miter limit. Older rendering-mode and opacity studies
  retain four and 13 visible stroked-claim reviews separately from their original
  authored expectations; their other filled claims remain usable.
- Raise the PDFium requirement from 4.30 to 5.0 for native character-to-object
  association. Keep text, geometry, worker JSON and ordinary example reports;
  bound traversal, pixel work and the association index. Retain independent
  omission renders and minimum-SDK replay in `studies/native-glyph-bounds`.

### Overlapping native PDF text

- Require review when a quoted character's observed paint is confined to
  overlapping native glyph bounds. A covered nine previously borrowed a
  replacement one's pixels and verified `$900.00` on a page displaying `$100.00`.
- Include partially cropped and clipping-risk text as possible pixel lenders.
  Keep text, word boundaries, geometry, worker transport and human correction
  provenance. Bound the overlap audit by glyph count and pixel work; incomplete
  attribution remains unavailable.
- Retain 14 authored PDFs, before/after verdicts and independent PDFium/Poppler
  omission controls in `studies/overlapping-text`. This conservative observation
  can also send legitimate overprinted text to review; it does not establish
  readability or font-to-Unicode correctness. The package release is unchanged.

### Native PDF paint contribution

- Compare each native character's inward-rounded layout region at 144 DPI
  against a disposable reference with native text paint suppressed. Preserve
  text clipping, verify the untouched reference render first, and never edit
  the original document. Missing contribution or incomplete checks require
  review and cannot provide conventions, row anchors or column headings.
- Keep source text, geometry, word segmentation, worker transport and correction
  provenance. Native records with rendering-mode metadata but no audit remain
  unchecked; supplied and recognized OCR words retain their existing behavior.
- Add a concrete Hidden text demo sample: a printed image says $90.00 over a
  native $900.00 claim. Retain 34 authored PDFs, 102 claims, independent renderer
  checks and measured processing costs under `studies/flat-raster`. Regional
  contribution is not proof of readability, character identity or the ownership
  of overlapping native ink. This is unreleased source work.

### Clipped PDF evidence

- Require review when native glyph bounds cross a conservative outer clipping
  bound. Track paths, saved graphics state, transforms, intersections and
  nested Form bounding boxes without discarding the source text or locations.
- Preserve the flag across worker JSON transport and word assembly. Affected
  words cannot establish number/date conventions, row anchors or column roles;
  edit tolerance cannot remove their clipping reason.
- Retain authored PDFs and before/after claims under `studies/clipped-text`.
  This checks outer bounds, not arbitrary pixel visibility: path holes,
  interior curved boundaries, text clipping masks and overpainting remain
  outside its scope. Partly clipped but readable ink can still require review.

### Transparent PDF evidence

- Retain zero-opacity native text through fill/stroke alpha changes, saved
  graphics state, nested Form XObjects and transparency-group composition.
  Inherited text rendering modes also survive Form invocation. Split words
  at opacity changes and preserve the flag across worker JSON transport.
- Require review for quoted zero-opacity words and exclude them from convention
  inference, row anchors and column headers. A fill-and-stroke glyph with one
  remaining nonzero paint channel keeps the existing verification policy.
- Retain 42 authored PDFs, 84 paired claim checks and independent PDFium/Poppler
  pixel controls under `studies/zero-opacity`. This detects explicit zero alpha,
  not general pixel visibility or the accuracy of extraction.

### Unpainted PDF evidence

- Retain each native word's PDF text rendering mode, including inside Form
  XObjects and across the review server's worker boundary. Quotes touching
  invisible (3) or clipping-only (7) text require review with their evidence
  and location preserved; letter-edit tolerance cannot override this.
- Exclude unpainted words from number/date convention inference, row anchors
  and column headers. Painted words elsewhere on the page keep their existing
  verification policy. Existing OCR/caller-supplied words remain compatible.
- Retain 23 authored PDFs and 46 before/after claim checks, independent
  PDFium/Poppler pixel comparisons, installed CLI results and browser
  correction/archive evidence in `studies/unpainted-text`. This does not detect
  every way a PDF can hide text, measure extraction accuracy or release a package.

### Preserve numbers beyond spreadsheet precision

- Store numeric spellings outside a conservative 15-digit, normal-float
  spreadsheet range as literal XLSX text in both Python and browser exports.
  Keep ordinary numeric/boolean/blank types, original values and correction
  provenance. JSON and CSV retain their existing serialization.
- Avoid converting arbitrary Python integers to float during XLSX export;
  large integers no longer round or raise `OverflowError` in the writer.
- Retain constructed native spreadsheet, real API and browser evidence under
  `studies/numeric-xlsx`. Existing review bounds remain; text does not recover
  earlier float/JSON rounding. This is unreleased source work.

### OCR missing-text pages in mixed PDFs

- Add opt-in `--ocr-missing-pages` to `extract` and `verify`, and the library's
  `load_pdf_with_ocr`. Preserve native pages and their word boxes; recognize
  pages without native words, including blanks, with the existing local engine.
- Record attempted page numbers in mixed-document OCR provenance and apply
  word/text budgets to native and recognized text together. Recognition failures
  preserve prior outputs, including in-place verification.
- Keep default loading and all-scanned provenance unchanged. The review server
  retains its native path. Controlled PDFs and actual engine/CLI evidence are
  retained under `studies/mixed-page-ocr`; no recognition-accuracy benchmark,
  package release or deployment is included.

### Refuse claim values without a verification rule

- Validate every present wrapper's actual value before grounding. Objects,
  containers, null, Python dates, Decimal and other unsupported types now raise
  a field-specific `ValueError`; an unrelated quote can no longer verify them
  or make them a row-location hint for another claim.
- Require explicit date/text wrappers to retain string values, including after
  caller mutation. Remove the successful fallback for unhandled value types.
- Keep supported scalar verification and absent optional wrappers unchanged.
  No input conversion or partial report is performed. Containers belong outside
  `Evidenced`; optional absence belongs outside it too (`Evidenced[str] | None`).
- Retain a labelled synthetic PDF and before/after replay through the real
  fixture extractor and verifier under `studies/claim-types`.

### Separate string intent from accidental date-name matches

- Restrict generic string date hints to complete words in the final named
  member. `candidate_name`, `updated_by`, `validate_status` and enclosing
  date-related objects no longer cause unrelated text to fail date validation.
- Add `EvidencedDate` and `EvidencedText` for explicit custom-schema intent,
  including nested containers. Preserve the extraction JSON shape and record
  explicit policy as `declared_kind` in verification reports.
- Use one kind decision for value checking, letter-edit tolerance and date
  conflict explanations. Calendar-invalid and ambiguous dates remain in review;
  explicit date fields never receive text tolerance. Explicit text policy
  does not itself disqualify a field from supplying a row-location hint.
- Retain labelled synthetic PDF controls and real SDK streaming coverage.
  Custom nonconventional date names should use `EvidencedDate` explicitly.

### Keep declared custom-schema containers in verification

- Traverse tuples and string-keyed mappings as well as nested models and lists.
  Previously, valid custom models could hold unsupported claims while their
  verification report contained no fields.
- Quote literal mapping keys and non-identifier model field names in paths,
  preventing a field named `a.b` from overwriting nested field `a.b`.
- Ignore quoted key text when finding positional row hints. A key containing
  `items[0].amount` is not evidence that its claim belongs to a table row.
- Reject non-string mapping keys explicitly. Retain real-PDF before/after
  evidence under `studies/container-claims`; built-in schema selectors are unchanged.

### Keep supplied claims visible at the extraction boundary

- Reject duplicate JSON members with their decoded JSON Pointer, including
  escaped duplicate names. Use the same decoder for fixture files, saved-result
  verification, server uploads and collected Anthropic SDK replies.
- Reject non-finite JSON numbers and unpaired Unicode surrogates before they can
  create unreadable server reports. Preserve valid UTF-8/BOM and BOM-marked
  UTF-16 inputs.
- Forbid unexpected members throughout schema validation, so extra claims and
  misspelled fields cannot be dropped before review. Preserve declared aliases
  and optional defaults. Require Pydantic 2.12 for its per-call extra-field policy.
- Failed reads and validations keep previous CLI files and server review decisions.
  Retain synthetic PDF, real SDK-parser and browser evidence in
  `studies/claim-integrity`; no model API, package release or hosted deployment.
- Keep the Retry button readable beside long import errors on narrow screens.

### Preserve CLI inputs and reports

- Refuse report destinations that identify the source PDF or consumed extraction
  fixture, including normalized paths, parent-directory aliases and hard links.
  Reject output symlinks before PDF or provider work and recheck before writing.
- Replace reports only after a complete, flushed temporary write. A failed write
  preserves the previous report, including `verify`'s intended in-place update,
  removes the temporary file and returns a concise exit-2 error. Report files are
  private (0600 on POSIX).
- Retain actual CLI alias, short-write and unchanged-report checks in
  `studies/report-files`; no hosted or package release is included.

### Portable review archives

- Save a local review as an inspectable ZIP containing the PDF, original claims
  and every saved human decision. Open it after restarting the server without
  an API key or another extraction call.
- Recompute automated verification on restore, keep corrections separate from
  original claims, and create a new session only after validation succeeds.
  Reject malformed, oversized and incompatible archives without evicting work.

### Literal spreadsheet export

- Add XLSX downloads in the review UI and API. Identifiers and formula-like
  strings use text cells; numbers and booleans keep their types. Review scopes,
  corrections and original verification status match JSON/CSV.
- Refuse oversized or unsupported text with a JSON fallback instead of producing
  a partial workbook.

### Explicit table-column evidence

- Flag supported numeric quotes aligned with a different declared table header,
  including quantity/unit-price swaps that preserve multiplication. Retain the
  original quote boxes and separate arithmetic verdicts.
- Add `column_headers` to `RowEvidenceRule` and `report.column_checks`, including
  the server worker's serialized report. Invoice defaults recognize complete
  Description / Qty / Unit price / Amount headers and declared alternatives.
- Keep missing headers, intervening non-table rows, header gaps, and ambiguous
  supporting numbers explicitly unavailable. No semantic or completeness proof
  is inferred. Controlled PDFs and external coverage observations are retained
  in `studies/column-evidence`.

### Scanned-PDF CLI fallback

- Connect `extract` and `verify` to the existing optional local Tesseract loader
  when the PDF has no extractable text. Preserve page numbers and record OCR
  provenance in verification reports, with a CLI warning about recognized text.
- Bound OCR page rendering, text volume and Tesseract runtime; reject empty
  recognition and mismatched explicit page counts without writing a result.
- Retain actual engine/CLI captures and coordinate checks in `studies/ocr-fallback`.
  Native-text PDFs and the review server retain their existing loading policy.

### Conflicting document conventions

- Distinguish missing number/date convention evidence from conflicting evidence.
  Caller defaults now fill only missing evidence; they no longer silently verify
  one reading of an ambiguous quote when the document shows both conventions.
- Keep explicit amounts and unambiguous dates usable, retain the quoted text
  and boxes, and explain the conflict in review reasons. Existing unique-convention
  helper results remain compatible; plural helpers expose all observed conventions.
- Retain controlled PDF and CLI captures in `studies/mixed-conventions`.

### Unicode evidence locations

- Keep original character offsets through Unicode case folding. A dotted capital
  I elsewhere on a page no longer disables case-insensitive matching or lets a
  repeated name become a single verified fuzzy match.
- Retain every caseless occurrence for expansions such as sharp S and dotted I,
  and for Greek sigma variants. Never accept half of an expanded character as
  whole-word evidence; original PDF text and boxes remain the evidence shown.
- Retain ten actual synthetic PDFs and API before/after reports in
  `studies/unicode-grounding`, including four false verified-location repairs.

### Repeated evidence on invoices

- Prepare page text, numeric tokens and source offsets once per verification;
  reuse bounded quote candidate lists while checking each claimed value and row
  independently. A 100-row synthetic invoice that exhausted the review server's
  CPU budget now completes without changing that budget or its report.
- Keep document snapshots local to each verification, preserve page-hint order,
  and retain every occurrence when a candidate list exceeds the reuse limit.
- Retain actual PDF/API/browser reproductions, timings, and an unchanged
  133,722-case receipt replay in `studies/grounding-reuse`.

### Complete written-date evidence

- Reject written dates carved out of longer days, years or identifiers in
  both grounding and value checks. A printed `May 1, 20260` no longer verifies
  `2026-05-01`; the complete quote and highlight remain available for review.
- Share supported written-month parsing, including `Jan. 1, 2026`, `1 Jan. 2026`
  and `May 1 2026`, so value checks accept the spellings grounding recognizes.
- Retain actual PDF and CLI before/after results in `studies/written-dates`.

### Extracted date claims

- Require one calendar-valid `YYYY-MM-DD` value for a date claim. Negated prose,
  alternative dates and ambiguous numeric claims no longer verify because one
  substring matches the evidence. Localized formats remain supported in evidence.
- Leave invoice date ordering explicitly `not_checked` when either extracted
  date fails the contract. Preserve the original claim, quote, page and boxes
  for review; do not normalize or correct the extraction silently.
- Retain before/after actual PDF grounding and CLI captures in `studies/date-claims`.

### Explicit Boolean evidence

- Verify Boolean leaves from a single explicit yes/no or true/false answer,
  optionally after a label and colon/equal sign. Compare the claimed value to
  that answer; preserve case and whitespace normalization.
- Send prose, conditions, choice lists and multiple answers to review.
  A quote saying "approved, not denied" no longer verifies `approved=False`
  because of unrelated negative words. Preserve the claim, source text,
  page and highlight; verification does not silently correct an extracted value.
- [Retain 32 synthetic PDFs and 64 paired claims](studies/boolean-evidence/README.md),
  including explicit-answer controls and both polarities of each ambiguous quote.
  Boolean fields are exposed through custom Python schemas; this change does
  not establish a label's semantic association with a schema field.

### Calendar-valid date evidence

- Require complete, valid calendar dates before inferring day-first or
  month-first order. Impossible dates, identifier fragments and date-shaped
  pieces of phone numbers no longer override a caller's default.
- Use the same numeric-date boundaries in grounding and the parser fallback,
  so rejected fragments cannot silently return as verified date evidence.
- Retain 252 before/after checks through 42 constructed PDFs: 58 unsupported
  verifications and 20 unnecessary reviews become zero on these inputs.
  All 7,600 scripted receipt date claims keep their prior outcomes. The
  [study](studies/date-conventions/README.md) records four changed document
  conventions, a fused-OCR limitation and an existing wrong-location match.

### Item association for unique quotes

- Apply explicit row-evidence rules to invoice and receipt line-item numbers,
  including unique quotes. A number quoted from another item now needs review
  while retaining its real source highlight. Missing, rejected or edited
  descriptions cannot establish the item's row.
- Add `report.row_checks` with `same_line`, `separate` and `unavailable`
  outcomes, both source locations and source-support verdicts captured before
  row/arithmetic checks. These observations do not establish table columns.
- Add `RowEvidenceRule` for custom schemas, with independently grounded named
  anchors regardless of declaration order, validated collection paths and an
  explicit `row_rules=[]` override for independent source checks.
- In a paired replay of the same 2,853 scripted receipt claims, wrong verified
  unique quotes fell from 746 to five; 192 previously correct locations now
  need review. Repeated-quote results stayed unchanged. The
  [study](studies/row-association/README.md) preserves all 19 remaining errors
  and a constructed wrong-column case that still verifies.

### Repeated quotes and row evidence

- Resolve a repeated quote only when exactly one occurrence shares a visual
  line on the same page as a strongly grounded, value-supported sibling.
  Do not borrow the nearest value from another row or page, break column
  ties, or let a rejected/edited description disambiguate another field.
- Unresolved evidence retains an explicit reason and no invented highlight.
  Resolved fields' JSON notes identify the anchor and the limits of the choice.
- Add a synthetic PDF, installed-package review/export coverage and a
  [paired audit of 2,853 scripted claims on 400 CORD receipts](studies/row-locality/README.md).
  Wrong verified locations among repeated quotes fell from 431 to 14;
  197 previously correct locations now need review. This does not establish
  table-column or semantic field correctness, especially for unique quotes.

### Inspectable arithmetic

- Check invoice quantity times unit price against each line amount. Failed
  calculations send all three participating fields to review, with the
  calculation, difference and tolerance visible beside their source quotes.
- Add `report.cross_field_checks`: passed, failed and not-checked rules with
  their operands and exact decimal results. Preserve `cross_field_issues` as
  the failed subset. Missing tax or quantity is not silently zero or one.
- Perform sums, products and inclusive tolerance comparisons in decimal
  arithmetic. Avoid false failures at the two-cent boundary and small amounts
  disappearing when added to large ones; isolate calculations from the
  caller's decimal context.
- Add a synthetic line-arithmetic PDF and a fourth local static demo sample.
  Retain controlled PDF, independent rational-arithmetic, installed-wheel and
  browser evidence in [the arithmetic study](studies/arithmetic-evidence/README.md).
- The audit describes original extracted claims. Review edits remain separate
  and do not recalculate it; unmodelled discounts, units and currency rounding
  can require review even when a transaction is legitimate.

### Numeric evidence and signed amounts

- Preserve leading, Unicode, accounting and trailing minus signs, including
  signs separated from currency symbols. A clipped quote remains weak evidence
  with the full numeric source highlighted; other occurrences remain ambiguous.
- Parse whole supported tokens. Exponents, identifiers, malformed grouping,
  fractions and rates cannot supply smaller numeric fragments. Retain `2x`/`x2`
  quantity notation and support leading decimal points and valid Indian grouping.
- Use printed decimals in numeric comparisons; preserve exact integer inputs,
  reject non-finite claims, and remove the additional floating-point allowance.
- Respect visual row boundaries so a footer dash does not negate the prior total.
- Keep weak-match score text readable in both review themes. Add a synthetic
  credit note and a real PDF upload/review regression.
- Fresh before/after evidence: 44 controlled PDFs, all 133,722 receipt cases,
  and the installed wheel's browser correction/export workflow. The
  [numeric study](studies/numeric-evidence/README.md) records five newly reviewed
  annotated fields and the reference-parser limitations; it is in-sample.

### Grounding and verification, earlier annotated-receipt study

Checked against 1,052 CORD v2 and SROIE receipts (`studies/cord-grounding`), with what a
model returns imitated by rule. In 0.2.7 a total one cent off was `verified` in 42% of
cases and a name with one letter changed in 78%; an amount written `60.000` was read as
sixty, so a total a thousand times too small was `verified` 382 times in 408; and dates
written `23-01-2019` were not read. The rules below reject those by construction, and
they also send to review every name in which a model has repaired an OCR misread
(0.2.7 verified 83% of those). They were written with these receipts in view.

- `verify(..., text_edit_tolerance=n)`, off by default: a text field of twelve letters or
  more may differ from the page by up to `n` letters and stay `verified`, with what
  differed in the field's `notes`.
- `verify(..., default_number_style=, default_date_order=)` and the CLI's `--number-style`
  and `--date-order` say how to read a number (`"decimal"`, `"thousands"`) or a numeric
  date (`"dmy"`, `"mdy"`) that the document itself does not settle. On these receipts
  they take amounts verified at the right place from 79% to 95% and dates from 63% to
  98%. A document that settles the question is read its own way whatever they say.

- A string value must be a run of the evidence's words, ignoring case, spacing and
  punctuation; a value that differs in a letter or digit is `needs_review`.
- A fuzzy match is strong only if its letters and digits agree with the page (a
  separator between digits and a leading minus count). `GroundingMatch` gains
  `letters_agree` and `by_value`.
- A quote that is only a number or a date is found by value (`60000` at `60.000`,
  `2018-12-25` at `25/12/2018`); a quote that differs only in case is found at every
  place the page has it. New module `fieldproof.ground.values`.
- Numbers are compared to the precision the page wrote (`9.00` does not support `9.01`;
  `NUMBER_TOLERANCE` is half a cent, was a whole one). `60.000` is sixty or sixty
  thousand: it is read the way the document's other numbers settle
  (`check_number(..., number_style=)`), and where they settle nothing neither reading is
  verified and the field is `needs_review` with the two readings given.
- Numeric dates written with `-` or `.` and two-digit years are read.
- A minus sign is no longer treated as punctuation that a quote may leave out.

### Review workbench

- Corrections of nested fields save correctly and retain numbers and booleans.
  Approval and rejection retain the correction; Reset restores the original.
  Invalid corrections leave the decision unchanged and the editor available.
- Sample/PDF loads and extraction replies belong to the operation that started
  them. Cancellation and replacement discard stale replies; failed replacement
  keeps the previous valid document. Late review replies stay with their document.
- Review progress and decision filters separate human review from automated
  verification. Exports default to reviewed fields, with an explicit option to
  include pending fields. Downloads snapshot the displayed decisions and wait
  for pending saves. Exports add `original_value` and `value_source` columns so a
  human correction cannot be mistaken for the originally verified value.
- Demo decisions remain available in the tab when browser storage is blocked;
  invalid stored overlays are discarded. Sample/index/page-image errors offer
  recovery. Keyboard focus survives selection, review, filtering and editing;
  320px layouts use separate Fields/Document views, retain correction drafts,
  expand filters on demand and fit the document without clipping it.
- A source checkout serves its fresh web build before an older packaged copy.
  Production Chromium/Firefox coverage now exercises the static demo and the
  real local fixture API, alongside review/export contract tests in CI.
- Local document sessions can be reopened after a tab reload and removed with
  explicit confirmation. Capacity refusal preserves stored decisions; a
  correction draft blocks navigation until saved or cancelled.
- PDF intake, geometry, extracted text and retained sessions have explicit
  budgets. Parsing, rendering and verification run in disposable processes with time/resource
  limits; oversized fixtures, field lists and correction totals are refused
  without replacing a valid review. Concurrent intake and PDF queues are bounded.
- Cropped and rotated PDFs use the rendered visible canvas for text/evidence
  coordinates, including shifted MediaBox origins. Text outside that canvas is
  excluded; glyph baseline directions retain logical words and decimal numbers.
  Fractional page pixel sizes use the renderer's ceiling.

### Maintenance

- The uv lock now resolves stable httpx 0.28.1 and Pydantic 2.13.5 instead of
  development/beta versions selected by a permissive local resolver setting. The
  project explicitly prefers stable releases.
- The web toolchain uses ESLint 10 with compatible TypeScript lint packages;
  existing configured rules are retained.

## [0.2.7] - 2026-10-03

### Compatibility

- Python 3.13 and 3.14 are tested and declared. CI runs the suite on 3.14
  as well, and the package's classifiers list both versions. The code is
  unchanged: with the newest release of every dependency, the tests pass on
  3.14 and on 3.15's release candidate.

## [0.2.6] - 2026-10-02

### Accessibility

- The review UI, checked with axe-core (WCAG 2.1 A and AA, and its best-practice rules) in light and dark,
  at desktop and phone widths, on each sample
  document: no findings now. The faint text was 2.6:1 to 3.1:1 (light) and
  3.4:1 (dark), and the "review" and "verified" labels just under 4.5:1 on
  their tints. The page has an `h1`, and the page viewer, which scrolls, can
  take keyboard focus.

## [0.2.5] - 2026-10-02

### Security

- The review UI carries a Content-Security-Policy. Scripts, styles and fonts
  load from the server that served the page only, and `connect-src 'self'`
  has the browser refuse to send a document, or anything read from it, to
  any other host, even for a script injected through a bug in how a field
  is rendered. Inline event handlers and `eval` are not allowed. Checked in
  Chromium and Firefox with a listener for policy violations, on the demo and
  on `fieldproof serve` through an upload, an extraction and the page images:
  none.

## [0.2.4] - 2026-10-02

### Changed

- The review UI's fonts ship in the package. `fieldproof serve` runs on your
  own machine, over documents you may not be free to share, and its page
  asked Google Fonts for its typography on every load (and fell back to
  system fonts without a connection). The same font files are now part of
  the wheel, with their SIL Open Font License texts (`web/src/fonts/`), and
  the page makes no request to any host but the server it came from. Nothing
  looks different: screenshots before and after match. The wheel grows from
  about 60 KB to about 530 KB.

## [0.2.3] - 2026-10-02

### Security

- The oldest dependency versions the package accepted had published
  advisories in exactly the code that reads what a stranger uploads:
  `python-multipart` 0.0.9, `starlette` 0.38.6 (through `fastapi` 0.115),
  `pdfminer.six` 20231228 (through `pdfplumber` 0.11.0) and `Pillow` 10.4
  (the `ocr` extra), plus `click` 8.1.8. An ordinary install already got
  current versions; an install held back by another package's constraints
  could get those. The minimums are now the first releases without an
  advisory: `python-multipart>=0.0.31`, `starlette>=1.3.1`,
  `pdfminer.six>=20251230`, `click>=8.3.3`, `Pillow>=12.3`, and with them
  `fastapi>=0.133`, `pdfplumber>=0.11.9`, `typer>=0.16`. `pip-audit` reports
  nothing for the locked versions or for the minimum ones, and the tests pass
  on both.

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
