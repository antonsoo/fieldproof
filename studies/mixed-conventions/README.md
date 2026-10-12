# A fallback cannot settle conflicting evidence

Baseline `c006a5e7e1b93c7037b64cfb0f2229c9e9418cd9` uses the same `None` result
for two different situations: no decisive number/date convention was found, or
both conventions were found. `verify` then applies the caller's fallback in
either case. On a document containing both US and European formats, supplying
different defaults can verify either `60` or `60000` from `60.000`, and either
March 4 or April 3 from `03/04/2026`.

The corrected verifier retains the set of observed conventions. Defaults apply
only to an empty set; a unique inferred convention still wins over a default.
Conflicting patterns leave ambiguous claims in `needs_review`, with their source
quote, page and boxes retained and an explicit conflict reason. Unambiguous
amounts and dates remain usable. Number and date conflicts are independent.
The existing singular inference helpers retain their old return values; new
plural helpers expose the complete observed set.

This is an unreleased source change, not a package or hosted-demo update.

## Controlled PDF and CLI results

All documents and extractions here are constructed examples, not real invoices
or model output. No provider is called. [`replay.py`](replay.py) generates eight
PDFs covering absent, consistent and conflicting conventions, reverse evidence
order, and signals split across two pages. It checks all nine default pairs and
two paired amount/date readings, plus two unambiguous controls per report.

| Observation | Baseline | Corrected source |
|---|---:|---:|
| Complete reports matching the declared expectations | 102 / 144 | 144 / 144 |
| Ambiguous claims verified despite conflicting conventions | 48 | 0 |
| Explicit, unambiguous control fields verified | 288 / 288 | 288 / 288 |

The [before](before.json) and [after](after.json) captures retain all 576 field
decisions, original quotes and actual PDF locations. These selected inputs test
the decision rule, not document-extraction accuracy or prevalence in user files.

The [illustrative PDF](../../examples/mixed-conventions.pdf) and
[handwritten fixture](../../examples/fixtures/mixed-conventions.json) reproduce
the same behavior through the real CLI:

```bash
fieldproof verify examples/fixtures/mixed-conventions.json examples/mixed-conventions.pdf \
  --number-style thousands --date-order dmy --out /tmp/fieldproof-mixed.json
```

The [baseline CLI result](cli-before.json) verifies all four fields. The
[corrected result](cli-after.json) keeps the vendor and invoice number verified
and sends the total and issue date to review. The quoted values have not changed;
their document-wide interpretation remains unresolved.

## Receipt compatibility

The original receipt study's unchanged adapter and claim generator replay
133,722 cases across all 1,052 CORD/SROIE documents, with that study's stated
number/date defaults. Every input is paired, and **no verdict or location result
changes**. The cached source files are hash-checked against the original manifest.
This is compatibility evidence for those annotated words and generated claims,
not a fresh OCR/model run or an independent estimate of accuracy.

One document has conflicting calendar-valid date-shaped tokens, `11-22-31` and
`19-09-17`; its annotated date is unambiguous and its verdicts remain unchanged.
A valid-looking numeric token is not proof that it is semantically a date. The
pre-existing verifier limitations and the adapter's ground-truth limitations
remain; unchanged wrong locations in the corpus are not repaired by this work.
[Sources, licences and original study limits](../cord-grounding/README.md) apply.

## Limits

- Inference remains a document-wide heuristic. It does not infer a field-specific
  locale, identify the semantic role of every date-shaped token, or reconcile
  different conventions in different sections. A unique but irrelevant signal
  can still mislead the inference.
- A conflict does not prove that either reading is wrong. It means a fallback
  cannot establish which reading this quote supports. Reviewers can make an
  explicit correction; that does not rewrite the automated verification report.
- The review server does not expose the CLI/library fallback settings. Its
  ambiguous fields already needed review without a fallback; this change adds
  the conflict explanation there. The before/after verification change is
  demonstrated by the library and actual CLI captures above.
- The number convention describes the role of a dot. Ordinary two-decimal
  quantities alone do not settle it, and unit/currency semantics remain outside
  this check. No per-field override is introduced by this change.

## Reproduce

```bash
uv sync --locked --extra dev
uv run python studies/mixed-conventions/replay.py --source . \
  --output /tmp/fieldproof-mixed-after.json --pdf-dir /tmp/fieldproof-mixed-pdfs
uv run python studies/mixed-conventions/review_example.py
```

For the baseline, extract `git archive c006a5e` into a separate directory, pass
that directory as `--source`, and add `--baseline`. Omit `--source` to exercise
a separately installed wheel. The generated PDF hashes must agree between runs.
The example generator recreates the checked-in PDF and fixture exactly.

For the full receipt replay, retain the earlier study's source cache and run its
driver twice with `--stated`, changing only the source tree:

```bash
uv run --locked --extra dev --with pyarrow python -I studies/cord-grounding/run.py \
  --src /path/to/source/src --out /tmp/fieldproof-receipts.jsonl --workers 4 --stated
```

The independent comparison driver in `studies/numeric-evidence/compare_receipts.py`
checks the complete case inventory and matching inputs before comparing verdicts
and locations. Raw receipt text and images are not redistributed here.
