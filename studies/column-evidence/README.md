# A passing calculation can hide swapped columns

The [constructed invoice](../../examples/column-evidence.pdf) prints Delivery,
quantity `3`, unit price `12.50`, and amount `37.50`. Its
[fixture](../../examples/fixtures/column-evidence.json) swaps quantity and unit
price. Baseline `4cb9624` verifies both: each quote exists on the right item line,
and `12.50 * 3` still equals `37.50`.

The column observation now sends both fields to review. It keeps the original
quote boxes and the passing arithmetic ledger. It never rewrites the extracted
values. The example is synthetic, not a transaction or a model's output.

## What qualifies as column evidence

Invoice defaults recognize these labels, ignoring case and whitespace:

| Field | Header alternatives |
| --- | --- |
| description | Description, Item description |
| quantity | Qty, Quantity |
| unit_price | Unit price |
| amount | Amount, Line total |

All four headers must occur once on one visual line, without additional words,
with non-overlapping horizontal boxes. A multiword label cannot jump a gap
larger than twice the smaller word height. Columns may occur in any order.

The closest complete header above the item on the same page applies only
through contiguous complete data rows. Each intervening row must contain text
under the description header and numeric text under every numeric header.
Prose, totals, sparse rows and wrapped rows break that connection. Headers
never carry across pages. Layout is cached only within one verification call.

Horizontal alignment means overlap of at least half the narrower box's width
with exactly one header. The rule does **not** invent cell boundaries between
headers. Source words must have finite, nonempty boxes; unusable page geometry
makes its column evidence unavailable. Numeric token support uses the existing
number convention and precision checks. Whole-row quotes work when all tokens
supporting the claimed value align with the same column. Equal supporting
numbers in different columns remain ambiguous.

`report.column_checks` adds one observation per declared numeric member:

| Status | Observation | Effect on the field |
| --- | --- | --- |
| aligned | Supporting numeric tokens align with the expected header | No upgrade or independent semantic proof |
| contradictory | Supporting numeric tokens align with a different configured header | Otherwise verified field requires review |
| unavailable | Missing/ambiguous headers, quote support, geometry, or table connection | No change to the existing verdict |

Each entry includes the field path, reason, observed column when available,
header labels and their page/text/character offsets/rectangles, and supporting
number locations. Unavailable checks retain locations when the header was
established but the number's column was unresolved. The existing review UI shows
contradiction reasons and the original evidence highlight. Human corrections
remain separate from the original report and its arithmetic/row/column ledgers.

Custom schemas declare their own exact labels in a `RowEvidenceRule`:

```python
from fieldproof.verify import RowEvidenceRule, verify

report = verify(data, document, row_rules=[
    RowEvidenceRule(
        "items", "description", ("quantity", "price"),
        column_headers={
            "description": ("Product",),
            "quantity": ("Units",),
            "price": ("Unit price",),
        },
    ),
])
```

The mapping must name the anchor and every member of the row rule. Aliases must
be nonempty and distinct. Fields still need their usual `Evidenced` wrappers;
column observations currently apply only to numeric members. Custom schemas
and receipts do not acquire column rules implicitly. `row_rules=[]` disables
both row and column constraints; omitting `column_headers` keeps row checks
without column observations.

## Controlled evidence and coverage

[run.py](run.py) draws 308 native PDFs and constructs claims from the drawing
instructions. It exercises all 24 column orders, three text alignments,
correct/swapped assignments, token/whole-row quotes, aliases, upper-case labels,
missing/duplicate/ambiguous headers, a header on another page, intervening prose,
header gaps and repeated equal numbers. No model or OCR runs.

| Controlled result | Baseline | Current |
| --- | ---: | ---: |
| Wrongly verified numeric fields in recognized swapped layouts | 292 | 0 |
| Those fields sent to review | 0 | 292 |
| Field verdicts changed outside those swaps | 0 | 0 |
| Item source locations retained unchanged | 1,232 | 1,232 |
| Arithmetic ledgers retained unchanged | 308 | 308 |

The 924 current column observations comprise 586 aligned, 292 contradictory,
and 46 unavailable. These counts include related layout variations and are
**not independent real-world accuracy samples**. The unavailable layouts retain
their prior source verdicts, including unsupported column assignments.
[Paired results](results/comparison.json), [baseline cases](results/before-cases.json),
[current cases](results/current-cases.json), and four complete report pairs are
retained. The comparison requires identical PDF and extraction hashes, source
text/boxes, and arithmetic hashes before counting changed verdicts.

A separate [coverage probe](coverage.py) loads all 11 PDFs in invoice2data's
`tests/compare` at commit `09378126e3ae86ddef5435ba166b4fc026e386a4`.
**Zero have a complete header recognized by these defaults.** For example,
AzureInterior has extra discount/tax columns, and other files use different
labels or omit quantity. [Source hashes and observations](results/external-coverage.json)
are retained. This is a header-recognition probe using this implementation,
not an independent correctness oracle, extraction benchmark, or evidence that
those invoices were verified. No source PDF or customer information is copied
into this repository. The upstream project is
[invoice2data](https://github.com/invoice-x/invoice2data/tree/09378126e3ae86ddef5435ba166b4fc026e386a4),
MIT, copyright 2015 Manuel Riel.

## Limits

This is a narrow contradiction check, not table extraction. It does not establish
item completeness or semantic correctness. It cannot catch a swap without
usable configured headers, infer columns from whitespace, resolve repeated
identical numbers, handle arbitrary extra columns, or carry headers over wrapped
or interrupted rows. OCR can supply incorrect text or boxes. Identical table
geometry can still describe different semantics. Absence of a contradiction
is not proof that the assignment is correct. The earlier
[row-association study](../row-association/README.md) has no headers on its known
wrong-column control; that case remains unresolved by this addition.

## Reproduce

From the source checkout with development dependencies installed:

```bash
fieldproof extract examples/column-evidence.pdf --schema invoice --provider fixture \
  --fixture examples/fixtures/column-evidence.json --out column-result.json
fieldproof verify column-result.json examples/column-evidence.pdf --out column-verified.json
uv run --locked --extra dev python -I studies/column-evidence/run.py --src src --out /tmp/column-current
```

Extract baseline source using `git archive 4cb9624 src`. Run the same study with
`--src` pointing to that extracted source and `--observe-only`, then run
`compare.py BEFORE/cases.json AFTER/cases.json OUTPUT.json`. Omit `--src` to run
against a separately installed wheel; the study asserts its package import
comes from that interpreter's environment.

For an installed server on port 4300, run
`web/node_modules/.bin/playwright test --config studies/column-evidence/browser.config.mjs`.
`FIELDPROOF_BROWSER_URL` overrides the URL. `FIELDPROOF_BROWSER_FULL=1` also
runs the existing live/static-demo suite (demo defaults to port 4301).
`UPDATE_COLUMN_SCREENSHOTS=1` saves the actual review screenshots and exported
corrections. `FIELDPROOF_COLUMN_BASELINE=1` observes the old verdicts against the
baseline server using the same new PDF/fixture.
