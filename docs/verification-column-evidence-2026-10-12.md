# Explicit column evidence: source and installed-package verification

Implementation: `6dfb2ee51953698522a91b4166efd1b2c402f1ef`.
Baseline: `4cb9624f6a8342003bd81d7aea11e5e7cc1ddb25`.

A fixture assigning quantity `12.50` and unit price `3` to a PDF that prints
quantity `3` and unit price `12.50` previously verified both. Multiplication
still passes. Complete declared table headers now supply a separate spatial
observation; contradictory assignments require review with the actual number
and header locations retained. The [study](../studies/column-evidence/README.md)
contains the algorithm, API, replay scripts, exact limits and paired reports.

| Verification | Observed result |
| --- | --- |
| 308 constructed PDF/input pairs | All hashes equal before/after; 292 wrong numeric assignments move from verified to review |
| Original quote evidence and arithmetic | 1,232 item source locations and 308 arithmetic ledgers unchanged |
| Existing examples | All 105 field verdicts across nine PDF/fixture pairs unchanged; reports differ only by the additive column ledger |
| External header coverage | Zero recognized complete headers across invoice2data's 11 pinned PDFs; no real-document accuracy claim |
| Clean Python 3.12.12 archive | Ruff, mypy, and 437 tests pass; one real-Tesseract check skipped because the engine is unavailable |
| Installed Python 3.11.13 and 3.14.7 | Each repeats 437 passing tests plus the same skip; all 308 study cases match the inspected reports byte for byte |
| Installed console entry points | Each runs ten extract/verify pairs; 20 output JSON files are identical between interpreters |
| Web build | Node 24.21.0; typecheck, lint, format, and 50 unit checks pass |
| Installed server and built static demo | 76 Chromium/Firefox browser scenarios pass |
| Paired new review flow | Four baseline/current browser scenarios, eight desktop/phone views; reasons, source highlights, corrections and original ledgers checked |
| Package provenance | 124 source/test/example/build inputs equal the clean archive; 57 package files including 34 Python modules equal clean source, sdist, wheel and both installations |
| Served UI | All 23 assets served by both baseline and installed-current servers equal the tested build |

The four retained screenshots were opened and inspected. Browser requests stay
on the local server origins; no hosted site was used for these checks. The final
capture adds a visible `line_items` search filter to the archived browser harness;
the production source is unchanged. The artifact receipt records both harness
hashes and the source-input comparison.

| Local artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| sdist | 600091 | `b7b784b9db014c95fdd5a947179b99ec95d72b64ec86254437c50c3afc3d6347` |
| wheel built from sdist | 578247 | `3245059c08bf3ecce0162b55a3fafec0b2bf415fc67c84720d963c1efd9a44ed` |

See [the machine-readable receipt](../studies/column-evidence/results/artifacts.json).
No package release, tag or hosted deployment accompanies this source change.

The rule is intentionally narrow: default invoices need all four configured
headers, usable geometry and contiguous complete rows. Missing or ambiguous
column evidence remains unavailable and does not alter the prior source verdict.
This cannot establish semantic correctness, row completeness, OCR accuracy or
arbitrary table structure. It adds measurable work: the constructed 300-row
verification/report serialization median rose from 180.74 ms to 359.75 ms on
this 14-vCPU WSL2/Linux machine; five local repetitions are not a latency guarantee.
