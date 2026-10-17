# A replacement glyph cannot verify the covered original

On source baseline `621e738`, the PDF below visibly says `$100.00`, while
Fieldproof verifies the extraction's `$900.00` claim. The author drew native
`Authorized total: $900.00`, covered the nine with an opaque white rectangle,
and drew a smaller native one in its place. Extracting the original quote is
still possible. The old raster check found native-text pixels in every
character's rectangle, including the replacement one's ink inside the old
nine's bounds.

![Actual original browser: rendered 100, extracted 900, verified](../../docs/assets/overlapping-text/before-chromium-1440.png)

These invoices are authored synthetic counterexamples, with no real payment or
measured production prevalence. [generate.py](generate.py) retains their source;
the PDFs and extraction are usable without a provider or OCR engine.

| Authored cases | Before | After |
| --- | --- | --- |
| Four replacement sizes, three rotations, crop, nested Form | 9 falsely verified | 9 need review |
| Original, nonpainting/transparent/nearby lender, tight tracking | 5 verified | 5 verified |

[Before](results/before.json) and [after](results/after.json) retain every verdict,
reason, word and rectangle. Source bytes, extracted text, word boundaries,
offsets and geometry match across the replay. The original browser reproduction
is retained separately in [before-browser.json](results/before-browser.json).

The independent [pixel check](pixels.py) renders each original and an authored
control in which the old nine was never painted. For the nine affected pages,
each renderer produces byte-identical RGB pixels for the pair. The five visible
controls change when the nine is omitted. All [28 checks](results/pixels.json)
pass across PDFium and Poppler at 144 DPI. The comparison is within each engine;
the engines need not rasterize fonts identically to one another.

## Correction and boundaries

Fieldproof retains the original-versus-text-suppressed raster comparison. It
also records the union and overlaps of potentially painting native characters'
layout bounds in two one-bit masks. Bounds round outward for the overlap mask;
the character's observation still rounds inward to complete pixels. A character
needs some observed contribution outside the overlapping regions. If all its
observed paint lies inside another character's bounds, the word records
`raster_state: "ambiguous_overlap"` and requires review with a specific reason.

This is a conservative attribution check. It does **not** identify which glyph
painted a pixel or read the rendered amount. Legitimate duplicate overprinting,
stacked marks, tiny glyphs and unusual font metrics can require review too.
Visible text elsewhere is retained. Unpainted and explicitly transparent glyphs
cannot supply paint, while partially cropped and clipping-risk glyphs can;
the audit includes those even when word extraction discards them.

Overlap work is bounded to 50,000 potentially painting characters and 64 million
accumulated rectangle pixels per page, in addition to the existing raster/object
limits. Exhaustion or invalid geometry leaves attribution **unavailable**. The
two masks are disposed per page. Words requiring review cannot establish number
or date conventions, row anchors or column headings; edit tolerance does not
remove the paint reason. Recognized OCR and manually supplied words retain their
existing policy.

The [compatibility replay](compatibility.py) checks all eleven existing example
PDFs against the original source. Their source hashes, text, geometry and complete
verification report hashes are identical:
[before](results/examples-before.json), [after](results/examples-after.json).

## Reproduce

```sh
uv sync --locked --extra dev --extra ocr
uv run python studies/overlapping-text/replay.py /tmp/overlap-after.json --check
uv run python studies/overlapping-text/pixels.py
```

`pixels.py` additionally needs Poppler's `pdftoppm`; the application does not.
`generate.py` recreates the retained inputs. To replay the old behavior with the
same dependencies, archive baseline `621e738` and set `PYTHONPATH` to its `src`.

```sh
uv run fieldproof verify studies/overlapping-text/fixture.json \
  studies/overlapping-text/fixtures/replacement-15.pdf --out /tmp/overlap-report.json
```

The CLI keeps the covered 900 in review. In the local review server, upload the
same PDF and `fixture.json`, inspect the amount, correct it to 100, export and save
a review archive. The correction keeps the original automated verdict and quote.
The existing static demo does not execute this native loader; this correction
needs the updated local package. No source was pushed, package released or site
deployed as part of this work.
