# Row-evidence verification, 2026-10-09

Implementation `4d1b24b`, study and browser scenario `1680015`, based on
`c7f7cbc`. This is local, unreleased work. No push, tag, deployment, provider
request or customer document was involved. All work was done without sub-agents.

The concrete change is in repeated-quote selection: an unrelated nearby row
or page, a rejected description, or tied columns can no longer supply a
silently chosen evidence location. The [study](../studies/row-locality/README.md)
records both the improvement and the extra review burden. It does not claim
to solve table structure or semantic field assignment.

## Verified behavior

| Check | Command or workflow | Result |
| --- | --- | --- |
| Actual PDF controls | `uv run --locked --extra dev python -I studies/row-locality/run.py --src src --out OUT` | All 14 expected statuses and source locations; nine unsafe baseline choices rejected, five valid controls retained |
| Annotated receipt replay | `uv run --locked --with pyarrow python -I studies/row-locality/receipts.py --src SRC --out OUT`, baseline and current, then `compare.py` | 2,853 identical claims on 400 pinned receipts; all source hashes checked |
| Existing example data | `uv run --locked --extra dev python scripts/build_demo_data.py` | All four static samples regenerate without tracked changes |
| Clean locked Python 3.12.12 | Fresh archive of `1680015`; `uv sync --locked --extra dev --extra ocr`; `uv run --locked pytest -q` | 315 passed in 39.44 seconds |
| Python lint and types | `uv run --locked ruff check src tests studies/row-locality`; `uv run --locked mypy src` | Clean; 32 source files typed |
| Formatting | `ruff format --check src/fieldproof/ground src/fieldproof/verify/engine.py tests/test_row_locality.py studies/row-locality` | All 13 checked files formatted |
| Minimum Python 3.11.13 | Fresh environment; `uv pip install --resolution lowest-direct -e '.[dev,ocr]'`; `pytest -q` | 315 passed in 42.61 seconds; two dependency deprecation warnings |
| Minimum-version PDF pipeline | Same PDF replay using the 3.11 environment | All 14 expected statuses and locations |
| Fresh web install and builds | `npm ci`; `npm run lint`; `npm run typecheck`; `npm run format:check`; `npm test`; `npm run build`; `npm run build:demo` | Clean; 50 unit tests; 34 files in each output identical to the working build |
| Clean distribution build | `uv run --locked python scripts/bundle_ui.py`; `uv build` | Wheel and sdist built; 23 bundled UI files |
| Installed CLI, outside the checkout | New wheel-only runtime environment; documented `extract` then `verify` commands on the row example | Both report 14 verified / one review / zero unsupported |
| Installed library | PDF replay with `--src` naming installed `site-packages`; import location asserted | All 14 expected statuses and locations |
| Production browser workflows | Existing full suite with external server URLs, installed wheel server and production static demo | 64 passed, zero skipped, unexpected or flaky; Chromium and Firefox |

The minimum environment resolves the lowest **direct** dependencies, not every
transitive dependency. Its two warnings concern Starlette's HTTPX compatibility
and an AnyIO alias. Web tooling was Node 26.7.0 / npm 12.0.1; no claim about a
new Node 24 run is made. The runtime browser payload contains no changed UI code.

## Inspectable artifacts

The [full browser summary](../studies/row-locality/results/browser.json) retains
every scenario and its outcome. The suite checks page errors, unhandled promise
rejections, CSP violations and off-origin requests. Its accessibility checks
include the new review at desktop and phone widths. An initial new test expected
reload to reopen the document automatically; it was corrected to exercise the
existing Sessions / Open workflow, after which both focused and full runs passed.

The new scenario verifies that the ambiguous quantity has no highlight and the
other two quantities have their own locations. A correction from one to three
survives export and session reopening while preserving the original report.
The installed-wheel critical workflow can be repeated with:

```bash
# Start the installed package's server separately on port 4298.
web/node_modules/.bin/playwright test --config studies/row-locality/browser.config.mjs
```

The full run used the repository's existing live/demo test files and four
browser projects, with the installed server on 4298 and static preview on 4299.
The normal source-server suite remains `npm --prefix web run test:browser`.
Servers were launched separately so stopping them did not terminate the runner.

[Package hashes](../studies/row-locality/results/package.json) confirm that all
55 runtime payload files in the tested wheel match the clean archive's new
build: 32 Python modules and 23 UI files. README metadata differs between the
earlier test wheel and the later documentation build; application code does not.

All four [screenshots](assets/row-locality/) were captured from the actual
installed application and visually reviewed. The warning is legible, the PDF
shows the three quantities, and the phone layout has no horizontal overflow.
Images are 62-187 KB. The existing desktop layout shows many field rows; the
new flagged field sorts to the top rather than needing a new screen.

## Boundaries and next work

The receipt replay's repeated-quote errors fell from 431 to 14. Of the changes,
416 wrong locations became reviews, one became correct, and 197 previously
correct locations became reviews. No correct location became wrongly verified.
The rule was not tuned to remove the remaining cases after inspecting them.

The 746 deliberately swapped **unique** quotes still verify; source support
alone does not establish a value's row, column or field role. This is tracked
separately as local issue `officina-4k2`. The repeated-quote repair is
`officina-024`. Single-line overlap, schema-order anchors, imperfect OCR geometry
and the study's amount parser all limit what these measurements establish.
No production accuracy rate is inferred from scripted claims.

Demo build: `npm --prefix web run build:demo`, output `web/dist-demo/`.
Live bundle: `uv run --locked python scripts/bundle_ui.py`, output
`src/fieldproof/server/static/`. Both remain local.

Suggested repository description: "Document extraction with source-linked evidence, consistency checks and human review."
Topics: `document-ai`, `pdf`, `data-extraction`, `grounding`, `ocr`, `python`, `human-in-the-loop`.
