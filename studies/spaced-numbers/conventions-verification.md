# Preserve formatting evidence when an amount's boundaries are uncertain

The correction is `79c85ad223e73f53a2a931529e1e6197bb6dbcc7`.
The initial spacing correction at `b283e1b` introduced this regression:

```text
Total 60.000
First convention 1.234,50
Quantity and price 1 1,234.50
```

The last row cannot establish the value of either numeric component because its
spacing is unresolved. Its complete `1,234.50` spelling still establishes a
decimal-point separator role. Discarding that observation hid the conflicting
formats and let the verifier automatically approve 60000. Reversing the cues
wrongly approved 60. A caller's default must not override a documented conflict.

The fix retains lexical punctuation roles independently of amount support.
Values still use whole unresolved spans; this does not let a component verify.
Malformed numbers, identifiers, exponents, rates and counts retain their
existing exclusions from convention inference.

| Six independent native PDF controls, 14 claims | `b283e1b` | `79c85ad` |
| --- | ---: | ---: |
| Conflicting-format claims wrongly approved | 2 | 0 |
| Supported single-convention claims withheld | 2 | 0 |
| Unexpected style observations | 4 | 0 |
| Unresolved component claims approved | 0 | 0 |

The [before](results/conventions-before.json) and
[after](results/conventions-after.json) ledgers retain every verdict, reason,
rectangle, expected convention, source hash and input digest. Each page is an
independent document in the replay, so cues on other control pages cannot leak
into its convention. These authored controls are not OCR/model accuracy data.

```sh
uv run --locked python studies/spaced-numbers/conventions.py --src src --out /tmp/conventions.json
```

Normal replay uses the committed PDF and needs no ReportLab. To regenerate it,
add `--generate` with the development dependencies installed. Use
`--observe-only` to retain the known baseline mismatches.

The full source suite passed Ruff, mypy on 41 modules and 820 Python checks.
Five actual-engine OCR cases were skipped because Tesseract was unavailable.
The original 134-claim native ledger is exactly unchanged, including reasons
and rectangles. Rerunning all 133722 receipt cases on 1052 documents produces
the same verdict/location pairs as `b283e1b`: 383 changes from `d94f2f4`, zero
newly verified claims and the same review costs described in
[the spacing study](verification.md). This corpus was used during development;
it is compatibility evidence, not a held-out extraction benchmark.

The package version remains 0.2.7; source hashes identify the correction. The
earlier installed/browser receipts remain scoped to their recorded revisions.
No registry release is claimed.
