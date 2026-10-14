# Native text and scanned pages in one PDF

At source `d2ed381946c956d153d5150b5fd61c95317953bf`, a PDF with any native text
used only the native loader. OCR fallback worked when every page lacked text.
In the controlled mixed invoice, the header remained usable but its image-only
totals page supplied no words: three fields verified and three were unsupported.
This was a documented limitation, not a claim that those totals were verified.

The source adds an explicit `--ocr-missing-pages` option to `extract` and `verify`.
Native pages retain their words, offsets and boxes. Pages without native words
go through local Tesseract, with their original page numbers retained. The
library entry point is `fieldproof.document.ocr.load_pdf_with_ocr`.

```bash
fieldproof extract studies/mixed-page-ocr/inputs/mixed.pdf --fixture studies/mixed-page-ocr/inputs/mixed.json --ocr-missing-pages --out /tmp/mixed-result.json
fieldproof verify /tmp/mixed-result.json studies/mixed-page-ocr/inputs/mixed.pdf --ocr-missing-pages
```

Use an installation built from this source with its OCR extra and a working
Tesseract/English data installation. These commands need no API key or model.

## Actual recognition

The producer authors native invoice headers and rasterizes three totals at
144 DPI into image-only PDF pages. These are synthetic, clear typeset inputs,
not camera/scanner samples or an OCR benchmark. The native, mixed, scan-first,
blank-interstitial and all-scanned inputs and hashes are retained. The fixture
extractor replays known claims; no model is called.

| Controlled input | Default supported / unsupported | Per-page OCR supported / unsupported |
|---|---:|---:|
| Native header and native totals | 6 / 0 | 6 / 0 |
| Native header and scanned totals | 3 / 3 | 6 / 0 |
| Scanned totals before native header | 3 / 3 | 6 / 0 |
| Native header, blank page, scanned totals | 3 / 3 | 6 / 0 |
| Scanned totals only; no header claims supported | 3 / 3 | 3 / 3 |

Mixed-document provenance adds `processed_pages`, including blank pages attempted
by OCR. `page_count` still names the whole document and `empty_pages` retains
blank recognition. An absent `processed_pages` keeps the legacy whole-document
OCR meaning. Native-only reports still omit `ocr`.

`replay.py` runs both real CLI commands in default and opt-in modes, plus actual
missing-engine/data failures. The [baseline captures](results/before/results.json)
retain ten default workflows. Existing default report bytes are compared with
the new source, rather than assuming compatibility from successful exits.

`oracle.py` compares every native page with `load_pdf` and recognized words/boxes
with direct [Tesseract TSV](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html#tsv-output).
That checks retention, offsets and pixel-to-point conversion using the same
recognizer; it does not independently establish recognition accuracy. It also
exercises combined budgets and an actual one-microsecond recognition timeout.
The [pytesseract floor interface](https://github.com/madmaze/pytesseract/blob/v0.3.10/README.rst)
documents the TSV, language and timeout calls used here.

```bash
uv run --extra dev --extra ocr python studies/mixed-page-ocr/make_inputs.py
uv run --extra dev --extra ocr python studies/mixed-page-ocr/replay.py --python "$PWD/.venv/bin/python" --out /tmp/mixed-replay
uv run --extra dev --extra ocr python studies/mixed-page-ocr/oracle.py --out /tmp/mixed-oracle
```

The replay can use an independently installed interpreter and `--source` for an
older archive. [Installed verification](verification.md) records the builds,
engine provenance and precise scope.

## Boundaries

The mode is explicit because native empty pages may be intentional blanks and
recognition requires optional dependencies and work. It does not replace pages
that already contain words, detect partial/bad OCR text layers, deskew or infer
missing field semantics. Default native behavior and the review server's path
remain as before; the server does not gain an OCR option here.

The new path applies the existing 64-page, 16-million-pixel/page, 100,000-word and
two-million-character budgets to the combined document. Each engine call has
the configured positive timeout; rendering is not sandboxed and this is not a
whole-job deadline. Missing dependencies, engine/language failure or a later
recognition error produces no partial report and preserves the previous output.

Six supported fields here mean agreement with recognized/native evidence under
existing checks. OCR can still read a plausible wrong number. Blank recognized
pages remain explicit, and no document-wide completeness or visual correctness
is inferred from the field counts.
