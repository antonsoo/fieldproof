# Item-association verification, 2026-10-09

Implementation `4ef12a4`, evidence `bb6f846`, baseline `c16cd40`.
The change checks whether quoted invoice and receipt numbers share the visual
line of their independently supported item description, including unique quotes.
Custom schemas can declare the relationship with `RowEvidenceRule`.
The report preserves the original source verdict and both source locations.
All work was performed without sub-agents.

The [study](../studies/row-association/README.md) defines the API, reproduces the
original failure, and records its limits. In the example PDF, a unique `2`
belongs to Packing but was assigned to Delivery. It now needs review while
retaining its actual source highlight. The previous report verified all 15
fields; both current CLI commands report 14 verified, one review, zero unsupported.

## Behavior and independent evidence

| Check | Result |
| --- | --- |
| Nine constructed PDFs, native text extraction | Five wrong assignments now require review; two valid controls remain verified; one correct wrapped row requires review; one wrong-column case still verifies |
| Paired annotated receipt replay | Same 2,853 scripted claims on 400 receipts; source hashes and identical inputs checked |
| Wrongly verified unique quotes | 746 before, five after; 741 now require review |
| Additional correct locations requiring review | 192 |
| Repeated-quote outcomes | Unchanged: 629 correct, 14 wrong, 729 needing review |
| Correct locations becoming wrong | Zero |
| Installed CLI and browser | Review reason and real highlight retained; correction 2 to 3 survives export and session reopening |

All 19 remaining receipt errors are retained in the paired results. The corpus
uses source annotations, an existing reading-order adapter and scripted claims;
it does not measure production, model or OCR accuracy. Skew, overlapping rows,
wrapped cells and semantic column roles remain limitations. A same-line result
explicitly does not establish the column or field role.

## Clean checkout and package

Checks ran from a fresh `git archive bb6f846`, not just the working environment.

| Command or workflow | Result |
| --- | --- |
| `uv sync --locked --extra dev --extra ocr`; `uv run --locked pytest -q` | Python 3.12.12: 323 passed in 35.38 seconds |
| `uv run --locked ruff check src tests studies/row-locality studies/row-association` | Clean |
| `uv run --locked mypy src` | 33 source modules, no issues |
| `ruff format --check` on changed Python modules and study scripts | 10 files already formatted |
| Fresh Python 3.11.13 environment; `uv pip install --resolution lowest-direct -e '.[dev,ocr]'`; `pytest -q` | 323 passed in 36.00 seconds; two dependency deprecation warnings |
| PDF study in clean and minimum environments | All nine expected outcomes; extracted reports and locations match the primary run |
| Fresh `npm ci`; `npm run typecheck`; `npm run lint`; `npm run format:check`; `npm test` | Clean; 50 web tests |
| `npm run build`; `npm run build:demo` | Both production outputs built; each has 34 files identical to the browser-tested build |
| `uv run --locked python scripts/bundle_ui.py`; `uv build` | 23 UI files bundled; wheel and sdist built |
| Installed wheel outside the source tree | CLI extraction and re-verification, nine PDF controls, and complete browser suite passed |

The minimum environment resolves the lowest direct dependencies, not every
transitive dependency. Its warnings concern Starlette's HTTPX compatibility and
an AnyIO alias. Web checks used Node 26.7.0 and npm 12.0.1. No fresh Node 24 or
Python 3.14 run is claimed here.

The [package ledger](../studies/row-association/results/package.json) records
hashes: all 56 runtime files match between the installed test wheel and the
clean build (33 Python modules, 23 UI files). README metadata differs because
the test wheel preceded the study documentation. Clean and minimum-version
PDF reports are retained alongside it; ReportLab versions produce different
PDF bytes but the extracted evidence matches.

## Browser review

The installed wheel served the production UI; the static demo was separately
served from its production build. Chromium and Firefox ran the complete suite:
**66 passed**, zero skipped, unexpected or flaky, in 166.29 seconds.
The [browser ledger](../studies/row-association/results/browser.json) lists every
scenario. The suite checks page errors, unhandled rejections, CSP violations
and off-origin requests. The new workflow also runs accessibility scans at
1440 and 375 pixels, checks horizontal overflow, reads the row ledger through
the actual server API and confirms human edits preserve that original ledger.

```bash
# Start the installed server on 4300 and production static demo on 4301 first.
FIELDPROOF_BROWSER_FULL=1 web/node_modules/.bin/playwright test \
  --config studies/row-association/browser.config.mjs
```

All four [screenshots](assets/row-association/) were captured from the installed
application and visually inspected. The flagged field appears first; its
warning wraps on the phone without horizontal overflow. Desktop shows the
actual quoted quantity on the other row. The current interface exposes the
reason and highlight; the fuller comparison ledger is in report JSON.

The final browser config uses the operating system's temporary directory for
output rather than a machine-specific path; test discovery was checked after
that non-runtime change.

The static demo build is `npm --prefix web run build:demo`, output
`web/dist-demo/`. The installed UI bundle is built by
`uv run --locked python scripts/bundle_ui.py`, output
`src/fieldproof/server/static/`. This verification does not constitute a PyPI
release or a Pages deployment.

Suggested repository description: "Document extraction with source-linked evidence, consistency checks and human review."
Topics: `document-ai`, `pdf`, `data-extraction`, `grounding`, `ocr`, `python`, `human-in-the-loop`.
