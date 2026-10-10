# Explicit Boolean answers and misleading prose

At `79c3061`, an extracted `approved=False` was **verified** against each of
these actual PDF quotes:

| Printed statement | Old result for `approved=False` | Source checkout |
| --- | --- | --- |
| The request is approved, not denied. | Verified | Needs review |
| No changes: approval confirmed. | Verified | Needs review |
| Approval was denied previously, but is confirmed today. | Verified | Needs review |
| Approval: yes | Needs review | Needs review |
| Approval: no | Verified | Verified |

The old checker collected positive and negative words. For a false claim, any
negative word was enough, regardless of what it negated or whether it described
a previous state. Grounding correctly found the quote; the value check then
gave it the wrong meaning.

`1b87206` verifies a Boolean only from a single explicit answer: `yes`, `no`,
`true` or `false`, case-insensitive, with an optional final period. An optional
label is separated by `:` or `=`. Examples: `Approval: YES`, `Renewal = false`.
Labels can contain word characters, spaces, parentheses, slash, ampersand,
comma, apostrophe and hyphen; a label containing another complete yes/no/true/false
word requires review. Other forms keep their evidence and receive a review reason.

The change deliberately sends ordinary prose such as "Approved in November"
to review too. A small English keyword list cannot establish negation scope,
conditions, tense, checkbox selection or the relationship between a statement
and a schema field. It is preferable to expose that uncertainty than silently
assign the wrong value. No extracted value is automatically corrected.

Boolean leaves are part of the public custom-schema Python API, including the
[purchase-order example](../../README.md#bring-your-own-schema). This is an
unreleased source change; the PyPI version remains 0.2.7.

## Retained PDF replay

[`run.py`](run.py) generates [32 labelled synthetic PDFs](pdfs/), loads their
real text layers and coordinates, and verifies both Boolean values against
each quote. The 64 outcomes are hand-specified controls. No extraction model
was called; these are constructed counterexamples, not production accuracy data.

| Control group | Before | After |
| --- | ---: | ---: |
| Explicit answers: matching claim verifies, opposite claim needs review | 24/24 | 24/24 |
| Prose and choices: neither value automatically verifies | 20/40 | 40/40 |
| All outcomes | 44/64 | 64/64 |

The 20 changed outcomes include correct guesses about readable prose as well
as wrong guesses. They are **not** 20 measured extraction errors. The first
three table rows demonstrate unambiguously wrong false approvals. The replay
also includes conditional answers, future approval, double negation, both
checkbox selections and competing answers.

All 64 claims retain the same values, exact matched text, match score, page
and rectangles before and after. JSON values remain Booleans. Read
[`before.json`](before.json), [`after.json`](after.json), and the installed-wheel
replays for [Python 3.11](installed-3.11.json) and [Python 3.14](installed-3.14.json).
Every report includes the driver, PDF and implementation hashes.

Each control has its own one-page PDF so a literal `yes` does not match unrelated
controls elsewhere in a combined document. An initial combined-PDF experiment
correctly encountered the existing repeated-quote review rule; it could not
isolate Boolean interpretation. The final replay exercises both stages without
removing or bypassing grounding checks.

## Reproduce

From the repository root:

```sh
uv sync --locked --extra dev
uv run --no-sync python studies/boolean-evidence/run.py --src src \
  --pdf-dir studies/boolean-evidence/pdfs --output /tmp/fieldproof-booleans.json
```

To inspect the previous behavior, pass `--src /path/to/79c3061/src` and
`--observe-only`. To test a wheel, invoke that environment's Python and omit
`--src`; `reportlab` is needed only to regenerate the verification fixtures.
Existing PDFs must match regeneration byte for byte.

The [verification record](checks.json) contains the clean-checkout commands,
package hash and dependency snapshots. The clean Python 3.11 source suite and
the Python 3.14 installed-wheel suite exercise the generic verifier and existing
invoice/receipt/contract behavior. The static and server UI builds were rebuilt
from the lockfile for packaging. This change is to the Python custom-schema
value checker; no new browser workflow is claimed.

## Limits

- Matching an explicit answer does not prove that its label belongs to the
  caller's schema field. A quote from the wrong field can still supply the same
  written answer. Inspect the retained source association.
- Prose, checkbox glyphs, choice lists, untranslated answers and unfamiliar
  labels need review. This narrows automatic verification coverage.
- A model that quotes only a short `yes` or `no` still has to pass grounding:
  repeated, clipped or mismatched evidence follows the existing review rules.
- Synthetic examples establish these failure modes and the explicit-answer
  contract. They do not measure real document extraction accuracy or review effort.
