# Reviews that can be reopened

The baseline is `f11b663a1a4abe434fb8f06c5ee963a3913f0ef2`. Its in-memory
sessions survive a tab reload, but not a server restart. JSON/CSV/XLSX exports
retain chosen values; they cannot reopen the original document review.

This study uses the repository's **synthetic** invoice, receipt, contract and
line-arithmetic PDF/fixture pairs. No live model or real customer document is
used. It evaluates recovery, not extraction accuracy or reviewer judgment.

| Workflow | Baseline | Archive implementation |
| --- | --- | --- |
| Old session after an actual server restart | 404 for all four | Still 404; new sessions have new IDs |
| Download a review archive | 404 for all four | PDF, claims and all decisions saved |
| Open archive on an empty server | 404 for all four | All four restored without a model call |
| Recomputed report and human decisions | Not recoverable | Equal to the pre-restart report/decisions with the same verifier |
| API JSON, CSV and XLSX exports | No restored session | Before/after bytes equal in all three formats for all four documents |
| Page rendering after recovery | No restored session | Page 1 rendered for all four documents |

`before.json` and `after.json` retain the HTTP results and PDF hashes.
The input artifacts remain in `examples/`; candidate extractions are in
`examples/fixtures/`. The contract has two pages, while this API replay renders
only its first page. Automated reports are recomputed, not copied from the ZIP.

The retained after replay uses an independently installed wheel on Python
3.12.12. [`after-python311.json`](after-python311.json) repeats the four-document
restart on Python 3.11.13. Both import the package from isolated `site-packages`,
with all 36 Python source files matching the tested implementation.

## Browser workflow

`browser.py` starts a real server, runs four browser workflows, terminates it,
starts an empty server, then reopens the actual downloaded ZIP files in new
browser contexts. Chromium and Firefox each run at 1440 pixels in dark mode
and 375 pixels in light mode. Each uses the synthetic invoice and makes four
decisions: one approval, two corrections (`00042` and numeric `123.5`), and one
rejection, leaving the other fields pending.

The replay downloads JSON, CSV, XLSX and an archive both before and after the
restart: 32 actual browser downloads. It checks that each format's bytes match
across the restart, that original claims and all 25 field decisions match,
and that the rendered PDF and evidence highlights return. Browser JSON rows
are also compared with the API semantically; the two JSON serializers need
not use the same whitespace. API and browser XLSX files are separate writers,
so the study compares each writer's output to itself across the restart.

Every served HTML/CSS/JavaScript/font response is byte-compared with the
specified build directory. External requests are blocked and recorded; local
API requests remain necessary. This is a local-server workflow, **not** an
offline static demo. The replay checks page errors, CSP violations, axe and
horizontal overflow. It captures the reopened review at each viewport.

That broader dark-mode check also exposed an existing unsupported badge with
4.3:1 contrast (`#e2685c` on `#33282b`). The dark foreground is now `#f07a6f`;
the replay checks its rendered state along with the new archive controls.

The retained [`browser-save.json`](browser-save.json) and
[`browser-restore.json`](browser-restore.json) come from the installed wheel.
All six served assets per browser context match the package's static files;
all 23 bundled files match the earlier source build. No page/CSP errors,
external requests, axe violations or horizontal overflow were observed in
these eight workflows. All four final screenshots were visually inspected:
[Chromium desktop](../../docs/assets/review-archives/chromium-1440.png),
[Chromium phone](../../docs/assets/review-archives/chromium-375.png),
[Firefox desktop](../../docs/assets/review-archives/firefox-1440.png),
[Firefox phone](../../docs/assets/review-archives/firefox-375.png).

## Clean package and independent ZIP tools

Implementation commit `28dead8c58124c37eadd07d5582cac0c45f2c1f6` was unpacked
into a clean directory; all 619 tracked files matched before and after checks.
The fresh Python/Node 24 installation passed lint, type checks, formatting,
536 Python tests, 62 web contract tests, both production builds and 86 browser
workflows. One optional real-Tesseract test was skipped because the executable
was unavailable. The wheel was built through the source distribution, then
installed into separate Python 3.11 and 3.12 environments. Its local version
number remains 0.2.7; it was not uploaded to a registry.

[`verification.json`](verification.json) records commands, runtime versions,
the wheel size/hash and scope. Info-ZIP's independent `unzip` reader passed
all four generated archives' CRCs, hashes and exact original PDF bytes
([receipt](zip-tools.json)). Its `zip` writer then repacked those members with
deflate compression. All four repacks restored through the installed Python
3.11 server and re-saved to the original stored ZIP bytes
([receipt](zip-restore.json)).

The `save_ms` and `restore_ms` values are single observations on these small
synthetic files, on 14 vCPU WSL2 Linux with 48 GiB RAM. They are not a latency
guarantee for other PDFs or machines. Initial replay-harness errors concerned
a missing URL slash and an incorrect expectation that API and browser JSON
whitespace matched; the final scripts normalize the URL and compare JSON
semantically across writers. The dark badge contrast issue was fixed in the UI.

## Run it

From a prepared source checkout with Python development dependencies and the
web dependencies installed:

```bash
uv run --locked python studies/review-archives/restart.py \
  --source . --python "$PWD/.venv/bin/python" --output /tmp/fieldproof-restart/after.json
npm --prefix web run build
uv run --locked python studies/review-archives/browser.py \
  --source . --python "$PWD/.venv/bin/python" --tools web --static web/dist \
  --output /tmp/fieldproof-restart/browser
```

Use `--source` with the baseline checkout for the before API replay, while
keeping `--python` pointed at a compatible interpreter with the dependencies.
For an independently installed wheel, add `--installed` to either script,
point `--python` at that environment, and give the browser script the wheel's
actual bundled static directory. `--source` then supplies only example files.
The subprocess removes `ANTHROPIC_API_KEY`; installed mode also removes
`PYTHONPATH` and the static-directory override. The browser tools stay in
`--tools`, so the installed app does not need Node at runtime.

`tests/test_archives.py` separately checks malformed ZIPs, member checksums,
duplicate JSON keys, schema incompatibility, correction types, resource limits,
capacity refusal and fresh verification. The browser regression checks failed
saves, cancellation, an invalid ZIP and reopening the existing session afterward.

## Limits

The archive is an editable, unencrypted snapshot, not an authenticated audit
log or an automatic backup. It carries the entire source PDF. The old automated
report is not stored; a later verifier may reach different conclusions from
the same claims. A lost response can leave a completed restore in Sessions.
See the [format and recovery guide](../../docs/review-archives.md) for exact
limits and supported schemas. No hosted demo or registry release is implied.
