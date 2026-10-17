# fieldproof

**Review extracted document fields against the words and locations that support them.**

[![PyPI](https://img.shields.io/pypi/v/fieldproof)](https://pypi.org/project/fieldproof/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-antonsoo.github.io%2Ffieldproof-14524c)](https://antonsoo.github.io/fieldproof/)

An invoice extractor can quote the right words and still return the wrong total,
borrow another item's quantity, or cite text hidden beneath the visible page.
Fieldproof keeps each value with its evidence, locates the quoted words, checks
the value and related fields, and opens the remaining questions for review.
Human corrections retain the original extraction and automated verdict.

![Reviewing a hallucinated PO number and an inconsistent invoice total](docs/assets/hero-review.png)

## Try the review workflow

The **[live demo](https://antonsoo.github.io/fieldproof/)** contains five authored
sample documents with deliberately planted extraction errors. Choose
[Arithmetic](https://antonsoo.github.io/fieldproof/#line-arithmetic) to inspect
`3 x 19.95` against a printed `39.90`, or
[Hidden text](https://antonsoo.github.io/fieldproof/#hidden-text) to compare an
image printing `$90.00` with a native text layer claiming `$900.00`.

Inspect a field, approve, edit or reject it, then download JSON, CSV or XLSX.
The demo uses precomputed Python reports and page images. It does not upload
or process your documents. Decisions persist in browser storage when available;
otherwise they remain in the tab. Phone layouts separate Fields and Document
views, and the loaded review works offline.

## Quickstart

This repository contains verification corrections beyond **PyPI 0.2.7**. To
process a PDF with the current source and its local review UI, install
[uv](https://docs.astral.sh/uv/) and Node 24 or later, then:

```bash
git clone --depth 1 https://github.com/antonsoo/fieldproof && cd fieldproof
uv sync --locked
uv run python scripts/bundle_ui.py && uv run fieldproof serve
```

Open `http://127.0.0.1:8000`. Upload `examples/invoice.pdf`, choose **Fixture**,
and supply `examples/fixtures/invoice.json`. This replays an extraction without
an API key. The fixture path and review UI run locally. Choosing the Anthropic
provider sends document content to that provider; the review UI itself makes
no off-origin requests.

For only the tested CLI/library correction, including replacement of an existing
0.2.7 installation, use the pinned source:

```bash
python -m pip install --force-reinstall "fieldproof @ git+https://github.com/antonsoo/fieldproof.git@05ac81a33215bc858d125f291d1467244fb56dde"
```

A direct Git install has **no bundled UI**. The checkout command above builds
it. `pip install fieldproof` installs the older registry verifier with its
bundled UI; neither a matching version number nor a deployed static demo
establishes that the native source correction is installed.

From the checkout, reproduce the sample through the CLI:

```bash
uv run fieldproof extract examples/invoice.pdf --schema invoice --provider fixture \
  --fixture examples/fixtures/invoice.json --out result.json
uv run fieldproof verify result.json examples/invoice.pdf
```

## What a verdict means

| Automated verdict | Meaning |
| --- | --- |
| `verified` | Located evidence passed the configured support and cross-field checks. |
| `needs_review` | Located evidence is weak, ambiguous, incompatible with the value, or fails another check. |
| `unsupported` | No usable evidence quote was located for the claim. |

These verdicts describe the verifier's evidence, not the truth of a document or
the accuracy of an extraction model. Human decisions are separate: approving
or editing a value does not rerun its original automated checks.

Reviewed-only export includes approved and edited fields. **All except rejected**
also includes pending fields. Both omit rejected values and retain each exported
field's original value, correction provenance and verification status. **Save
archive** retains the PDF, original claims and all saved decisions so work can
resume after a server restart. Archives are explicit, unencrypted saves;
in-memory sessions alone are not durable.

See [review decisions, spreadsheet types and archive recovery](docs/usage.md#review-decisions-and-exports).

## What gets checked

- **Quotes and values.** Whole-word alignment, repeated-quote ambiguity, printed
  signs and units, numeric precision, calendar-valid dates and document-wide
  formatting conventions. Conflicting JSON members or discarded claim fields
  are input errors.
- **Related fields.** Line-item quantities and prices, subtotal/tax/total
  arithmetic, date ordering, row association and narrowly supported labelled
  table-column contradictions. Unavailable checks stay distinct from passing
  ones.
- **Native PDF evidence.** Invisible and transparent text, outer clipping bounds
  and a bounded raster comparison. Another glyph's overlapping ink cannot by
  itself certify a covered character. Failed native associations remain
  unavailable.
- **Review provenance.** Source locations remain inspectable after corrections,
  exports and archive restoration. Bounded processing workers preserve existing
  sessions when new work cannot be accepted.

Built-in schemas cover invoices, receipts and contract terms. Providers include
Anthropic and stored fixtures. Optional Tesseract OCR is available to the CLI
and library; the review server currently requires a native text layer.

### Bring your own schema

Use Pydantic fields of `Evidenced[T]` and the same verifier. Optional row and
column rules state relationships the schema expects. See the
[custom-schema example](docs/usage.md#bring-your-own-schema),
[library example](docs/usage.md#as-a-library) and
[extractor protocol](docs/usage.md#bring-your-own-extractor).

## Evidence and remaining costs

The [CORD/SROIE study](studies/cord-grounding/README.md) uses 1,052 real receipts
with supplied OCR and field ground truth. It measures grounding and deliberately
mutated claims, without calling a model. Stricter matching rejects all 2,251
one-letter name mutations in that retained study, while also sending
OCR-repaired names to review. These receipts informed the rules, so the result
is not an out-of-sample extraction benchmark.

The [native glyph-bounds study](studies/native-glyph-bounds/README.md) retains an
actual false verification: an italic seven lends ink outside its advance box
to a covered nine in `$900.00`. All 25 authored covered controls now require
review, supported by 72 independent PDFium/Poppler omission comparisons.
Nine visible controls verify; two conservatively require review. Existing
visible stroked claims can also require additional reviews. These synthetic
controls do not measure production prevalence.

The [evidence guide](docs/evidence-guide.md) maps individual claims to retained
inputs, before/after reports, independent controls and installed/browser
receipts. Each study identifies its source and publication boundaries.

The local [Arabic-number correction](studies/arabic-numbers/README.md) addresses
another false verification: a printed `١٬٢٣٤٫٥٦` supported a claim of `234`.
Complete amounts now retain their separators, and percentage signs cannot
disappear into plain amounts. The study includes native locale formatting and
the actual PDF review workflow. This correction is not in the pinned public
install above, a registry release or the hosted demo.

The [spacing correction](studies/spaced-numbers/README.md) prevents `1 234,56`
from verifying its tail as 234.56. It preserves uncertain grouped values for
review and uses layout to retain clearly separated quantity/price cells.

## How it works

```text
PDF -> words + locations -> extracted values + quotes -> grounding + checks
                                                          |
                                              original report + human review
                                                          |
                                               value exports / review archive
```

The loader retains source text and geometry. Grounding associates quotes with
candidate words; verification compares the claimed values with the evidence
and applicable relationships. The UI renders the original page with highlights
and keeps corrections separate. See [design and architecture](docs/design.md).

## Accuracy and limitations

A positive raster difference does not prove readability, font-to-Unicode
correctness or exact ownership of overlapping ink. Stroke bounds can be
conservative. Native attribution requires PDFium 5.0 or later and has explicit
work budgets; incomplete observations require review. Caller-supplied and
recognized OCR text have different provenance and do not receive this native
paint audit.

OCR mistakes, wrapped or skewed tables, unclear number/date conventions and
legitimate discounts can all need human interpretation. Nothing checks that a
document is authentic. A saved correction is a decision, not newly verified
evidence. See the [full limitations](docs/design.md#accuracy-and-limitations)
and [document/session limits](docs/usage.md#document-sessions-and-limits).

## Development

[Development and packaging](docs/development.md) covers Python/web checks,
production browser workflows, UI bundling and static-demo regeneration. The
tests use stored fixtures and local API servers; no live model call is needed.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests welcome.

## License

[MIT](LICENSE), Copyright (c) 2026 Anton Soloviev.
