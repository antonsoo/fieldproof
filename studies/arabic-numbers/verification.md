# Local verification of the Arabic-number correction

The production code under test is commit
`760a1d7995f9dd4d25220ee20b32773fbf75d5e0`. The final evidence commit also
uses the UI's actual theme button in the focused browser check. The Python
implementation and bundled production UI are unchanged by that check.

## Fresh archive and distributions

A fresh `git archive` of the source commit was installed with the locked
development and OCR extras. The commands below ran in that archive:

```sh
uv sync --locked --extra dev --extra ocr
.venv/bin/ruff check src tests studies/arabic-numbers
.venv/bin/mypy src
.venv/bin/pytest -q -rs
.venv/bin/python scripts/bundle_ui.py
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run format:check
npm --prefix web test
npm --prefix web run build:demo
uv build --out-dir dist
```

Python lint and strict type checking passed (41 source files). The complete
Python suite passed 748 checks; five actual-Tesseract cases were skipped
because the executable is unavailable. The OCR Python extra was installed.
Web lint, type checking and formatting passed, along with all 70 unit checks.
Both production web builds succeeded. `scripts/bundle_ui.py` performs a fresh
`npm ci` and packages the local-server UI, excluding source maps.

Build outputs:

| Command | Output |
| --- | --- |
| `npm --prefix web run build` | `web/dist/` |
| `npm --prefix web run build:demo` | `web/dist-demo/` |
| `python scripts/bundle_ui.py` | `src/fieldproof/server/static/` |
| `uv build --out-dir dist` | `dist/fieldproof-0.2.7-py3-none-any.whl`, `dist/fieldproof-0.2.7.tar.gz` |

The wheel was built through the source distribution. The version remains
0.2.7; version equality does not identify the corrected source.

[`artifacts.json`](results/artifacts.json) records distribution sizes and
SHA-256 hashes. [`artifacts.py`](artifacts.py) confirms identical parser bytes
in the wheel, source distribution and installed package, then compares all
23 locally served UI files with the wheel's bytes. This is loopback serving
evidence, not a public deployment check.

## Independent installed environments

The wheel was installed outside the checkout and replayed with Python's `-I`
isolation. No source directory was added to the installed probes' import paths.
The actual server's PDF and verification workers used that same environment.

| Environment | PDFium | pdfplumber | Pydantic | Native PDF replay | Wrong/correct API claim |
| --- | --- | --- | --- | --- | --- |
| Python 3.14.7, current resolved dependencies | 5.14.0 | 0.11.10 | 2.14.1 | 87/87 expected verdicts | needs_review / verified |
| Python 3.11.13, lowest supported direct dependencies | 5.0.0 | 0.11.9 | 2.12.0 | 87/87 expected verdicts | needs_review / verified |

For the latter, every declared runtime, development and OCR requirement from
`pyproject.toml` was made a direct requirement before resolving with
`uv pip install --resolution lowest-direct`. Passing only the wheel as a direct
requirement would not test its dependency floors.

Receipts: [`installed.json`](results/installed.json),
[`installed-api.json`](results/installed-api.json),
[`minimum.json`](results/minimum.json), and
[`minimum-api.json`](results/minimum-api.json). Their complete Python source
hashes agree with the repaired source replay. All 43 new numeric regression
checks also passed against the Python 3.14 installed wheel.

The installed receipts use `run.py --summary-only` to retain the verdict counts,
source hashes and a canonical hash of the complete claim ledger. Both installed
ledger hashes exactly match the full source-after ledger, including its reasons
and rectangles; identical rows are not duplicated in these receipts.

The actual installed CLI commands ran in separate disposable directories, with
the identical PDF and extraction fixture copied into each:

```sh
fieldproof extract review.pdf --schema invoice --provider fixture \
  --fixture review.json --out report.json
fieldproof verify report.json review.pdf
```

The baseline extraction reports four verified fields. The repaired extraction
reports three verified fields and one requiring review. Unedited output is in
[`before-cli.txt`](results/before-cli.txt) and
[`after-cli.txt`](results/after-cli.txt). The installed `fieldproof serve --port`
command also serves the bundled UI and completes the focused review flow.

## Browser workflow

The full production browser suite and focused screenshot workflow use Chromium
and Firefox against the independently installed wheel. The static demo has its
own production preview. The focused test checks:

- The wrong `234` claim requires review and highlights the entire printed
  Arabic amount. The other three invoice fields remain verified.
- Desktop and 375-pixel layouts in light and dark themes retain readable
  controls, no horizontal overflow and zero automated accessibility violations.
- Editing the total to `1234.56` preserves `234` as the original extraction and
  keeps its automated verdict separate from the human correction.
- JSON and CSV downloads work with the browser completely offline and produce
  no requests. Reconnecting gives identical server-export rows.
- Saving an archive, deleting its session and restoring it recomputes the same
  automated report while retaining the correction and export values.

Use a separately launched installed server and built demo with:

```sh
FIELDPROOF_BROWSER_URL=http://127.0.0.1:4350/ \
  UPDATE_ARABIC_NUMBER_SCREENSHOTS=1 \
  ./web/node_modules/.bin/playwright test \
  --config studies/arabic-numbers/browser.config.mjs
```

Set `FIELDPROOF_BROWSER_FULL=1` and `FIELDPROOF_DEMO_URL` to run all existing
live and demo cases. Detailed results and final screenshots are linked from
the [study](README.md); `results/verification.json` records final check counts.

All 102 distinct live/demo browser cases passed across the full sweep and
targeted reruns. The initial sweep passed 97. Three live cases failed around
a SIGTERM that stopped the local test server, including two explicit connection
refusals; two other cases exceeded the 30-second aggregate browser deadline.
After restarting the server, the exact five failed cases passed with
`--last-failed --timeout 90000`. The new flow used its final theme-button setup.
No functional assertions or application worker budgets were removed.
The [initial failures](results/initial-browser-failures.json) and
[complete case ledger](results/browser-sweep.json) retain this distinction.
The initial execution session ultimately reported SIGTERM (143), after logging
all 102 outcomes and its 97/5 summary. The five-case rerun and focused workflow
both completed with exit 0; the initial session is not recorded as a clean run.

The focused workflow passed in both engines, with eight layout/theme audits.
Its aggregate timeout is 90 seconds for four accessibility audits, exports and
two worker-backed imports; the application's 30-second PDF-worker budget is
unchanged. All eight final screenshots were opened and inspected. The controls,
complete amount highlight and mismatch reason remain visible, and the narrow
layout uses its existing Fields/Document tabs without horizontal overflow.

| Browser | Desktop light | Desktop dark | Phone light | Phone dark |
| --- | --- | --- | --- | --- |
| Chromium | [1440](../../docs/assets/arabic-numbers/chromium-1440-light.png) | [1440](../../docs/assets/arabic-numbers/chromium-1440-dark.png) | [375](../../docs/assets/arabic-numbers/chromium-375-light.png) | [375](../../docs/assets/arabic-numbers/chromium-375-dark.png) |
| Firefox | [1440](../../docs/assets/arabic-numbers/firefox-1440-light.png) | [1440](../../docs/assets/arabic-numbers/firefox-1440-dark.png) | [375](../../docs/assets/arabic-numbers/firefox-375-light.png) | [375](../../docs/assets/arabic-numbers/firefox-375-dark.png) |

The browser receipts retain the original and archive-restored reports, human
correction, exported rows, layout observations and the empty offline request
list: [Chromium](results/chromium-browser.json), [Firefox](results/firefox-browser.json).

## Boundaries and handoff

No model credentials or external document services were used. Full browser
review operations need the local server; the offline assertion covers the
already loaded view and its exports. Neither these controls nor the native
formatter establish general Arabic-script, OCR or real-invoice accuracy.
Space-grouped amounts remain a separate reproduced open issue,
`officina-fnld`; the tokenizer cannot infer column boundaries from whitespace.

The work is local. No push, tag, registry upload or Pages deployment was
performed. The existing pinned public install and static hosted demo do not
include this correction.

Suggested repository description (unchanged scope): "Review document extraction
against exact evidence, value checks and preserved human corrections."
Topics: `document-ai`, `pdf`, `grounding`, `python`, `data-integrity`, `llm`, `ocr`.
