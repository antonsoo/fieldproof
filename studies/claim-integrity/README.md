# Claims must not disappear before review

At baseline `d477aab676e24ff37b490b419f3ce417c9a69abd`, a synthetic invoice with
four ordinary claims produced **4 verified, 0 needs review, 0 unsupported**.
The same result appeared after adding a conflicting `total.value`, a conflicting
evidence quote, or an unsupported `bank_account` claim. JSON decoding retained
the last duplicate member; schema validation discarded unexpected fields.
The report therefore described only the surviving claims.

The server accepted those replacements and discarded a previously saved human
correction. An escaped lone surrogate also passed extraction validation before
breaking the server's JSON response. These are controlled malformed inputs,
not measured frequencies in real invoices or outputs from a live model.

## Before and after

`fixtures.py` creates a labelled synthetic PDF and 15 input cases. The replay
runs each through the actual CLI's extraction and in-place verification, and
through the server upload/extraction endpoints with an existing edited total.
Twelve cases also pass through the real Anthropic SDK's streamed Messages parser.
Its HTTP transport returns recorded synthetic text in 17-character deltas;
no external service or live model is called.

| Case | Previous behavior | Current behavior |
| --- | --- | --- |
| Duplicate value, evidence, entire field or escaped member name | Last member wins | Refused with decoded member path |
| Extra claim, line-item field or `Evidenced` member | Field discarded | Refused with schema error path |
| NaN or overflow to infinity | Non-finite value admitted to report data | Refused before validation |
| Escaped lone surrogate | CLI accepts; server response fails | Refused with explicit Unicode error |
| Five valid/default/BOM controls | Accepted | Accepted; CLI reports byte-identical |

[before.json](before.json) and [after.json](after.json) retain input hashes,
CLI exits/output, report counts and field paths, server outcomes and SDK-parser
outcomes. All ten malformed cases now fail fixture extraction with exit 1,
saved-result verification with exit 2 and server extraction with HTTP 422.
Existing CLI destinations, in-place source JSON and server reports/corrections
remain unchanged. A subsequent valid server import succeeds in every case.
All five valid controls retain their original report bytes.

The browser replay uses the real local server, synthetic PDF and file inputs.
It first refuses four malformed uploads with visible errors, then successfully
extracts the valid file and edits its total. Replacement extraction after review
is an API operation, not a control currently offered by the UI: the driver sends
those requests explicitly over HTTP, verifies the unchanged report/correction,
and downloads the reviewed JSON through the browser. It covers Chromium/Firefox
at 1440px dark and 375px light and compares served assets with the chosen build.
The phone screenshot exposed a Retry button wrapping into three lines beside
the error. Its flex item now keeps its natural width.

## Installed-artifact checks

[verification.json](verification.json) records a fresh 674-file archive of
implementation `89d7f21ee78ff1b2b8d65af42f409ca508b08ed9`, locked installation,
lint/type/format checks, both web builds, packaging and file hashes. All archived
tracked files remained unchanged. Each Python suite completed with 574 passes
and one skip because the Tesseract executable is unavailable.

| Environment | Pydantic | Anthropic SDK | Result |
| --- | --- | --- | --- |
| Source archive, Python 3.12.12, lockfile | 2.13.5 | 1.11.0 | Full suite and 15-case replay pass |
| Installed wheel, Python 3.11.13, lowest direct dependencies | 2.12.0 | 0.77.0 | Full suite and 15-case replay pass |
| Installed wheel, Python 3.11.13, current dependencies | 2.14.1 | 1.13.0 | Full suite and 15-case replay pass |
| Installed wheel, Python 3.14.7, current dependencies | 2.14.1 | 1.13.0 | Full suite and 15-case replay pass |

[installed-minimum.json](installed-minimum.json) and
[installed-current.json](installed-current.json) retain the installed replay
outcomes. All five valid report hashes match the baseline in every environment.
The wheel and source distribution contain the same 37 Python files and 23
bundled UI files as the checked build; all three installations match those files.
Package compatibility checks pass. These local artifacts retain version 0.2.7;
they are not the previously published PyPI artifact with that version.

The clean web run completed 62 unit checks and 86 production-browser checks.
The additional [installed-server browser replay](browser.json) passed all four
profiles with no observed page errors, external requests, CSP violations,
accessibility violations or horizontal overflow. It ran against a fresh
Python 3.14 wheel installation, not the source imports. Its eight screenshots
were inspected:

| Browser and viewport | Rejected import | Preserved correction |
| --- | --- | --- |
| Chromium, 1440px dark | [Error](../../docs/assets/claim-integrity/chromium-1440-error.png) | [Review](../../docs/assets/claim-integrity/chromium-1440-review.png) |
| Chromium, 375px light | [Error](../../docs/assets/claim-integrity/chromium-375-error.png) | [Review](../../docs/assets/claim-integrity/chromium-375-review.png) |
| Firefox, 1440px dark | [Error](../../docs/assets/claim-integrity/firefox-1440-error.png) | [Review](../../docs/assets/claim-integrity/firefox-1440-review.png) |
| Firefox, 375px light | [Error](../../docs/assets/claim-integrity/firefox-375-error.png) | [Review](../../docs/assets/claim-integrity/firefox-375-review.png) |

This is a local client/server workflow: third-party requests are blocked, but
the local API remains available. It is not an offline-server claim. Browser
versions are Chromium 153.0.8010.12 and Firefox 155.0, using Node 24.21.0 on WSL2
Linux. The final evidence commit does not modify tested runtime files.

## Validation boundary

The JSON decoder keeps object member pairs until their parent path is known.
It refuses decoded duplicate names (including escaped aliases), non-finite
numbers and strings or keys that cannot encode as valid UTF-8. Ordinary objects
are created only after those checks. Error paths use JSON Pointer escaping:
`/` becomes `~1` and `~` becomes `~0` within a member name. Separate objects may
of course each contain a member named `value`. UTF-8, UTF-8 BOM, and BOM-marked
UTF-16LE/BE inputs remain supported.

Schema validation uses `model_validate(..., extra="forbid")`. This applies to
nested models and wrappers without changing a caller's model configuration or
inventing a separate schema walker. Declared aliases and defaults remain
supported. [Pydantic introduced the per-call option in 2.12](https://pydantic.dev/articles/pydantic-v2-12-release#extra-configuration-per-validation),
so the declared minimum rises from 2.10 to 2.12. The lock retains 2.13.5; the
oldest-dependency check also exercises 2.12.0 with Python 3.11.

The controlled SDK replies deliberately violate the requested schema. Their
rejection tests the boundary after SDK stream assembly; it does not estimate
how often an actual provider would emit them. Refusal and truncated-output
handling remain separate. This change does not introduce arbitrary-precision
numeric models, infer semantic roles for a correctly quoted field, verify an
unknown schema member, or recover input a caller already dropped before invoking
Fieldproof. A deliberate custom model validator can transform input by design.
These are extraction-boundary checks, not a general JSON-losslessness claim.

## Replay

With the source development environment installed, choose new output folders:

```sh
uv run python studies/claim-integrity/replay.py /tmp/claims-after after --source .
uv run python studies/claim-integrity/browser.py --source . --python "$PWD/.venv/bin/python" --tools web --static web/dist --output /tmp/claims-browser
```

Build the source UI first with `cd web && npm ci && npm run build`. Browser
binaries must match the project's Playwright installation. `fixtures.py` is
only needed to regenerate the committed synthetic cases, not for replay.

For the baseline, archive the commit above to a separate checkout and use
`before --source PATH`. For an installed wheel, invoke `replay.py` with that
environment's Python and omit `--source`; its TestClient checks require the
development HTTP client dependency. The browser driver accepts `--installed`
and the installed package's static directory, and starts an actual local server.

For minimum installed dependencies, supply the wheel and every declared
runtime/dev/OCR requirement directly to `uv pip install --resolution
lowest-direct`; supplying only the wheel treats its dependencies as transitive
and does not exercise their declared floors. Finish installation before starting
checks, and do not let a source `uv run` replace a virtual environment in use.

The retained evidence covers source and local artifacts only. No PyPI release
or hosted deployment accompanies this change.
