# Arithmetic evidence, 2026-10-09

Every value on a PDF can be quoted correctly while the values disagree with
each other. Before this change, a line saying quantity `3`, unit price `19.95`
and amount `39.90` passed verification when the subtotal and tax added up.
The earlier checker also used binary floats at an inclusive two-cent boundary
and could lose a small tax when adding it to a very large subtotal.

These are deliberately constructed documents and arithmetic cases. They are
not real transactions, LLM outputs, or an estimate of invoice accuracy. No
external provider was called. The controls informed the implementation.

## What changed in the replay

Baseline: checkout `e92cf6f`. Current: implementation hashes in the retained
JSON files. Both were run with Python 3.12.12 in the same environment.

| Check | Before | Current |
| --- | --- | --- |
| Quoted `3 x 19.95`, printed amount `39.90` | 10 verified, no review | 7 verified, 3 review |
| Invoice sum `1`, subtotal `1.02` | 2 fields sent to review | Within inclusive tolerance |
| Receipt sum `0.2 + 0.8`, subtotal `1.02` | 3 fields sent to review | Within inclusive tolerance |
| Subtotal `10000000000000000`, tax `1`, unchanged total | No arithmetic issue | Exact difference `-1`; 3 fields reviewed |
| Product with a printed but unmodelled discount | No arithmetic issue | 3 fields reviewed; adjustment caveat retained |
| Remaining 8 PDF controls | Expected field verdicts | Expected field verdicts plus calculation records |

The discount case is an intentional limitation: a legitimate adjustment can
explain the mismatch, but the schema has no discount field. It is **not** a
known fraudulent or incorrect invoice. Missing unit price and absent totals
produce `not_checked`, while zero, signed and fractional inputs are calculated.
The cancellation control already failed correctly on baseline Python 3.12;
we do not count it as a newly detected defect there.

[`cases.py`](cases.py) defines all 13 controls. [`run.py`](run.py) generates
native-text PDFs, validates the fixture claims, loads the actual PDFs and
runs the full grounding/verifier. Results retain field reasons, locations,
counts and PDF hashes: [`before.json`](results/before.json),
[`after.json`](results/after.json). Regeneration writes the PDFs and fixtures
beside the report, rather than committing another set of generated documents.
The more readable review example is committed under
[`examples/line-arithmetic.pdf`](../../examples/line-arithmetic.pdf), with its
[fixture](../../examples/fixtures/line-arithmetic.json) and
[generator](review_example.py). Its actual CLI outputs are retained as
[`cli-before.json`](results/cli-before.json) and
[`cli-after.json`](results/cli-after.json).

## Independent arithmetic oracle

`fractions.Fraction` checks 2,400 line products, 1,200 item sums and 1,200
subtotal-plus-tax calculations. It operates on the actual validated claim
strings and never imports the checker's decimal calculation helper. It
compares the exact result, signed difference and inclusive `1/50` tolerance.
Quantities include eighths and negatives; observed amounts include boundary
offsets; sum cases include cancellation and widely separated magnitudes.

| Rule | Cases | Baseline disagreements | Current disagreements |
| --- | ---: | ---: | ---: |
| Line product | 2,400 | 1,028 | 0 |
| Item sum | 1,200 | 121 | 0 |
| Subtotal plus tax | 1,200 | 473 | 0 |
| Total | 4,800 | 1,622 | 0 |

The oracle expects 2,245 failures and 2,555 passes. Baseline disagreements
include the previously absent product rule; they are not all regressions in
the old summation rule. The current replay also has zero disagreements and
all 13 expected PDF outcomes on Python [3.11.13](results/python311.json),
[3.14.7](results/python314.json), and a freshly installed
[wheel on 3.12.12](results/installed.json). `oracle.seconds` includes model
construction and extra audit assertions in the current implementation;
it is not an equal-work performance comparison.

## Cost of a document

[`measure.py`](measure.py) separately measures the same work in each checkout:
one warm-up, then nine batches of ten documents. These are median milliseconds
per document on this 14-vCPU WSL2 Linux / 48-GB workstation, Python 3.12.12.
Other work can affect timings; this small run does not establish a speedup.

| Document and operation | Before, ms | Current, ms |
| --- | ---: | ---: |
| Existing invoice, verify parsed PDF | 13.51 | 12.18 |
| Existing invoice, load and verify | 27.40 | 26.32 |
| Arithmetic invoice, verify parsed PDF | 4.11 | 3.98 |
| Arithmetic invoice, load and verify | 14.05 | 14.12 |

The tradeoff visible here is report size: the existing invoice's JSON report
grows from 7,157 to 10,422 bytes, and the arithmetic example from 2,610 to 4,768
bytes, to retain calculations rather than just failures. Raw observations are
in [`measure-before.json`](results/measure-before.json) and
[`measure-after.json`](results/measure-after.json).

## Reproduce

From the repository root, with `uv` installed:

```bash
uv sync --locked --extra dev --extra ocr
mkdir -p /tmp/claude-1000/fieldproof-arithmetic/before
git archive e92cf6f src | tar -x -C /tmp/claude-1000/fieldproof-arithmetic/before
uv run --locked --extra dev --extra ocr python -I studies/arithmetic-evidence/run.py \
  --src /tmp/claude-1000/fieldproof-arithmetic/before/src \
  --out /tmp/claude-1000/fieldproof-arithmetic/before-replay --observe-only
uv run --locked --extra dev --extra ocr python -I studies/arithmetic-evidence/run.py \
  --src src --out /tmp/claude-1000/fieldproof-arithmetic/replay
uv run --locked --extra dev --extra ocr python -I studies/arithmetic-evidence/measure.py \
  --src src --out /tmp/claude-1000/fieldproof-arithmetic/measurement.json
```

`--observe-only` preserves baseline observations without requiring the new
behavior. Without it, any unexpected field verdict, rational comparison or
exact calculation mismatch fails the replay.

The static demo is built from real verification reports:

```bash
uv run --locked --extra dev python scripts/build_demo_data.py
npm --prefix web ci
npm --prefix web run build:demo
npm --prefix web run preview -- --mode demo --outDir dist-demo --port 4296
```

Open `/fieldproof/#line-arithmetic` on that local server. The output is
`web/dist-demo/`; nothing was deployed. The Arithmetic selector, PDF highlight,
three warnings, saved correction and JSON download are exercised in Chromium
and Firefox. Desktop, 375-pixel and 320-pixel layouts are checked. Screenshots
are in [`docs/assets/arithmetic`](../../docs/assets/arithmetic), and actual
corrected rows are retained in the two `*-observations.json` files there.

To exercise the installed wheel, build with `python scripts/bundle_ui.py` in
the development environment and `uv build`, install that wheel into a fresh
venv, and start its `fieldproof serve --host 127.0.0.1 --port 4297` from outside
the checkout. Then, in the checkout:

```bash
web/node_modules/.bin/playwright test \
  --config studies/arithmetic-evidence/installed-browser.config.mjs
```

That config starts no source server: both browsers upload the real PDF and
fixture to the separately running wheel, inspect the calculation returned
through its worker, correct quantity, and download the actual reviewed JSON.
Report calculations must still describe the original claims after a correction.
See [verification details](../../docs/verification-arithmetic-2026-10-09.md)
and [rule limitations](../../docs/arithmetic-checks.md).
