# Grounding checked against annotated receipts: what fieldproof finds, and what it accepts that is not there

fieldproof exists to catch a model that reports a value the document does not
contain. Until now its grounding had been tested on its own three sample
documents with hand-written assertions, so neither failure had a rate: failing
to find a value that is there, and (the expensive one) accepting a value that
is not. This study measures both on 1,052 real receipts whose words and field
values were annotated by someone else, with no model in the loop.

## What came out

- **Released 0.2.7 accepted wrong values for two kinds of field.** Offered a
  name with one letter changed, it marked the field `verified` at the right place
  77% of the time on the held-out half (866 of 1,124 cases). Offered a total
  one cent away from the page's, it did so 45% of the time (141 of 312), and 60%
  (188 of 312) when the quote was the true one with only the value changed. Digit changes, transposed
  digits, shifted and swapped dates, and amounts or names from other receipts
  were almost never accepted (0.3% of digit-changed amounts, 0.2% of names from
  other receipts). The "fuzzy match accepts 19.80 for 18.90" worry did not
  materialise; the value check caught it. The cent tolerance and the string
  similarity of 82 did the damage.
- **It also failed to find values that were there, mostly because it compared
  numbers and dates as strings.** With the label quoted as a model would, 22% of
  held-out amounts and 63% of dates were not verified at the right place.
  Indonesian receipts write sixty thousand as `60.000`, which the number parser
  read as sixty; dates written `23-01-2019` or `12.01.19` were not read at all;
  a date or amount a model had rewritten (`2018-12-25`, `60000`) was found at the
  right place 0.0% and 8.1% of the time.
- **Wrong-place groundings were almost never accepted.** Of 1,949 annotated
  single-word fields whose value is written more than once on the page, all 1,949
  went to review as ambiguous when quoted bare as printed; none was verified at the
  wrong occurrence, in the released version or in the checkout. With the label
  quoted, verified-at-the-wrong-place was 0.0% to 0.1% for amounts, dates and
  names in both versions (one amount in the checkout). It happens for rewritten
  bare quotes: 0.8% of amounts before, 0.4% after; 2.1% of quantities in both.
- **After the changes (source checkout, unreleased)** the false accepts above are 0
  of 312 and 0 of 1,124 on the held-out half, 1 of 2,247 for names overall, and 0 of
  3,517 for amounts; found-at-the-right-place for amounts rises from 77.6% to
  95.9%, dates from 36.7% to 60.4%, names the model re-cased or re-punctuated
  from 65.9% to 93.7%, and rewritten bare date and amount quotes from 0.0% and
  8.1% to 47.7% and 48.5%. Names quoted verbatim stay at 95.5% (95.8% before). Small integers
  (quantities) are unchanged: a bare `1` is on the page many times.
- The remaining review rate is mostly honest: a numeric date whose day and
  month are both 12 or under goes to review unless the document settles the order,
  and a quote that occurs more than once is ambiguous.

## Why this measurement

A grounded field is only worth showing a reviewer if the highlighted words
are the words the value came from, and a `verified` badge is only worth anything
if the value could not have been invented. Both depend on thresholds nobody had
set against data: a 70 to 92 fuzzy score, a one-cent number tolerance, an 82
string similarity.

## The data

| | documents | annotated fields | licence |
|---|---:|---:|---|
| CORD v2 | 400 (dev 200, held out 200) | 3,585 | CC BY 4.0, from the dataset card |
| SROIE 2019, a third-party copy | 652 (dev 326, held out 326) | 2,446 | the copy's card says MIT; the competition's own terms were not verified |

Total 1,052 documents, 6,031 annotated fields (`results.json`, `summary`).

- **CORD v2** (<https://huggingface.co/datasets/naver-clova-ix/cord-v2>) gives
  every word on a receipt with a four-corner box and, for the parsed lines, the
  field they belong to (`total.total_price`, `sub_total.tax_price`, `menu.nm`,
  `menu.price`, `menu.cnt`) and whether a word is a key or the value. Only lines
  in `valid_line` have text, so a page here contains the annotated lines and
  nothing else: no shop header, no date.
  The train shard 0 (200 receipts) is the dev set and the validation and test
  files (100 each) are held out.
- **SROIE 2019** has full-page OCR lines with boxes and four key fields: company,
  address, date and total. The copy used is
  <https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding>
  (652 receipts), whose card says it is the ICDAR 2019 competition data with extra
  line labels. Even-numbered receipts in file order are the dev set, odd-numbered are
  held out. The OCR lines are split on whitespace into words with the line's box
  shared out by character count.
- **Not used.** FUNSD: its licence page at
  <https://guillaumejaume.github.io/FUNSD/license/> returned 404 and the download
  page said "EMPTY LINK FOR NOW", so there was nothing to check or fetch. The
  original SROIE site was not queried.

`fetch.py` downloads the four parquet files at pinned revisions and checks them
against `manifest.json` (1.18 GB, images never read).

### How fieldproof sees a page, and the adapter

fieldproof's `Document` is pages of `Word(text, bbox, start, end)` where `start` and
`end` are offsets into the page's text (the words joined by single spaces), built by
`document/loader.py` from a PDF text layer or Tesseract. `adapt.py` builds the same
structure from annotated words. It puts words in reading order by grouping their
vertical centres into lines and sorting each line left to right; the dataset's own
order is not used. The adapter is part of the study, not the library: nothing in
fieldproof's workflow needs to read pre-extracted words.

## The measure

Each annotated field becomes a one-field `Evidenced` model and goes through
`fieldproof.verify.verify` on the receipt's `Document`. The outcome is the
status it returns, plus whether the highlighted rectangles cover the annotated
words (at least half of them and at most three other words).

- **right place**: `verified`, at the annotated words.
- **wrong place**: `verified`, somewhere else.
- **review**: `needs_review`. **not found**: `unsupported`.
- For values that are not on the page, **accepted** means right place plus wrong
  place. Cases whose wrong value happens to be on the page as another number or
  date (953 of 17,331) are left out of that denominator.

The three measurements, each in terms of what a model returns for a field
(`value`, and a verbatim `evidence` quote that is meant to be copied from the page):

1. **As written.** The quote is the label (up to two words on the same line before
   the value) plus the value exactly as printed; the value is the number or ISO date.
2. **As a model would return it.** Fixed rules, no model:
   (2a) the value is rewritten and the quote stays verbatim: amounts without
   symbols and separators, ISO dates, names lower-cased, title-cased, without
   punctuation, trimmed, with a first or last word dropped, addresses joined with
   commas; (2b) the quote is rewritten too and offered bare (`60000`,
   `2018-12-25`, `book ta k taman daya`).
3. **Not there.** A wrong value, offered three ways: *fabricated with label* (the
   label plus the wrong value as the quote, which is what a model that invents a
   total would write), *fabricated bare*, and *true quote* (the real quote with only
   the value wrong). Wrong values: an amount with one digit changed (random
   position), two adjacent digits transposed, the last digit off by one (one cent),
   the same field from another receipt, a date plus or minus a day, day and month
   swapped, a name with one letter or digit changed, and a name from another
   receipt. Every choice is seeded from the document and field.

Amounts are read with a locale-aware rule written in `run.py` (separators followed by
exactly three digits are thousands). SROIE dates are read day first, as Malaysian
receipts write them; the ISO "gold" date is that reading of the printed text, not
something the dataset states.

## Results

Held-out half (CORD validation and test, odd SROIE receipts). "Before" is the
released v0.2.7 built from its tag; "after" is this checkout. Every row is in
`results.json`; the dev half agrees in direction and is below.

Right place (verified at the annotated words), and accepted (verified although the
value is not on the page):

| field type | n (as written) | as written, before → after | rewritten value, before → after | rewritten value and quote, bare, before → after | n (not on the page) | accepted, label + wrong value, before → after | accepted, true quote + wrong value, before → after |
|---|---:|---|---|---|---:|---|---|
| amount | 1,172 | 77.6% → 95.9% | 77.6% → 95.9% | 8.1% → 48.5% | 3,517 | 4.1% → 0.0% | 4.4% → 0.0% |
| quantity | 430 | 40.2% → 40.2% | 40.2% → 40.2% | 22.1% → 22.3% | 514 | 0.0% → 0.0% | 0.0% → 0.0% |
| date | 283 | 36.7% → 60.4% | 36.7% → 60.4% | 0.0% → 47.7% | 958 | 0.0% → 0.0% | 0.0% → 0.0% |
| text | 1,125 | 95.8% → 95.5% | 65.9% → 93.7% | 62.1% → 89.8% | 2,247 | 38.6% → 0.0% | 43.4% → 0.0% |

n for the "rewritten" columns is larger than the "as written" one because there are
several rewrites per field (amount 3,516; quantity 430; date 566; text 6,545).
Wrong-place verifications in the first two value columns are 0.0% for quantities and
dates and 0.1% for text in both versions, and 0.0% before and 0.1% after for amounts
(one case, `cord-test-45`). In the bare-quote column they are 0.8% → 0.4% (amounts),
2.1% (quantities), 0.0% (dates) and 0.1% (text); the full split is in `results.json`.

By kind of error, same held-out half, label + wrong value as the quote:

| kind of error | n | accepted before | accepted after |
|---|---:|---:|---:|
| amount, last digit off by one | 312 | 45.2% | 0.0% |
| amount, one digit changed | 1,155 | 0.3% | 0.0% |
| amount, two digits transposed | 919 | 0.0% | 0.0% |
| amount from another receipt | 1,131 | 0.0% | 0.0% |
| quantity, digit changed / from another receipt | 362 / 152 | 0.0% | 0.0% |
| date plus or minus a day | 566 | 0.0% | 0.0% |
| date, day and month swapped | 110 | 0.0% | 0.0% |
| date from another receipt | 282 | 0.0% | 0.0% |
| text, one letter changed | 1,124 | 77.0% | 0.0% |
| text from another receipt | 1,123 | 0.2% | 0.1% |

The one-cent rows are not 100% because the old check allowed a difference of at most
0.01 between floating-point numbers: 9.01 against 9.00 passes, and some other cent pairs
(9.11 against 9.10, depending on the digits) land a rounding error over 0.01 and do not.
Of the true quotes with only the value one cent off, 60.3% were accepted (188 of 312).
With a made-up quote the figure is lower, 45.2%, because a short quote one digit off the
page also falls under the strong-match score of 92 more often.

Dev half (the part the changes were looked at on):

| field type | as written, before → after | rewritten value, before → after | accepted, label + wrong value, before → after |
|---|---|---|---|
| amount | 79.1% → 93.9% | 79.1% → 93.9% | 3.6% → 0.0% |
| quantity | 43.0% → 43.0% | 43.0% → 43.0% | 0.2% → 0.0% |
| date | 42.6% → 65.6% | 42.6% → 65.6% | 0.0% → 0.0% |
| text | 97.3% → 97.3% | 65.5% → 95.4% | 39.5% → 0.0% |

### Why the rest is still in review

From `results.json` (`not_verified_with_label_as_written`, dev and held out together,
this checkout; before in parentheses):

- amounts: 119 ambiguous (a value written twice) and 1 not found; the 390 where the
  value differed from the number read (nearly all of them `60.000`-style amounts) are
  gone;
- dates: 199 numeric dates that could be day first or month first (147 before, when
  184 more were "format not read"), 10 ambiguous;
- quantities: 496 ambiguous, which is right: a bare `1` is on a receipt many times.

## What was wrong and what changed

All in the source checkout, unreleased. The tests that encode them use short strings
from these receipts (`tests/test_real_receipts.py`); one old test asserted that a
misspelt name was supported and now asserts it is not.

1. **Numbers are compared as values, to the precision the page wrote.** `9.00`
   supports `9` and `9.001`, not `9.01`; the fixed 0.01 tolerance (a whole cent) is
   half a unit of the last printed place, never more than half a cent
   (`NUMBER_TOLERANCE`). A token such as `60.000` has two readings, sixty and sixty
   thousand, and either matches unless the document settles which: a number like
   `1,234.50` says `.` is a decimal point, `1.591.600` says it is a thousands
   separator (`ground/values.py`, `number_style`). This mirrors how dates already
   worked. A bare `9.99` or `111,000` settles nothing; one CORD receipt prints
   `111,000` and `222.000` side by side.
2. **Numeric dates with `-` or `.` and two-digit years are read**, not only `/`.
3. **A quote that is only a number or only a date is found by value** when no
   character match exists: `60000` at `60.000`, `2018-12-25` at `25/12/2018`
   (`GroundingMatch.by_value`). A quote that differs only in letter case is found at
   every place the page has it, so a repeated name stays ambiguous.
4. **A fuzzy match is strong only if its letters and digits agree with the page**
   (case, spacing and punctuation ignored; a separator between digits and a leading
   minus count). "INDAH GIFT & HOME DECQ" is 95/100 like the page and not the name on
   it. Without the separator rule a made-up `12.00` was verified against the time
   `12:00`; without the minus rule `30,000` was verified against change given back,
   `-30,000`. Both were found by this study.
5. **A string value must be a run of the evidence's words, ignoring case, spacing
   and punctuation**, instead of 82% similar. A value similar to the evidence but
   different in a letter is reported as such and sent to review.

No threshold was tuned. The one constant that moved, the number tolerance, went from
a whole cent to half a cent because a page cannot support a value that rounds to a
different cent.

## What is left

- A fuzzy-matched quote that occurs twice is not reported as ambiguous: fuzzy
  alignment returns one best window.
- Dates: 40% of held-out dates still go to review because nothing on the receipt
  settles day-first against month-first. That is the existing design, and these
  receipts are all day-first.
- A `60.000` that nothing settles is read either way, so a value off by a factor of a
  thousand can pass for it. The released version accepted sixty and refused sixty
  thousand; the checkout accepts both. Both versions are measured in
  `results.json` under `scaled_wrong`.
- One text false accept remains in the held-out half: another receipt's address that
  is a prefix of this receipt's address (two branches of one chain).

## What this does not show

- **No model was used.** The "extraction" is the annotated value rewritten or
  corrupted by the rules above. A model's real errors (transposing a column,
  choosing the wrong line, inventing a plausible total) are not these.
- **The pages are not scans.** The words come from the datasets' annotation. CORD pages
  contain only the annotated lines. SROIE text is the competition's OCR, not
  Tesseract's. No pixel noise reached fieldproof, so what fuzzy matching buys on a
  badly scanned page is not measured. The change that makes a letter-differing
  quote go to review rather than verified is argued from the extraction prompt in
  `src/fieldproof/extract/anthropic_provider.py` (the model is given the same page text
  that grounding checks and told to copy it character for character, so a quote that
  disagrees with the page in a letter is a model's copy error); it has not been
  tested on a scan.
- **Fields were checked one at a time.** Row-locality hints between line-item fields
  were not used, and the cross-field rules (line items sum to the subtotal) do not run
  for the study's one-field models.
- **Forms are not covered**, only receipts. FUNSD was not obtainable.
- **The held-out half was not untouched.** I ran and read both halves while finding
  the problems, so it is held out from nothing but the final rules; every change is a
  rule, none a constant fitted to a score. The dev and held-out rows move together.
- **The dataset's boxes are one yardstick.** A value printed in two columns of one
  row (a unit price equal to the line amount) counts as wrong place when the other
  column is quoted. 1,949 fields have their value written more than once.
- **Gold dates are my reading.** SROIE gives the printed text; the ISO date is parsed
  day first by `run.py`. The SROIE total and date narrowed to the first matching token
  of the labelled line.
- **Licence of the SROIE copy is only as stated on its card.**

## Reproduce

```sh
git worktree add /tmp/fieldproof-0.2.7 v0.2.7             # the released version
uv venv /tmp/fp-venv && UV_PROJECT_ENVIRONMENT=/tmp/fp-venv uv sync --frozen --all-extras
uv pip install --python /tmp/fp-venv/bin/python pyarrow
python3 studies/cord-grounding/fetch.py                    # 1.18 GB, checks SHA-256
cd studies/cord-grounding
/tmp/fp-venv/bin/python -I run.py --src /tmp/fieldproof-0.2.7/src --out cache/rows-released.jsonl
/tmp/fp-venv/bin/python -I run.py --src ../../src --out cache/rows-checkout.jsonl
/tmp/fp-venv/bin/python -I analyze.py released=cache/rows-released.jsonl checkout=cache/rows-checkout.jsonl
```

`analyze.py` writes `results.json` and prints every table in this file. `run.py` takes a
couple of minutes per version with four workers.

## References and licences

- CORD v2, dataset card and files: <https://huggingface.co/datasets/naver-clova-ix/cord-v2>
  at revision `7f0115a4b758a71d6473b8d085751692da2fef98`; the card states
  `license: cc-by-4.0`.
- SROIE copy: <https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding>
  at revision `3e9c4eb6eb75d1a72396ab005bcd0abdcf319060`; the card states MIT and
  says the source is the ICDAR 2019 competition, <https://rrc.cvc.uab.es/?ch=13>
  (that page was not fetched).
- FUNSD: <https://guillaumejaume.github.io/FUNSD/>, not used, see above.

Data are not committed. Quoted receipt text in the tests is a few words each.
