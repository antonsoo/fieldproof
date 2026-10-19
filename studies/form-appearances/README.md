# Filled PDF forms must not appear blank in review

At source `d93ab59`, Fieldproof rendered page annotations without initializing
PDFium's form environment. A saved text field displayed its empty box; checked
boxes and selected choices could also disappear. The review image and the image
sent to local OCR therefore omitted saved widget appearances.

The source repair initializes static AcroForm rendering before acquiring page
handles. Review PNGs, OCR input and both sides of the native-text paint audit
use the same form environment. Original PDF bytes are never rewritten.
The form environment has no JavaScript platform and disables XFA. XFA documents
are rejected with an explicit diagnostic, including through the server worker.

## Authored controls

All 14 [PDFs](fixtures/) are invented ReportLab experiments, not transactions.
[`generate.py`](generate.py) and [`cases.json`](cases.json) retain the construction
and source hashes. [`replay.py`](replay.py) compares real review pixels with an
explicit direct PDFium form render and retains the native document/claim results.

| Observation | Before | Corrected source |
| --- | --- | --- |
| Review mismatch, 13 supported controls | 10 | 0 |
| Visible native `$42.00` claim, 12 controls with native text | Verified | Verified |
| Native `$900.00` behind the `$100.00` widget | Needs review | Needs review |
| Hidden text field | Hidden | Hidden |
| Unchecked box and native-only control | No form-render effect | No form-render effect |
| Form-only page, actual local Tesseract | No recognized words | `$100.00`, with its word box |
| XFA control | Accepted as a static page | Explicitly rejected |

Controls include a selected choice, checked/unchecked boxes, empty/hidden text,
90/180/270-degree rotation and a CropBox. Rotation fixtures keep the full source
content inside the MediaBox before applying rotation. The replay also checks
worker JSON round trips and unchanged fixture bytes.

The native loader still extracts page text, not form-field values. Displaying
`$100.00` does not create a native quote occurrence for it. A page containing only
widgets still takes the optional OCR path; recognized words retain OCR provenance.
The mixed-page option does not OCR pages that already contain native words.

## Public producer inputs

[`public.py`](public.py) checks the unchanged LibreOffice 6.4 and pdfTeX-1.40.23
controls from [py-pdf/sample-files at 02b8203](https://github.com/py-pdf/sample-files/tree/02b8203bf416db3dbdb03438bc8278dfcb0555f3).
The LibreOffice example already contains the saved values `Alice` and `Bob`.
The replay additionally fills the pdfTeX `Name` field with the invented text
`Example Form`, using pypdf 6.21.1. All three review images disagree with the
explicit form renderer before the repair and agree afterward.

Poppler independently renders these same PDF bytes. The optional `--ocr` path
retains actual Tesseract reads of both renderers, including errors: it reads
`Alice` in the corrected LibreOffice view and in Poppler's view, but does not
reliably read the second field or the small pdfTeX fields. The saved `Bob`
appearance is visibly clipped. Neither the field dictionary nor a positive
render difference establishes that the full value is readable.

These are producer examples, not a prevalence or recognition benchmark. Upstream
PDFs and their derived renders are CC BY-SA 4.0; [attribution](NOTICE.md).
Only authored MIT fixtures are retained in this repository; public PDFs/renders
stay in the replay's temporary directory.

## Reproduce

From the checkout, with Tesseract and English data installed for the OCR step:

```sh
uv sync --locked --extra dev --extra ocr
uv run --locked --extra dev python studies/form-appearances/replay.py /tmp/form-views
uv run --locked --extra ocr python studies/form-appearances/ocr.py /tmp/form-ocr
```

Public controls require the pinned sample checkout and the optional study reader:

```sh
git clone --filter=blob:none --sparse https://github.com/py-pdf/sample-files /tmp/form-samples
git -C /tmp/form-samples checkout 02b8203bf416db3dbdb03438bc8278dfcb0555f3
git -C /tmp/form-samples sparse-checkout set 010-pdflatex-forms 012-libreoffice-form
uv run --locked --extra dev --with pypdf==6.21.1 python studies/form-appearances/public.py \
  /tmp/form-samples /tmp/public-form-views --ocr
```

`--ocr` also requires `pdftoppm`. Without it, the public replay still compares
every review image to direct PDFium rendering and retains source/field hashes.
No new runtime dependency is needed for the product repair.

The [PDFium wrapper's API](https://pypdfium2.readthedocs.io/en/stable/python_api.html#pypdfium2.PdfDocument.init_forms)
requires form initialization before page acquisition. PDFium's
[form-fill header](https://pdfium.googlesource.com/pdfium/+/main/public/fpdf_formfill.h)
documents the null JavaScript platform and XFA-disabled configuration.

Package metadata remains 0.2.7. This is source work, separate from a PyPI release
or changes to either hosted demo.
