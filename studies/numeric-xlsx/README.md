# Numeric evidence must survive spreadsheet import

At source `91736cf`, the Python writer serializes every finite scalar number as
a numeric XLSX cell. Actual LibreOffice Calc 7.4.7.2 reads integer
`9007199254740993` as `9007199254740992`; three other constructed integers also
change. A direct writer call with `10**400 + 1` raises `OverflowError` while
checking finiteness through float conversion. The review API already rejects
that last correction within its existing bounds; this is a writer failure,
not an observed API 500.

The source correction uses literal text cells outside a conservative numeric
range shared by both writers. Numeric cells require absolute value below
`10**15`, at most 15 significant decimal digits in the current float spelling,
and zero or at least the smallest normal binary64 magnitude. Large Python
integers are inspected without conversion to float. Numbers outside that
range retain their canonical current spelling as inline text; booleans and
blank cells keep their types. This deliberately includes some numbers Calc
can store exactly, so the workbook does not depend on one application's wider
numeric range. Non-finite values still refuse export.

[Microsoft documents Excel's 15-digit precision limit](https://support.microsoft.com/en-us/excel/keeping-leading-zeros-and-large-numbers).
The browser's input is already a JavaScript Number: text fallback cannot undo
earlier rounding. Python-only integer cases therefore do not pretend to test
exact browser values. Python and JavaScript can also spell equal float values
differently (for example exponent padding); each writer retains its current
canonical scalar spelling. JSON/CSV serialization and review validation are
unchanged. Text cells are intentionally no longer directly usable as numeric
spreadsheet operands without an explicit conversion.

## Real Python writer and API

```sh
uv run --locked --extra dev python studies/numeric-xlsx/generate.py \
  --out /tmp/numeric-xlsx --label source
```

[`cases.json`](cases.json) contains 22 constructed scalar cases, five of them
Python-only integers. The driver exercises the actual writer, then uploads the
bundled synthetic PDF, runs its fixture extraction, edits `total`, and downloads
both reviewed/all export scopes. It checks the original automated report is
unchanged and every row retains correction provenance. No model or external
extraction service is used.

The actual baseline disagrees with the preservation policy in **34 of 58
writer/API workflows**; the corrected writer disagrees in none. These are
policy/type comparisons, not 34 observed rounding events in Calc. Its four
changed integer values and the separate writer exception are the independent
consumer counterexamples. Ordinary numbers, boolean and blank controls retain
their types. The existing oversized API correction remains a 422.

For the baseline, use a separately archived `91736cf` checkout on `PYTHONPATH`
and add `--observe-only`. The driver needs the package's server/dev dependencies.
An installed wheel can run the same driver with `--fixture-root` pointing to
the repository's examples; its runtime module digest is recorded.

## Browser writer

```sh
# Node 24, after npm ci --prefix web:
node studies/numeric-xlsx/generate-browser.mjs . /tmp/numeric-browser source
```

This directly imports the same TypeScript writer shipped in the app, using
17 Number/text/boolean/blank cases. The baseline has seven policy disagreements;
the correction has none. The shared ordinary scalar controls are unchanged.
Actual browser downloads and native-reader verification are recorded with the
completed verification artifacts below.
