# Grounding checked against annotated receipts: what fieldproof finds, and what it accepts that is not there

fieldproof exists to catch a model that reports a value the document does not
contain. Until now its grounding had been tested on its own three sample
documents with hand-written assertions, so neither failure had a rate: failing
to find a value that is there, and (the expensive one) accepting a value that
is not. This study measures both on 1,052 real receipts whose words and field
values were annotated by someone else.

No model is in the loop. What a model would return is imitated by fixed rules:
the annotated value rewritten the way models rewrite (ISO dates, bare numbers,
changed case), or damaged the way a typing error damages it (one letter, one
digit, one cent). Those are not a model's characteristic mistakes, which are
the wrong line, the wrong column, a derived or invented total. Of those, only
"a value from another receipt" is tried here.

## What came out

- **Released 0.2.7 verified names that the page does not say.** Offered a name
  with one letter changed, it marked the field `verified` 78% of the time
  (1,754 of 2,251; 76% to 80%). For a shop's name on a SROIE receipt it was 92%.
- **And totals a cent off.** 42% of amounts with the last digit changed by one
  were verified (265 of 631). Nearly all of these are SROIE totals: 245 of 558.
  Other wrong amounts and dates were almost never accepted: a changed digit
  elsewhere 7 times in 2,327, a wrong date never in 1,896.
- **The checkout accepts none of those, because it was written not to.** A
  text value must now be a run of the page's words, and a number must match to
  the precision the page printed. A changed letter or a changed cent cannot
  pass either rule, so 0 of 2,251 and 0 of 631 are what the rules say, not a
  measurement of them. As bounds: under 0.3% and under 0.5%.
- **That strictness has a price, and it is the same event.** A name that
  differs from the page by one letter is a model's typing error or a model
  repairing an OCR error, and the library cannot tell which. With one
  character on the page garbled the way OCR garbles (`O` for `0`, `l` for
  `1`), 0.2.7 verified the repaired name in 83% of 2,198 cases. The checkout
  verifies none and sends them all to review. An opt-in setting,
  `text_edit_tolerance=1`, brings back 66% of them and with them 70% of the
  one-letter false accepts.
- **It also failed to find values that were there, because it compared numbers
  and dates as strings.** With the label quoted as a model would quote it,
  78% of amounts and 40% of dates were verified at the right place; now 95%
  and 63%. Indonesian receipts write sixty thousand as `60.000`, which was
  read as sixty; dates written `23-01-2019` were not read at all. A date or an
  amount the model had rewritten (`2018-12-25`, `60000`) was found 0% and 8%
  of the time, now 49% and 46%.
- **One false accept is untouched: a factor of a thousand.** Where the page
  says `60.000` and nothing else on it settles what the dot means, sixty and
  sixty thousand both pass. Offered the wrong one, both versions accept it 383
  times in 409. On these receipts nothing ever settles it.

The rules were written while reading these receipts, all of them. There is no
held-out set here. The two halves the tables show are a consistency check, not
a test.

## Why this measurement

A grounded field is only worth showing a reviewer if the highlighted words
are the words the value came from, and a `verified` badge is only worth anything
if the value could not have been invented. Both depend on thresholds nobody had
set against data: a 70 to 92 fuzzy score, a one-cent number tolerance, an 82
string similarity.

## The data

| | documents | annotated fields | licence |
|---|---:|---:|---|
| CORD v2 | 400 (halves A and B, 200 each) | 3,585 | CC BY 4.0, from the dataset card and the authors' repository |
| SROIE 2019, a third-party copy | 652 (halves A and B, 326 each) | 2,446 | the copy's card says MIT; the competition's own terms were not verified |

Total 1,052 documents, 6,031 annotated fields (`results.json`, `summary`).

- **CORD v2** (<https://huggingface.co/datasets/naver-clova-ix/cord-v2>) gives
  every word on a receipt with a four-corner box and, for the parsed lines, the
  field they belong to (`total.total_price`, `sub_total.tax_price`, `menu.nm`,
  `menu.price`, `menu.cnt`) and whether a word is a key or the value. Only lines
  in `valid_line` have text, so a page here contains the annotated lines and
  nothing else: no shop header, no date.
  The train shard 0 (200 receipts) is half A and the validation and test
  files (100 each) are half B.
- **SROIE 2019** has full-page OCR lines with boxes and four key fields: company,
  address, date and total. The copy used is
  <https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding>
  (652 receipts), whose card says it is the ICDAR 2019 competition data with extra
  line labels. Even-numbered receipts in file order are half A, odd-numbered
  half B; 232 of half B's 326 receipts are headed by a company name that also
  heads a receipt in half A, so the halves share shops. For the total and the
  date, a receipt is used only when its labelled line holds a plainly formatted
  amount or date token, which leaves out lines such as `RM33.90` and leans
  the sample towards cleanly printed receipts. The OCR lines are split on
  whitespace into words with the line's box shared out by character count.
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

A fourth measurement imitates OCR damage. One character of an annotated name
is replaced **on the page** by a look-alike (`O`/`0`, `l`/`1`, `S`/`5`, `B`/`8`
and the like), and the field is offered three ways: the quote copied from the
garbled page with the value repaired, the quote and the value both repaired,
and both copied as garbled.

## Results

All 1,052 receipts. "Released" is v0.2.7 built from its tag, "checkout" is
this repository with its defaults, and "tolerance 1" is this repository with
`text_edit_tolerance=1`. Every row is in `results.json`.

Found at the right place (verified, at the annotated words):

| | n | Released | Checkout |
|---|---:|---:|---:|
| **Quote with its label, value as printed** | | | |
| amount | 2,360 | 78.4% | 94.9% |
| quantity | 853 | 41.6% | 41.6% |
| date | 565 | 39.6% | 63.0% |
| text | 2,253 | 96.6% | 96.4% |
| **Value rewritten, quote verbatim** | | | |
| text (case, punctuation, trimmed) | 13,116 | 65.7% | 94.6% |
| **Value and quote rewritten, quote bare** | | | |
| amount | 7,080 | 8.3% | 45.9% |
| quantity | 853 | 20.4% | 20.6% |
| date | 1,130 | 0.0% | 48.8% |
| text | 13,116 | 62.1% | 90.6% |

Accepted although the value is not on the page (the quote is the label and the
wrong value, as a model inventing it would write):

| Wrong value | n | Released | Checkout | Tolerance 1 |
|---|---:|---:|---:|---:|
| SROIE total, last digit off by one | 558 | 245 (43.9%) | 0 | 0 |
| CORD amounts, last digit off by one | 73 | 20 (27.4%) | 0 | 0 |
| SROIE total, another digit changed | 570 | 7 (1.2%) | 0 | 0 |
| CORD amounts, another digit changed | 1,757 | 0 | 0 | 0 |
| any wrong date | 1,896 | 0 | 0 | 0 |
| CORD item name, one letter changed | 947 | 620 (65.5%) | 0 | 457 (48.3%) |
| SROIE company, one letter changed | 652 | 602 (92.3%) | 0 | 596 (91.4%) |
| SROIE address, one letter changed | 652 | 532 (81.6%) | 0 | 531 (81.4%) |
| any wrong text, including another receipt's | 4,500 | 1,758 (39.1%) | 1 | 1,587 (35.3%) |

Cases whose wrong value happens to be on the page as another number or date
(953 of 17,331) are left out. The checkout's zeros follow from its rules; with
receipts as the unit their 95% upper bounds are 0.5% for the one-cent case
(631 cases on 575 receipts) and 0.3% for the one-letter case (2,251 on 1,052).
The one text value the checkout still accepts is another receipt's address
that is the beginning of this receipt's: two branches of one chain.

The one-cent row was not 100% in the released version because its check
allowed a difference of at most 0.01 between floating-point numbers: 9.01
against 9.00 passes, and some other cent pairs land a rounding error over 0.01
and do not.

Names with one character garbled on the page, verified at the right place
(2,198 cases; the rest go to review):

| The model returned | Released | Checkout | Tolerance 1 |
|---|---:|---:|---:|
| the quote as garbled, the value repaired | 1,825 (83.0%) | 0 | 1,441 (65.6%) |
| the quote and the value both repaired | 1,567 (71.3%) | 0 | 1,403 (63.8%) |
| the quote and the value both as garbled | 2,166 (98.5%) | 2,161 (98.3%) | 2,162 (98.4%) |

Set this beside the one-letter rows above. They are the same event seen from
two sides, and no setting separates them: the released version and tolerance 1
accept most repairs and most typing errors, and the default accepts neither.
The default is the strict one because the tool's promise is the page's exact
words. A pipeline whose model tidies up OCR text will see every such name in
review, with the reason given.

The thousands separator, true quote with the wrong value:

| The page says | Offered | n | Released accepts | Checkout accepts |
|---|---|---:|---:|---:|
| `60.000` | 60 | 409 | 383 | 383 |
| `60,000` | 60 | 1,243 | 16 | 4 |
| any other amount | ten times it | 708 | 44 | 44 |

On the 119 receipts with an `x.000` amount, no other number on the page
settles whether the dot is a decimal point or a thousands separator, for any
of their 401 such fields (`thousands.json`). The 44 tenfold accepts were not
looked into.

The two halves, checkout, right place with the label quoted: amounts 93.9%
and 95.9%, dates 65.6% and 60.4%, text 97.3% and 95.5%. They move together.

### Why the rest is still in review

From `results.json` (`not_verified_with_label_as_written`, checkout):

- amounts: 119 ambiguous (a value written twice) and 1 not found;
- dates: 199 numeric dates that could be day first or month first, 10 ambiguous;
- quantities: 496 ambiguous, which is right: a bare `1` is on a receipt many
  times;
- text: 44 ambiguous, 22 where letters differ from the page, 15 not found.

Of 1,949 annotated single-word fields whose value is written more than once on
the page, all went to review as ambiguous when quoted bare; none was verified
at the wrong occurrence in either version.

## What was wrong and what changed

All in the source checkout, unreleased. The tests that encode them use short
strings from these receipts (`tests/test_real_receipts.py`); one old test
asserted that a misspelt name was supported and now asserts it is not.

1. **Numbers are compared as values, to the precision the page wrote.** `9.00`
   supports `9` and `9.001`, not `9.01`: the tolerance is half a unit of the
   last printed place, never more than half a cent (`NUMBER_TOLERANCE`, which
   was a whole cent). A token such as `60.000` has two readings, and either
   matches unless the document settles which (`ground/values.py`,
   `number_style`).
2. **Numeric dates with `-` or `.` and two-digit years are read**, not only `/`.
3. **A quote that is only a number or only a date is found by value** when no
   character match exists: `60000` at `60.000`, `2018-12-25` at `25/12/2018`
   (`GroundingMatch.by_value`). A quote that differs only in letter case is
   found at every place the page has it, so a repeated name stays ambiguous.
4. **A fuzzy match is strong only if its letters and digits agree with the
   page** (case, spacing and punctuation ignored; a separator between digits
   and a leading minus count). Without the separator rule a made-up `12.00` was
   verified against the time `12:00`; without the minus rule `30,000` was
   verified against change given back, `-30,000`. Both were found in these
   receipts and the rules were written for them.
5. **A string value must be a run of the evidence's words, ignoring case,
   spacing and punctuation**, instead of 82% similar.
6. **`verify(..., text_edit_tolerance=n)`** lets a text field of twelve letters
   or more differ from the page by up to `n` letters and stay verified, with
   what differed recorded in the field's notes. Off by default. Numbers and
   dates never get it.

Two constants moved: the number tolerance, from a cent to half a cent, and a
new score given to a match that differs only in case. The recognition of
amounts knows the currency marks these receipts use (`Rp`, `RM`).

## What is left

- **The thousands ambiguity**, above. The honest fix is to send an unsettled
  `x.000` amount to review instead of accepting both readings; it was not done.
- A fuzzy-matched quote that occurs twice is not reported as ambiguous: fuzzy
  alignment returns one best window.
- 37% of dates still go to review, most because nothing on the receipt settles
  day-first against month-first. That is the existing design.
- Quantities: unchanged at 42%. A bare `1` cannot be placed.

## What this does not show

- **A model's errors.** The "extraction" is the annotated value rewritten or
  damaged by rule. Choosing the wrong line, swapping a column, summing or
  inventing a total are not tried, apart from offering another receipt's value.
- **Scans.** The words come from the datasets' annotation. CORD pages contain
  only the annotated lines, with no header or footer, so look-alike strings are
  rarer than on a real page and the false-accept and ambiguity rates here are
  lower bounds. SROIE text is the competition's OCR, not Tesseract's. The OCR
  damage above is one substituted character per name, by rule.
- **Anything out of sample.** Every rule was written with these receipts in
  view, and two were written for particular false accepts found in them.
- **Fields together.** Each field was checked alone. Row-locality hints between
  line-item fields were not used, and the cross-field rules do not run for the
  study's one-field models.
- **Forms.** Only receipts. FUNSD was not obtainable.
- **Other yardsticks.** "Right place" allows at least half the annotated words
  and up to three others. A value printed in two columns of one row counts as
  wrong place when the other column is quoted.
- **Gold dates.** SROIE gives the printed text; the ISO date is that text read
  day first by `run.py`, as Malaysian receipts write it.
- **The SROIE copy's licence** is only as stated on its card.

## Reproduce

```sh
git worktree add /tmp/fieldproof-0.2.7 v0.2.7             # the released version
uv venv /tmp/fp-venv && UV_PROJECT_ENVIRONMENT=/tmp/fp-venv uv sync --frozen --all-extras
uv pip install --python /tmp/fp-venv/bin/python pyarrow
python3 studies/cord-grounding/fetch.py                    # 1.18 GB, checks SHA-256
cd studies/cord-grounding
run() { /tmp/fp-venv/bin/python -I run.py "$@"; }
run --src /tmp/fieldproof-0.2.7/src --out cache/r-released.jsonl
run --src /tmp/fieldproof-0.2.7/src --ocr --out cache/o-released.jsonl
run --src ../../src --out cache/r-checkout.jsonl
run --src ../../src --ocr --out cache/o-checkout.jsonl
run --src ../../src --tolerance 1 --out cache/r-tol1.jsonl
run --src ../../src --tolerance 1 --ocr --out cache/o-tol1.jsonl
python3 -I analyze.py released=cache/r-released.jsonl,cache/o-released.jsonl \
    checkout=cache/r-checkout.jsonl,cache/o-checkout.jsonl \
    tol1=cache/r-tol1.jsonl,cache/o-tol1.jsonl
/tmp/fp-venv/bin/python -I thousands.py --src ../../src --out thousands.json
```

`analyze.py` writes `results.json` and prints the tables. `run.py` takes a
couple of minutes per run with four workers.

## References and licences

- CORD v2: Park, Shin, Lee, Lee, Surh, Seo and Lee, "CORD: A Consolidated
  Receipt Dataset for Post-OCR Parsing", Document Intelligence Workshop at
  NeurIPS 2019. Files from <https://huggingface.co/datasets/naver-clova-ix/cord-v2>
  at revision `7f0115a4b758a71d6473b8d085751692da2fef98`; the card states
  `license: cc-by-4.0`, and so does <https://github.com/clovaai/cord>.
- SROIE copy: <https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding>
  at revision `3e9c4eb6eb75d1a72396ab005bcd0abdcf319060`; the card states MIT and
  says the source is the ICDAR 2019 competition, <https://rrc.cvc.uab.es/?ch=13>
  (that page was not fetched).
- FUNSD: <https://guillaumejaume.github.io/FUNSD/>, not used, see above.

Data are not committed. The tests quote a few words each from CORD (CC BY 4.0,
cited above) and from the SROIE copy.
