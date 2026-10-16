# A printed 90 must not verify a hidden 900

At published baseline `2fb1cdb5b381f0b6c95b94c131431a60be3b6156`, a PDF could
show `Authorized total: $90.00` as an image over native text saying `$900.00`.
Fieldproof verified the hidden 900 and highlighted pixels displaying 90.
White-on-white text, opaque overpainting and patterned covers produced the same
false confidence without using invisible rendering modes or zero opacity.

These are authored synthetic inputs with declared expectations, not a measurement
of real-world prevalence or extraction accuracy. The **Hidden text** sample in
the existing static demo makes the mismatch inspectable without credentials.

## Observed change

| Check | Published baseline | Repaired source |
|---|---:|---:|
| Hidden amounts incorrectly verified | 20 | 0 |
| Visible control claims verified | 82 / 82 | 82 / 82 |
| Claims matching declared verdict | 82 / 102 | 102 / 102 |

The [34 retained PDFs](fixtures/) include equal foreground/background colors,
white ink on black and blue, black on yellow, opaque paths and images, a printed
90 covering native 900, patterned covers, visible text over a pattern, even-odd
clip holes, one hidden digit, mixed colors, 8/16/24-point text, A4, page rotations
and CropBox offsets. [Before](results/before.json) and [after](results/after.json)
retain input hashes, word states, geometry, actual verdicts, quotes and reasons.
The replay round-trips each document through worker-shaped JSON first.

[Independent pixel checks](results/pixels.json) compare each renderer with its
own reference PDF omitting the relevant native ink. All **68 PDFium/Poppler
comparisons** agree with the declared visible/hidden state. A partially hidden
amount omits just its hidden digit in that reference. No renderer-to-renderer
antialiasing equality is assumed. All 34 frozen PDFs regenerate byte for byte;
the generator derives PDFium's save-time trailer identifier deterministically.

## Method and boundaries

For a native page needing an audit, the loader renders the original at 144 DPI.
It opens a separate reference from the same source, verifies that its untouched
render matches the original, then changes native text rendering modes in that
reference only: paint modes 0/1/2 become invisible 3, and paint-and-clip modes
4/5/6 become clip-only 7. Existing 3/7 remain nonpainting. Nested and reused Form
objects are traversed once per native object; clipping, paths and images remain.
The API contract is documented in the [PDFium editing header](https://raw.githubusercontent.com/chromium/pdfium/main/public/fpdf_edit.h).
The original PDF and its render objects are never edited.

The difference between original and suppressed renders is sampled inside each
character's layout rectangle, rounded inward to complete pixels. Rounding
outward can borrow a neighboring glyph's antialiased edge and falsely approve a
hidden digit. If any character in a word has no contribution, the original word
requires review without changing its text, spaces, offsets or rectangle.

A page is bounded to 16 million pixels per frame by default (or the supplied
intake limit), 50,000 visited objects and Form depth 32. Unsupported objects,
failed mode changes, inconsistent reference renders, exceeded budgets and
subpixel/no-area character regions remain **unavailable**, never clean. Native
records serialized before this audit remain unchecked and require review.
Explicit invisible/zero-opacity/clipping risks keep their existing reasons.
Affected words cannot establish number/date conventions, row anchors or table
column roles, and edit tolerance cannot waive the observation. Recognized OCR
and manually supplied words keep their existing policy.

This is a bounded contribution check, **not proof of readability or identity**.
A positive regional difference may come from overlapping native text; font
character mappings may lie; tiny differences do not establish legibility. Text
used only to clip later paint can be readable but still require review. Partial
clipping, unusual glyph metrics or tiny text can conservatively require review.
A renderer bug or unsupported PDF feature can also affect the observation. The
original page and claim remain available for human inspection.

## Processing cost and compatibility

[Before](results/scaling-before.json) and [after](results/scaling-after.json)
measure authored 1/10/50-page ledgers in separate processes, with one warmup and
three timed loads. Source bytes and extracted text/geometry hashes match in
every row. All 22,700 words in the largest case have a positive contribution.

| Pages | Words | Before median, s | After median, s | After process peak RSS, MiB |
|---|---:|---:|---:|---:|
| 1 | 454 | 0.058 | 0.180 | 94.1 |
| 10 | 4,540 | 0.658 | 1.387 | 94.8 |
| 50 | 22,700 | 3.319 | 8.377 | 105.7 |

These observations include parsing, three page renders and character checks.
The later run had a higher machine load; they are not controlled universal
latency or memory guarantees. The original render, reference and difference
buffers are disposed per page. Server work remains in disposable processes with
its existing time, memory and output limits.

All ten pre-existing example PDFs keep their text, geometry and report hashes:
[before](results/examples-before.json), [after](results/examples-after.json).
The new eleventh example deliberately has a reviewable hidden claim. The static
demo data is regenerated from current verification reports, including existing
column-check details. The sample chooser now wraps as samples are added, keeping
all five choices available at phone widths without horizontal page overflow.

The [installed worker observation](results/worker.json) loads a 64-page,
29,056-word ledger in 6.9 seconds and renders its first page in 0.27 seconds,
within the existing 30-second wall, 20-second CPU and 768-MiB address-space
limits. Every loaded word has a positive contribution observation. The largest
child process's observed peak RSS is 144.4 MiB. These are one local run's
observations, not guarantees for arbitrary 64-page PDFs.

## Reproduce

```sh
uv sync --locked --extra dev --extra ocr
uv run python studies/flat-raster/replay.py /tmp/paint-after.json --check
uv run python studies/flat-raster/pixels.py
```

The independent check needs Poppler's `pdftoppm`; replay needs only the retained
PDFs. `generate.py` recreates the fixtures and demo PDF. `scaling.py --output
/tmp/paint-scaling.json` recreates the timing study. To replay the baseline,
point `PYTHONPATH` to that revision's `src` while keeping dependencies unchanged.

The ordinary CLI needs no model or OCR engine:

```sh
uv run fieldproof verify studies/flat-raster/extraction.json \
  studies/flat-raster/fixtures/image-prints-ninety.pdf --out /tmp/paint-report.json
```

For browsers, build the bundled UI and wheel using `scripts/bundle_ui.py` and
`uv build`; launch the installed server and serve `web/dist-demo` separately.
Set `FIELDPROOF_BROWSER_URL`, `FIELDPROOF_DEMO_URL`,
`FIELDPROOF_BROWSER_FULL=1`, and optionally `UPDATE_RASTER_SCREENSHOTS=1`, then
run Playwright with `--config ../studies/flat-raster/browser.config.mjs` from
`web/`. Live checks exercise actual worker extraction, correction, export and
archive restoration. The static demo consumes generated reports; it does not
run the native PDF loader in the browser.
