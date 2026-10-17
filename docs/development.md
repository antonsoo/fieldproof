# Development

The [evidence guide](evidence-guide.md) links retained source, installed
artifact and browser records. Each study identifies its verified revision;
older counts are historical, not a statement about the current checkout.
Use Node 24 or newer for the web toolchain.

```bash
uv sync --extra dev --extra ocr
uv run pytest
uv run ruff check src tests
uv run mypy src

cd web
npm ci
npm run typecheck
npm run lint
npm run format:check
npm test
npx playwright install chromium firefox   # once per machine
npm run test:browser                       # builds demo + local UI, tests both
```

`fieldproof serve` from a checkout serves `web/dist`. For a release,
`uv run python scripts/bundle_ui.py && uv build` builds the UI into the
package first, so the wheel carries it.

The production browser suite runs the bundled synthetic samples and the real
local PDF/fixture API in Chromium and Firefox. It covers typed corrections,
JSON/CSV downloads, stale replies, cancellation, storage failures, malformed
data, retries, keyboard focus and desktop/phone layouts in both themes. Every
workflow checks for page errors, CSP violations and off-origin requests; the
accessibility workflows use axe. No live model call is required. Local preview
and API servers use fixed loopback ports 4290 and 4289 and stop after the suite.
Cancellation stops waiting in the UI; work already accepted by the local server
can continue.

To measure the disposable PDF workers on Linux with the bundled samples, a
generated 64-page native PDF and an image-only scan:

```bash
uv run --extra dev --extra ocr python scripts/measure_server_resources.py --out measurements.json
```

The output records single-run timings and cumulative process RSS high-water
marks. It is a local measurement, not an accuracy or worst-case performance claim.

Regenerate the sample documents and demo data after changing them - the
output (`web/public/demo-data/`) is committed, since the Pages deploy is a
plain `npm ci && npm run build:demo` with no Python step:

```bash
uv run python scripts/generate_samples.py
uv run python scripts/build_demo_data.py   # writes + commit web/public/demo-data/
```

