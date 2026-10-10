# Date evidence verification, 2026-10-09

Core changes: `d7d0128`, `539b6c2`. Baseline: `7be880a`.
All work was performed without sub-agents.

A real PDF containing `Issue Date: 03/04/2026` and `Reference: 99/01/2026`
previously verified April 3 even when the caller specified month-first dates.
The impossible reference now supplies no convention. The review keeps the
actual source highlight and explains the uncertainty when no default is given.
The same boundaries apply to free-text parsing and grounding, including ISO
identifier fragments. An impossible ISO token in a quote cannot suppress the
ambiguity check on another numeric date.

The [study](../studies/date-conventions/README.md) contains the PDF, fixture,
reproduction commands, paired results and limits. In 252 checks through 42
constructed PDFs, unsupported verifications fell from 58 to zero, and supported
claims incorrectly sent to review fell from 20 to zero. Calendar validity is
also checked against a separate `datetime.date` constructor oracle.

A paired replay on 1,052 existing receipt annotations produced the same 7,600
claim verdicts, candidate counts and gold-location outcomes as the baseline.
Four inferred document conventions changed. The study explicitly retains the
cost of rejecting a real date fused to `TIME` and a pre-existing ISO quote
matched outside its annotated location. These are scripted grounding checks,
not measurements of production model or OCR accuracy.

## Clean build and installed package

Checks ran from a fresh archive, subsequently updated to `539b6c2` for the final
ISO repair. Runtime source and tests came from that commit. Later changes are
retained results and documentation.

| Command or workflow | Final result |
| --- | --- |
| `uv sync --locked --extra dev --extra ocr --python 3.14`; `pytest -q` | Python 3.14.7: 328 passed, 24.12 s |
| Fresh Python 3.11 environment; `uv pip install --resolution lowest-direct -e '.[dev,ocr]'`; `pytest -q` | Python 3.11.13: 328 passed, 25.87 s; two dependency deprecation warnings |
| `ruff check src tests studies/date-conventions`; `mypy src` | Clean; 33 typed source modules |
| `ruff format --check` on changed Python modules and study scripts | Clean |
| PDF replay in clean and minimum environments | All 252 verdicts and full field results match the primary run |
| Fresh Node 24.21.0 `npm ci`; typecheck, lint, format, `npm test` | Clean; 50 web tests |
| `npm run build`; `npm run build:demo` | Both production builds; each has 34 files identical to the working-tree build |
| `python scripts/bundle_ui.py`; `uv build` | Wheel and sdist built with 23 bundled UI files |
| Installed wheel outside the source tree | All 252 full PDF field results match; six real CLI extraction scenarios pass |

The [package ledger](../studies/date-conventions/package.json) lists dependency
versions and hashes for all 56 runtime files, identical in the clean source,
wheel and installed package. The minimum run uses the lowest allowed direct
dependencies, including Pydantic 2.10.0, pdfplumber 0.11.9 and pypdfium2 4.30.0;
it does not pin every transitive dependency. Its two warnings concern
Starlette's HTTPX compatibility and an AnyIO alias.

The normal Python lint scope is `src tests`; the new study scripts were checked
as well. An exploratory repository-wide `ruff check .` also found two existing
long lines in `scripts/generate_samples.py`, outside that configured CI scope.
Those unrelated lines were left unchanged.

## Installed review workflow

The final wheel serves its own bundled UI on a disposable local server. The
browser workflow uploads the actual PDF and fixture, checks three verified
fields and one needing review, inspects the highlight and both possible date
readings, edits the date, exports the correction and reopens the session.
Downloaded JSON equals the API export; the original automated report is
preserved. Human edits remain explicitly separate from automated verification.

Chromium and Firefox run accessibility and horizontal-overflow checks at 1440
and 375 pixels. The four [screenshots](assets/date-conventions/) were captured
from the installed application and visually inspected: the reason wraps on the
phone, and desktop retains the quoted date's highlight. The browser audit also
checks page errors, rejected promises, CSP violations and off-origin requests.

The full production suite covers this workflow and existing live/demo review,
correction, export, cancellation, resource-budget and PDF-rendering behavior.
All **68 workflows passed** in 1.9 minutes, with no failed or skipped cases.
The [browser ledger](../studies/date-conventions/browser.json) names each scenario.

```bash
# Installed server on port 4300; production demo on port 4301.
FIELDPROOF_BROWSER_FULL=1 web/node_modules/.bin/playwright test \
  --config studies/row-association/browser.config.mjs
```

The static demo remains a set of precomputed reports. This repair changes the
Python verifier and installed application's results; it is not a PyPI release
or a new Pages deployment. The source version remains 0.2.7 with these changes
under Unreleased. Build the source to use them.
