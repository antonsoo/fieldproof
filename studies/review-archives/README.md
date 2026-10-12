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
