# Arithmetic verification, 2026-10-09

Local source work based on `e92cf6f`; no publication, tag, push or deployment.
No provider requests or real customer documents were used. The new examples
are explicitly synthetic. The [study](../studies/arithmetic-evidence/README.md)
contains the reproducible comparison, actual reports and raw timings.

## Checks performed

| Surface | Command or workflow | Result |
| --- | --- | --- |
| Locked Python 3.12.12 | `uv sync --locked --extra dev --extra ocr`; `pytest -q` | 305 passed |
| Minimum Python 3.11.13 | Fresh venv; `uv pip install --resolution lowest-direct -e '.[dev,ocr]'`; `pytest -q` | 305 passed, two dependency deprecation warnings |
| Python 3.14.7 | Fresh `UV_PROJECT_ENVIRONMENT`; locked dev and OCR install; `pytest -q` | 305 passed |
| Python lint and types | `ruff check src tests studies/arithmetic-evidence scripts/build_demo_data.py`; matching `ruff format --check`; `mypy src` | Clean; 32 source files typed |
| Browser build | Clean `npm ci`; `npm run lint`, `typecheck`, `format:check`, `test`, `build`, `build:demo` | Clean; 50 unit tests |
| Numerical oracle | `studies/arithmetic-evidence/run.py`, current and old source selected with `--src` | 4,800 cases; 1,622 baseline disagreements, zero current |
| Full PDF pipeline | Same study generates, loads and verifies 13 PDFs | All expected current field verdicts on 3.11, 3.12 and 3.14 |
| Distribution | `python scripts/bundle_ui.py`; `uv build`; wheel installed into fresh runtime venv | Wheel and sdist built; 23 bundled UI files |
| Installed CLI | `fieldproof extract` and `fieldproof verify` on `line-arithmetic.pdf` from outside checkout | Both 7 verified / 3 review / 0 unsupported; baseline extract 10 / 0 / 0 |
| Installed library | Study replay against installed `site-packages`, import path asserted | All 13 PDF controls and 4,800 rational comparisons pass |

The minimum-version environment uses the lowest resolvable **direct**
dependencies, not the lowest version of every transitive dependency. The wheel
environment separately resolved current dependencies, including Pydantic 2.14.0
and FastAPI 0.143.0, without editable installation. ReportLab was added only to
generate the replay's controlled PDFs. It is not a new runtime dependency.

The configured source/test lint is clean. An exploratory repository-wide Ruff
run also encountered two pre-existing long lines in `scripts/generate_samples.py`;
that unrelated file was not changed or included in the clean-check claim.

## Browser and package behavior

The production static demo and the separately installed wheel's server were
exercised in Chromium and Firefox. The suite covers document/fixture upload,
actual PDF rendering and highlight placement, source-linked arithmetic warnings,
the worker's API report, numeric edits, reload/session behavior, and downloaded
JSON/CSV. The new live scenario confirms that correcting quantity to two exports
the correction with original value three and leaves the original audit intact.
The new static sample tests its deep link, correction, reload and JSON download.

Adding the fourth sample exposed overflow and reduced field space on 320-pixel
screens. The Arithmetic label and mobile selector spacing were adjusted. The
existing 320/375/1440-pixel layout, light/dark, keyboard and accessibility checks
were retained rather than weakened. See the final browser result retained in
[`browser-summary.json`](../studies/arithmetic-evidence/results/browser-summary.json).

One earlier managed-server run printed all 60 then-current scenarios passed but
its shell exited with SIGTERM during server cleanup. Final browser verification
uses separately started servers, including the installed wheel, so teardown
does not obscure the runner's exit status. The focused installed-wheel config
is retained in the study; the full suite uses the same test files and projects
with those external server URLs.

Screenshots in [`assets/arithmetic/`](assets/arithmetic/) were captured from
the running application and visually inspected, including both browsers, the
real PDF beside its three flagged values, and narrow static sample selectors.
Each image is below 1.5 MB. `chromium-observations.json` and
`firefox-observations.json` retain the actual API calculation and downloaded
correction row. These are browser observations, not mocked screenshots.

The demo build command is `npm --prefix web run build:demo`, output
`web/dist-demo/`. Before building after changing a fixture or verifier, regenerate
its data with `uv run --locked --extra dev python scripts/build_demo_data.py`.
The live server bundle uses `scripts/bundle_ui.py`, output
`src/fieldproof/server/static/`, included in the locally built wheel/sdist.

## Limits

The evidence establishes arithmetic behavior on constructed cases, not accuracy
on real invoices, model extraction quality, completeness of extracted line
items, currency-specific rounding or support for discounts and unit conversions.
Calculations operate on validated numeric claims, whose original precision may
already have been lost. A human correction does not recalculate the original
audit. Full details and the response contract are in
[arithmetic-checks.md](arithmetic-checks.md).
