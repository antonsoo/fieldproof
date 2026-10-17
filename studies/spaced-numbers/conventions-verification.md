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

## Installed artifacts and actual workers

A fresh source archive at `15113e8` builds the corrected wheel and sdist;
its 41 Python modules are identical to `79c85ad`. A separate non-editable
installation passes all 72 spaced-number regressions on both supported-runtime
checks below. Every declared runtime/dev/OCR dependency was supplied directly
with `--resolution lowest-direct` for the minimum installation.

| Installation | Python | PDFium | pdfplumber | Pydantic |
| --- | --- | --- | --- | --- |
| Built wheel | 3.14.7 | 5.14.0 | 0.11.10 | 2.14.1 |
| Minimum direct dependencies | 3.11.13 | 5.0.0 | 0.11.9 | 2.12.0 |
| Exact public README Git pin | 3.12.12 | 5.14.0 | 0.11.10 | 2.14.1 |

All three reproduce the 14 new claim records, including reasons and rectangles,
and the complete digest of the original 134-claim ledger. The installed native
receipts retain that digest and reference the existing full ledger rather than
duplicating it. Each installation also passes 12 actual API upload/extraction
worker controls and checks the resulting report/export statuses. Each control
uses its own one-page document. No provider/model calls are involved.

The [verification receipt](results/conventions-verification.json) links those
ledgers and records the complete corpus replay. The
[distribution receipt](results/conventions-artifacts.json) byte-compares all 41
Python modules in the wheel, sdist and installation and all 23 locally served
UI files. The [public source receipt](results/conventions-public-source.json)
records the actual Git installation provenance, public main ref and four pinned
raw files. Direct Git installation has no bundled UI, as documented; the wheel
separately contains it.

The corrected installed wheel also passes the actual Chromium and Firefox
spaced-amount review workflow: full source highlight, correction, offline JSON
and CSV downloads, reconnect and archive save/delete/restore. Accessibility and
overflow checks pass at 1440px and 375px in light and dark themes. All eight
new captures were opened and inspected and are byte-identical to the existing
[spacing screenshots](../../docs/assets/spaced-numbers/chromium-1440-light.png),
so no duplicate images are committed. The
[browser receipt](results/conventions-browser-summary.json) identifies this
final-source run independently of the older receipts.

The package version remains 0.2.7; source hashes identify the correction. The
earlier installed/browser receipts remain scoped to their recorded revisions.
These checks do not establish a registry release or hosted Python workbench.

The final installed wheel also replays the original Arabic-number study:
87 claims on 21 native PDF pages, with the complete claim-ledger digest
identical to its original corrected result (18 verified, 69 requiring review).
The [compatibility receipt](results/conventions-arabic-recheck.json) separates
this final-source recheck from that study's historical build and browser records.
