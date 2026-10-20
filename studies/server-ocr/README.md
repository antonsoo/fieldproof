# Local OCR review, exports and recovery

The review server at source `37084b8b399b183f6bc4a66f32573f319f0737a6`
rejected an image-only PDF even when the CLI could OCR it. The retained
[before response](results/before-scan.json) is HTTP 422 on the exact credited
CORD receipt now included here. This work connects the existing recognizer to
local upload, page review, value exports and recoverable archives.

## Concrete behavior

| Input | Native | OCR scanned pages | OCR every page |
| --- | --- | --- | --- |
| CORD v2 test row 0, real receipt photo | 422: no native words | Review opens; total stays needs review | Same recognition and verdict |
| Saved form, visible 100 over native 900, authored control | Original 900 claim needs review | Keeps native layer; 900 still needs review | Recognizes visible 100; original 900 still needs review |
| Two-page authored invoice: native header, image-only total | Total unsupported | Header uses native words; total uses OCR on page 2 | Both pages use OCR; total located on page 2 |
| Nine-page authored native document | Accepted | Not run in this replay | 413: OCR page budget |
| Blank authored page | Not run in this replay | Not run in this replay | 422: no recognized words |

The saved-form control is corrected to 100 in every reviewed replay, retaining
its original 900 and `needs_review` verdict. Approval is a human decision; it
does not convert an automated OCR verdict into a claim about the printed page.
Other replay approvals exercise decision transport, not an accuracy assessment.
The CORD total quote includes the printed line context so it locates the total,
rather than a repeated card-payment amount.

`results/capture.json` records 12 actual API cases. Eight accepted reviews save
archives, clear the in-memory store, restore, and compare the full reports,
decisions and exported rows. No model or remote recognition service is called.
The reference executes native Tesseract TSV directly, bypassing pytesseract,
Fieldproof's document conversion and the API. All 106 recognized words and
coordinates on six OCR pages match. It uses the same 144 dpi PDFium rendering;
this checks word transfer and coordinate conversion, **not** OCR accuracy or
an independent rasterizer.

`results/native-compatibility.json` compares an original invoice and human
correction against the isolated previous source. The report, both JSON/CSV/XLSX
scopes, and native version-1 archive are byte-identical. The old/new browser
export functions likewise emit identical JSON, CSV and XLSX bytes. This is one
concrete compatibility workflow, not a promise about every possible input.

## Data and limits

The receipt image and supplied annotations are **CORD / NAVER CLOVA,
CC BY 4.0**. [Source, changes and attribution](../../examples/recorded/cord/NOTICE.md)
and [exact input hashes](../../examples/recorded/cord/source.json) travel with
the sample. `fixtures/cord-ground-truth.json` retains the dataset annotations
under that same license. The extraction fixture is authored; no model output
or extraction benchmark is represented. The source image's header was already
redacted, so merchant and date remain empty and unsupported.

`prepare_receipt.py` verifies the pinned Parquet and image hashes, creates an
image-only PDF, and compares its embedded RGB pixels with the unchanged source.
With the recorded ReportLab 5.0.1 it also reproduces the PDF bytes exactly.
`produce_controls.py` generates labelled synthetic page and mixed-source controls.
The saved-form PDF comes unchanged from the earlier form-appearance study.

Native remains the default and permits 64 pages. Both explicit OCR choices
permit at most 8 pages, use English and 144 dpi, and impose a 10-second page
recognizer limit within the existing 30-second worker wall-clock budget.
The worker queue, document limits and Linux memory/CPU limits still apply.
The API can refuse a document below 8 pages if another budget is exceeded.
A POSIX timeout kills the process group, including Tesseract descendants; a
real parent/child timeout check exercises this. The Windows `taskkill /T` path
has not been exercised on Windows.

Missing-page mode preserves pages with any native words. It cannot repair a
partial or deceptive layer on those pages. All-page mode deliberately replaces
native evidence and may introduce recognition errors. The source notice,
per-page origin and export columns keep that distinction visible. Native
exports retain seven columns; OCR choices append `text_mode` and `text_source`.
Corrected rows keep the source of their **original evidence**.

Version-2 archives record the processing choice, not cached words or a verdict.
Restore needs the OCR tools and runs recognition again. Version-1 native saves
and reads remain supported. Neither format authenticates decisions.

## Reproduce

Use Node 24+, the checkout's locked Python dev/OCR environment, Tesseract and
English language data. The optional pyarrow dependency is only for producing
the recorded sample, not Fieldproof's runtime:

```bash
uv sync --locked --extra dev --extra ocr
uv run python studies/server-ocr/produce_controls.py
uv run --with pyarrow==26.0.0 python studies/server-ocr/prepare_receipt.py \
  --parquet /path/to/the/pinned/test.parquet --out /tmp/cord-prepared
uv run python studies/server-ocr/capture.py --out /tmp/server-ocr --demo
cd web && npm ci && npm run build && npm run build:demo
```

The Parquet URL and hash are in `source.json`; the existing CORD study's local
cache can be used instead of `--parquet`. `--demo` writes only the new attributed
example. It does not regenerate or alter the five existing examples.

Start `FIELDPROOF_STATIC_DIR=web/dist uv run fieldproof serve --port 7897` from
the checkout. In another terminal run:

```bash
node studies/server-ocr/browser.mjs --url http://127.0.0.1:7897/ --out /tmp/ocr-browser
```

The browser replay downloads actual files, parses the workbook XML and compares
typed cells with JSON, checks source notices and mixed-page navigation, edits
the saved form, exports offline, and restores archives into an empty store.
It uses Chromium and Firefox at 1440 and 375 pixels. The browser's store reset
is explicit deletion, not a server-process restart; installed-package recovery
is reported separately. The static demo branch of this script uses `--demo`
and a URL ending in `/fieldproof/`. Hosting a static sample does not install
an OCR backend or publish a registry release.
