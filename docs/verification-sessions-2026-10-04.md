# Session, resource and PDF evidence verification, 2026-10-04

Implementation tested: `94c0c64b6f062045449d8bc192ab166f336e0d32`.
All results are local. The changes have not been pushed, deployed or published
as a package. Version 0.2.7 remains unchanged; the changes are unreleased.
This continues the [earlier review-workflow audit](verification-review-2026-10-04.md).

## Resulting behavior

The Sessions dialog reopens an uploaded document and its saved extraction,
corrections and decisions after a tab reload. It shows the occupied document
slots and offers explicit removal with confirmation. A correction draft must
be saved or cancelled before navigating away. A failed listing, removal,
upload or replacement extraction leaves the previous review available.
Capacity refusal never evicts a document. Sessions remain in memory until
removal or server restart; they are not durable storage.

PDF parsing, rendering and verification now run serially in disposable
subprocesses. Intake, queueing, retained documents and review payloads have
explicit budgets. The API remains responsive while a parser is busy, and a
worker timeout or resource failure releases its slot and temporary files.

| Resource | Local server budget |
| --- | --- |
| PDF file / multipart request body | 25 MiB / 26 MiB |
| Fixture file / multipart request body | 2 MiB / 3 MiB |
| Other API POST bodies | 64 KiB |
| PDF geometry | 64 pages; 16,000,000 pixels per page at 144 DPI |
| Extracted text per document | 100,000 words; 2,000,000 characters |
| Retained sessions | 8 documents; 100 MiB of PDF bytes; 200,000 words total |
| Extraction / corrections | 2,000 fields; 1 MiB of saved corrections per session |
| Pending work | 4 intake requests; 2 PDF uploads; 4 queued/running PDF or verification operations |
| Worker scheduling | One active process; 30-second queue wait and 30-second execution timeout |
| Linux worker resources | 768 MiB address space; 20 CPU seconds; 64 MiB output-file limit |

The streamed body cap also applies without a truthful Content-Length. PDF
capacity is reserved before reading the complete upload into memory. Stricter
inherited process limits are respected. Address space is not an RSS budget.
Windows receives the timeout and application limits without the Unix process
resource limits; Windows behavior was not tested here.

## PDF geometry bug and independent checks

A real PDF with MediaBox 612 x 792 and CropBox `(100, 200, 500, 700)` exposed a
coordinate mismatch: the original model reported the full 612 x 792 page,
while the rendered PNG represented the visible 400 x 500 crop, at 800 x 1000
pixels. Text at original x=150 should appear at visible x=50. The mismatch
stretched the document and placed evidence highlights over the wrong content.

The model now uses the rendered visible canvas after crop, MediaBox origin and
rotation. Only fully visible characters supply evidence. Word segmentation
follows the glyph baseline direction so rotated and counter-rotated words and
decimal numbers retain their logical order. Fractional pixel dimensions use
the renderer's ceiling.

The 23 geometry tests include 16 crop, shifted-origin and outside-CropBox cases
at 0, 90, 180 and 270 degrees. A red rectangle authored into each PDF supplies
an independent oracle: the tests assert its absolute location in the actual
PNG and require grounded word boxes to lie inside it. Other cases cover
counter-rotated text, fractional dimensions and clipped/hidden characters.
Both browsers also check the committed cropped PDF's natural image dimensions
and highlight position.

## Verification results

| Check | Result |
| --- | --- |
| Locked Python 3.12.12 and 3.14.7 suites | 203 tests passed on each |
| Python lint and types | Ruff clean; mypy clean across 30 source files |
| Oldest direct dependencies, Python 3.11.13 | 203 tests passed; two dependency deprecation warnings |
| Installed wheel, Python 3.11.13 | 203 tests passed against site-packages code |
| Packaged UI | All 23 files matched the fresh production build by SHA-256; root and JavaScript served successfully with the expected CSP meta element |
| Fresh Node 24.21.0 / npm 11.19.0 install | Clean install passed; npm audit reported zero vulnerabilities |
| Web contracts | 50 Vitest tests passed; types, lint and formatting passed |
| Production browser workflows | 56 passed across Chromium and Firefox, demo and local API |
| Accessibility | 34 axe scans; zero reported violations |
| Browser runtime and network assertions | Zero page errors, unhandled rejections, CSP violations or off-origin page requests in the 56 workflows |
| Build reproducibility | All 32 files in each web build matched between the working Node 26.7 checkout and fresh Node 24.21 checkout |

The minimum-dependency run includes Pydantic 2.10.0, FastAPI 0.133.0,
Anthropic 0.77.0 and PDFium 4.30.0. It caught unsupported PDFium context-manager
usage before completion; explicit closing now works at the declared floor.
The remaining warnings concern Starlette/httpx TestClient and AnyIO deprecations.

Resource checks include actual process memory, CPU and output-file enforcement,
inherited budgets, killed-worker recovery, timeout cleanup, bounded intake and
queues, malformed/scanned/oversized PDFs, fixture/field/correction limits and
preservation of the previous report after failed verification. Browser checks
cover reopening decisions after reload, deletion confirmation and retry, draft
protection, full-capacity recovery, keyboard focus, both themes and phone layouts.

The lint toolchain uses ESLint 10.12.0 and TypeScript ESLint 8.71.0. Before/after
config inspection confirmed all 24 configured rule severities and active rule
options were retained. The clean install no longer emits the ESLint 9 retirement
notice. Compatibility was checked against the official
[ESLint migration guide](https://eslint.org/docs/latest/use/migrate-to-10.0.0) and
[TypeScript ESLint dependency documentation](https://typescript-eslint.io/users/dependency-versions/).

Final screenshots were inspected at 320 x 568 and 1440 x 900:

- [Phone upload](assets/phone-upload-2026-10-04.png)
- [Phone extraction configuration](assets/phone-configure-2026-10-04.png)
- [Phone session recovery](assets/phone-sessions-2026-10-04.png)
- [Cropped PDF evidence](assets/cropped-evidence-2026-10-04.png)

## Measured disposable-worker behavior

One local Linux run on the tested implementation produced the following
results, including subprocess startup. Render time is for the first page.
The complete [measurement JSON](assets/server-resource-measurements-2026-10-04.json)
is retained alongside the reproducible script.

| Input | PDF bytes | Pages | Text words | Load seconds | Render seconds | Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Bundled invoice | 2,388 | 1 | 91 | 0.166 | 0.215 | Loaded |
| Bundled receipt | 2,105 | 1 | 58 | 0.165 | 0.165 | Loaded |
| Bundled contract | 3,007 | 2 | 184 | 0.166 | 0.216 | Loaded |
| Generated native PDF | 51,049 | 64 | 28,160 | 3.166 | 0.216 | Loaded |
| Generated image-only scan | 141,612 | 1 | 0 | 0.115 | 0.215 | Upload refused: no text layer |

The largest-child peak RSS was 143,928 KiB, about 140.6 MiB; the parent peak
was also 143,928 KiB. These are cumulative high-water marks over the run,
including startup/fork costs, not per-document memory deltas or worst-case
guarantees. The scan's rendering measurement calls the renderer directly;
the review server refuses its upload. The CLI's separate OCR fallback remains
available. No live provider call or OCR/extraction accuracy measurement was made.

## Reproducing the checks

From a clean checkout with Node 24 active:

```bash
uv sync --python 3.14 --locked --extra dev --extra ocr
uv run --python 3.14 --locked --extra dev --extra ocr pytest -q
uv run --python 3.14 --locked --extra dev --extra ocr ruff check src tests
uv run --python 3.14 --locked --extra dev --extra ocr mypy src
cd web
npm ci
npm run typecheck
npm run lint
npm run format:check
npm test
npx playwright install --with-deps chromium firefox
UV_PYTHON=3.14 npm run test:browser
cd ..
uv run --python 3.14 --locked --extra dev --extra ocr python scripts/measure_server_resources.py
uv run --python 3.14 --locked --extra dev --extra ocr python scripts/bundle_ui.py
uv build
```

Repeat the Python checks explicitly with 3.12; `.python-version` otherwise
selects that interpreter. For minimum dependencies, create an independent
Python 3.11 environment, install `.[dev,ocr]` with `uv pip install --resolution
lowest-direct`, and run that environment's pytest. For the wheel check, install
the wheel with `[dev,ocr]` into another independent 3.11 environment, confirm
`fieldproof.__file__` is under site-packages, and run pytest from the checkout.
The local browser servers stop when the suite finishes. Remote CI was not run.

## Local Beads evidence

All nine Fieldproof tickets from this maintenance effort are closed in the
local Officina Beads workspace and explicitly exported to `.beads/issues.jsonl`.

| Ticket | Completed work |
| --- | --- |
| `officina-hzv` | Typed corrections, decisions and auditable exports |
| `officina-2yi` | Ownership of asynchronous loads and review replies |
| `officina-ayx` | Recovery from blocked or damaged demo storage |
| `officina-4ze` | Review progress, export scope, keyboard and phone controls |
| `officina-rud` | Production browser checks in both engines |
| `officina-ys6` | Fresh source UI takes precedence over stale packaged assets |
| `officina-bw2` | Measured and bounded PDF work; explicit session recovery and removal |
| `officina-oiu` | ESLint 10 migration with existing rules retained |
| `officina-8jw` | Correct visible-page evidence coordinates and logical rotated text |
