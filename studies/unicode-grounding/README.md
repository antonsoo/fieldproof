# Unicode case matching must preserve source locations

At baseline `b7ef1fccf22b82a0b82fb92ae97f2fe5e7ebb415`, a page containing
`İstanbul`, `Acme`, `Acme` verified the quote `ACME` at one of those two names.
The unrelated dotted capital I expands to two code points when lowercased.
The old safeguard disabled case-insensitive exact matching for that entire
page, then selected a single fuzzy match. A repeated quote became falsely
unique. A second page hint could hide the occurrence on the affected page too.

The repair keeps an offset map through Unicode case folding, prepared lazily
per page. Every folded character points back to the original source character.
Both exhaustive caseless matching and fuzzy alignment use that map. A boundary
inside a single expanded character is still rejected. Candidate reuse remains
bounded and local to one verification. Exact normalized matches still take
priority, followed by caseless matches, numeric/date equivalence and fuzzy
fallback; this change does not merge different matching tiers.

Python's [Unicode case-folding operation](https://docs.python.org/3/library/stdtypes.html#str.casefold)
is intended for caseless matching and includes expansions such as `ß` to `ss`.
This is the same operation already used for Fieldproof's letter-agreement check.
It is not transliteration or a locale-specific spelling rule. Original text,
claims and PDF coordinates are preserved for human review.

## Actual PDF reproduction

All ten documents are synthetic, generated with ReportLab and an embedded
DejaVu Sans subset. The [font notice](FONT-NOTICE.txt) applies to those subsets.
The fixture extractions replay without a model call. The script verifies that
the PDF text layer really contains the expected Unicode source characters;
none of these comparisons substitute an in-memory page for PDF loading.

| Case | Before candidates / verdict | After candidates / verdict |
| --- | --- | --- |
| Dotted I elsewhere, uppercase name | 0 / unsupported | 1 / verified |
| Dotted I elsewhere, repeated name | 1 / verified | 2 / needs review |
| Repeated dotted-I name | 1 / verified | 2 / needs review |
| Sharp-S and SS spellings | 1 / verified | 2 / needs review |
| Greek sigma variants | 0 / unsupported | 2 / needs review |
| Misspelling after dotted I | 0 / unsupported | 1 / needs review |
| Half an expanded letter | 0 / unsupported | 0 / unsupported |
| Complete expanded word | 1 / verified | 1 / verified |
| Exact repeated-name control | 2 / needs review | 2 / needs review |
| Repeated name across pages, hint on page 2 | 1 / verified | 2 / needs review |

[Before](results/before.json) and [after](results/after.json) retain the complete
reports, every candidate's original offsets/text/words/boxes, source text, PDF
hashes and implementation hash. All ten cases also ran through the actual API
verification worker: HTTP 200 with reports identical to the library. Four cases
lose a false verified location. A unique `STRASSE` quote still highlights the
complete printed `Straße`, while the incomplete `s` quote cannot verify `ß`.

```bash
uv sync --locked --extra dev --extra ocr
uv run python studies/unicode-grounding/replay.py --api --out /tmp/unicode-after.json
uv run pytest -q tests/test_unicode_grounding.py
```

To regenerate, add `--generate-font /path/to/DejaVuSans.ttf` to the replay
command. The checked-in PDFs are sufficient for replay; regeneration is optional.
For the baseline, archive the named commit and run the same script with
`PYTHONPATH=/path/to/baseline/src`; confirm the implementation hash against
`results/before.json`. Remove that override for installed-wheel checks.

These hand-specified cases establish the reported failures and source-coordinate
repairs. They are not a multilingual extraction accuracy benchmark, and do not
prove that a repeated name belongs to a particular document field.
