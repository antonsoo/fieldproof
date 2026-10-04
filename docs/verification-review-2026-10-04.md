# Review workflow verification, 2026-10-04

Implementation tested: `4835438f349b1c17137952b0dcb4dd41e3f96082`.
This is the first-stage snapshot. The two open follow-ups below have since
been completed; see the [session, resource and PDF evidence report](verification-sessions-2026-10-04.md)
for the latest implementation and results.
All results below are local. This work has not been pushed, deployed, or
published as a package; the version remains 0.2.7 with an unreleased changelog.

## Behavior checked

Nested corrections preserve number, boolean, and string types. Approve and
Reject retain a correction; Reset restores the extracted value. Invalid edits
leave the previous decision intact. Corrections retain the original extraction
value, evidence, and verification verdict, and are visibly identified as human
changes that have not been automatically reverified.

Both demo and local-server downloads support reviewed-only and all-except-
rejected scopes. JSON preserves scalar types; CSV includes the same decisions
and provenance. Browser exports capture the visible review state and wait for
saves to finish. API export defaults remain compatible with existing clients.

Document replacement, cancellation, delayed responses, malformed reports,
blocked storage, and image failures were exercised. A failed replacement keeps
the previous valid document. Replies from an old document cannot replace the
current review. Phone review uses separate Fields and Document views; drafts,
selection, and keyboard focus survive navigation and relevant rerenders.

## Verification results

| Check | Result |
| --- | --- |
| Locked Python 3.12.12 and 3.14.7 suites | 143 tests passed on each |
| Python lint and types | Ruff clean; mypy clean across 26 source files |
| Fresh Node 24.21.0 / npm 11.19.0 install | `npm ci` passed; audit reported zero vulnerabilities |
| Web contracts | 43 Vitest tests passed; types, lint, and formatting passed |
| Production browser workflows | 42 passed across Chromium and Firefox, demo and local API |
| Accessibility | 30 axe scans; zero reported violations |
| Browser runtime and network assertions | Zero page errors, unhandled rejections, CSP violations, or off-origin page requests in the 42 workflows |
| Build reproducibility | All 32 files in each build matched between the working checkout on Node 26.7 and a fresh checkout on Node 24.21 |
| Installed wheel, Python 3.11.13 | 143 tests passed against installed code; all 23 bundled UI files matched the fresh production build by SHA-256 |
| Oldest direct dependencies, Python 3.11.13 | 143 tests passed; two dependency deprecation warnings |

The installed wheel served its root page and JavaScript successfully with the
expected Content Security Policy. The browser suite uses actual production
builds, real local fixture extraction/API requests, and downloaded JSON/CSV.
It checks desktop 1440 x 900, phone 375 x 812, and narrow phone 320 x 568 layouts,
both themes, keyboard inspection, edits, focus, recovery, and request races.
CI now runs the web contract and production browser suites; a remote CI run
was not performed for this local change.

Phone screenshots were inspected after the final implementation:

- [Fields at 320 x 568](assets/review-phone-fields-2026-10-04.png)
- [Document evidence at 320 x 568](assets/review-phone-evidence-2026-10-04.png)

## Reproducing the checks

From a clean checkout with Node 24 active:

```bash
uv sync --python 3.14 --locked --extra dev --extra ocr
uv run --python 3.14 --locked pytest -q
uv run --python 3.14 --locked ruff check src tests
uv run --python 3.14 --locked mypy src
cd web
npm ci
npm run typecheck
npm run lint
npm run format:check
npm test
npx playwright install --with-deps chromium firefox
npm run test:browser
```

Repeat the Python commands with `--python 3.12` to test that interpreter.
An explicit interpreter matters because the checkout pins 3.12 in
`.python-version`. For the minimum-dependency check, create a separate Python
3.11 environment and install `.[dev,ocr]` with `uv pip install --resolution
lowest-direct`, then run its `pytest`. For packaging, run
`uv run --python 3.14 --locked python scripts/bundle_ui.py` followed by
`uv build`, and install the resulting wheel in a separate environment.

## Local Beads evidence and limits

The tickets are in the local Officina Beads workspace, explicitly exported to
`.beads/issues.jsonl`.

| Ticket | Outcome |
| --- | --- |
| `officina-hzv` | Fixed typed/nested corrections, decisions, and exports |
| `officina-2yi` | Fixed stale document/load/review ownership |
| `officina-ayx` | Fixed blocked or damaged demo storage recovery |
| `officina-4ze` | Added progress, export scope, keyboard and phone review |
| `officina-rud` | Added repeatable production browser verification |
| `officina-ys6` | Fixed source checkout serving stale bundled UI assets |
| `officina-bw2` | Open: measure and bound PDF uploads and retained sessions |
| `officina-oiu` | Open: update the retired ESLint 9 toolchain |

These checks use synthetic PDFs and fixtures. They do not measure live-model
extraction accuracy or OCR quality. Cancel stops the browser's wait; server
work already accepted can continue. PDF/session memory limits remain an open,
unbenchmarked issue. The minimum-dependency run emitted Starlette/httpx and
AnyIO deprecation warnings; the current npm install warned that ESLint 9 is
retired, while its lint run passed and the audit reported no vulnerabilities.
