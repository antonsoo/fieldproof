# A written date must keep every digit

At source `7a0b35e`, the fixture-provider command verified a contract's effective
 date as `2026-05-01` from the exact printed quote `Effective date: May 1, 20260`.
Grounding found the complete quote with a score of 100, but the value parser
silently dropped the last digit. The same path read `111 January 2026` as
January 11. These are constructed counterexamples, not model or OCR measurements.

The corrected value check sends that claim to review. It retains the original
claim, quote, page and boxes; it does not infer the intended date. Compare the
[before CLI report](cli-before.json) and [after CLI report](cli-after.json), or run:

```sh
uv sync --locked --extra dev
uv run --locked fieldproof extract studies/written-dates/extra-year-digit.pdf --schema contract --fixture studies/written-dates/extra-year-digit.json --out /tmp/written-date-report.json
```

## Shared evidence parsing

Written months now use the same complete-token boundaries as numeric dates.
They cannot begin inside a word/identifier or longer day, or end inside a longer
year/identifier. A sentence's final period and surrounding parentheses remain
valid. This is deliberately conservative about fused OCR words and identifiers.
Grounding and value checks import one set of patterns, preventing a permissive
fallback from accepting a fragment rejected by the other path.

Both paths also share supported written-month interpretation. The previous
value checker rejected `Jan. 1, 2026`, `1 Jan. 2026` and `May 1 2026` despite
grounding recognizing those spellings. They now retain support through the full
verification pipeline. Calendar validity still comes from the standard library.

## Actual PDF replay

[replay.py](replay.py) renders 26 deterministic PDFs and checks two quotes per
PDF: the literal labelled text and a rewritten ISO date. Expectations are
specified independently of the parsing code. Inputs, hashes, verdicts, source
text and boxes are retained in [before.json](before.json) and [after.json](after.json).

| Outcome across 52 constructed claims | Before | After |
| --- | ---: | ---: |
| Unsupported claims verified | 11 | 0 |
| Supported claims not verified | 8 | 2 |

The two remaining supported cases are existing grounding limits: an ISO quote
cannot locate the date inside `(May 1, 2026)` or `Date:May 1, 2026` under the
current whole-word/numeric-modifier rules. Quoting their full printed text
verifies correctly. These cases remain explicit in the replay, not counted as
fixed. This small boundary set does not estimate real-document accuracy.

```sh
uv run --locked python studies/written-dates/replay.py --out /tmp/written-dates.json
```

To compare an older checkout, supply `--src /path/to/old/src --observe-only`.
A date's presence still does not establish its semantic role or the intended
meaning of a malformed source. A human confirmation remains separate from the
automated verdict.
