# A grouping space must not certify the tail of an amount

An authored PDF printing `Total 1 234,56` verified a claim of **234.56** in
`d94f2f4`. French narrow non-breaking spaces and Russian/Swedish non-breaking
spaces have the same failure after the PDF loader joins words with single spaces.
The correct formatter input was 1234.56. These are controlled native-text PDFs,
not real invoices or an OCR/model accuracy measurement.

The correction keeps adjacent numeric groups as one unresolved source span.
Neither a component nor a guessed combined amount can verify from uncertain
spacing. Clipped quotes retain the whole span and its boxes for review. A
separate supported number elsewhere in the quote remains usable.

Layout restores row boundaries and separates adjacent numeric groups when their
horizontal gap is at least 1.5 times the taller word's height. Smaller gaps stay
unresolved. This is an explicit geometry heuristic; it does not identify semantic
column roles, prove a locale, or recover missing PDF whitespace characters. A
wide gap between a sign and its amount does not detach the sign. Invalid or absent
boxes cannot establish a cell boundary. OCR boxes can be inaccurate.

The paired last two pages of [`numbers.pdf`](fixtures/numbers.pdf) have identical
extracted row text, `Fuel surcharge 1 210.50 210.50`, with wide and tight cells.
Quantity 1 verifies in the wide layout and requires review in the tight layout.
The separate final price 210.50 remains supported in both. Neither layout can
verify an invented merged value of 1210.50. Plain string callers can retain actual
cell boundaries with tabs or newlines; a single-space string cannot establish them.

[`generate.mjs`](generate.mjs) captures native `Intl.NumberFormat` parts and their
original decimal inputs for French, Russian and Swedish. [`intl.json`](intl.json)
retains that capture. The specification distinguishes localized decimal and
grouping symbols ([Unicode LDML Numbers](https://unicode.org/reports/tr35/tr35-numbers.html));
the [CIPM recommendation on decimal markers](https://www.bipm.org/en/-/committees/ci/cipm/92-2003/resolution-2)
also allows spaces between groups of three. Those rules establish why a space can
belong to a number; they do not tell the verifier whether arbitrary PDF cells do.

[`cases.json`](cases.json) also includes authored ASCII/multiple-space, accounting,
irregular-group and rate controls. [`run.py`](run.py) loads the actual PDF and
verifies each page as an independent control, retaining source hashes, verdicts,
reasons and rectangles. A page hint is not used to bypass duplicate evidence
elsewhere in a document.

| Controlled claims | Before | After |
|---|---:|---:|
| Unsupported fragments/uncertain tight quantities approved | 39 | 0 |
| Supported ungrouped values and clear cells approved | 7 / 7 | 7 / 7 |
| Whole space-grouped values retained for review | 15 / 15 | 15 / 15 |

The 131 claims use 22 byte-identical PDF pages. Full ledgers are
[before](results/before.json) and [after](results/after.json). The baseline is an
independently installed wheel with the numeric sources from `760a1d7` (also the
sources in `d94f2f4`). This correction is source work; no registry release or
hosted deployment is implied. Installed/API/browser and receipt compatibility
evidence will be recorded separately after verification.

Replay from a checkout with locked development dependencies:

```sh
uv run --locked python -I studies/spaced-numbers/run.py --src src --out /tmp/spaced-after.json
```

Omit `--src` and use the intended environment's Python with `-I` to measure an
installed wheel. `--observe-only` retains old verdicts without asserting that
they match the new policy. `--summary-only` fingerprints the full claim ledger.
The committed PDFs need no local font installation; regeneration uses
`node studies/spaced-numbers/generate.mjs` then
`uv run --locked python studies/spaced-numbers/make_fixtures.py --font /path/to/DejaVuSans.ttf`.
The embedded font's license is retained in
[`../arabic-numbers/FONT-LICENSE.txt`](../arabic-numbers/FONT-LICENSE.txt).
