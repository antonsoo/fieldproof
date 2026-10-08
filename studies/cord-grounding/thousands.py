"""How often the document's own numbers settle what `60.000` means.

    python3 -I thousands.py --src ../../src --out cache/thousands.json

For every annotated amount written as `d.ddd` or `d,ddd` (the gold reading is thousands: 60.000
is sixty thousand), count the receipts whose other numbers settle the convention
(`fieldproof.ground.values.number_style`), and how many would be settled the other way, wrongly,
by also counting a bare `x.dd` token as proof that `.` is a decimal point (a rule tried and
dropped because CORD receipts print `10.00 %` or `Qty 4.00` beside `60.000`), and how many
sit in a receipt that also prints comma thousands (`111,000` beside `222.000`). It also counts
SROIE receipts of half B whose company text is also the company of a half A receipt (shops of
one chain on both sides of the split).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DOT_THOUSANDS = re.compile(r"^\D{0,3}\d{1,3}\.\d{3}\D{0,2}$")
COMMA_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d.,])")
BARE_DECIMAL = re.compile(r"(?<![\d.,])\d+\.\d{1,2}(?![\d.,])")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.src).resolve()))
    import run

    from fieldproof.ground.values import number_style

    counts = {
        "dot_thousands_amount_fields": 0,
        "receipts_with_such_a_field": set(),
        "fields_in_receipts_where_style_is_settled_thousands": 0,
        "fields_in_receipts_where_style_is_settled_decimal": 0,
        "fields_in_receipts_where_nothing_settles_it": 0,
        "fields_in_receipts_with_a_bare_x_dd_token": 0,
        "fields_in_receipts_that_also_print_comma_thousands": 0,
    }
    companies = {"A": set(), "B": set()}
    cases = run.load_cases()
    for case in cases:
        if case.dataset == "sroie":
            companies[case.split] |= {g.text for g in case.golds if g.kind == "company"}
    both_halves = [c for c in cases if c.dataset == "sroie"]
    counts["sroie_receipts_in_half_B"] = sum(1 for c in both_halves if c.split == "B")
    counts["sroie_half_B_receipts_whose_company_text_also_heads_a_half_A_receipt"] = sum(
        1
        for c in both_halves
        if c.split == "B" and any(g.kind == "company" and g.text in companies["A"] for g in c.golds)
    )
    for case in cases:
        text = case.document.pages[0].text
        style = number_style(text)
        has_bare = bool(BARE_DECIMAL.search(text))
        has_comma = bool(COMMA_THOUSANDS.search(text))
        for g in case.golds:
            if run.FIELD_TYPE[g.kind] != "amount" or not DOT_THOUSANDS.match(g.text):
                continue
            counts["dot_thousands_amount_fields"] += 1
            counts["receipts_with_such_a_field"].add(case.doc_id)
            key = {
                "thousands": "fields_in_receipts_where_style_is_settled_thousands",
                "decimal": "fields_in_receipts_where_style_is_settled_decimal",
                None: "fields_in_receipts_where_nothing_settles_it",
            }[style]
            counts[key] += 1
            counts["fields_in_receipts_with_a_bare_x_dd_token"] += has_bare
            counts["fields_in_receipts_that_also_print_comma_thousands"] += has_comma
    counts["receipts_with_such_a_field"] = len(counts["receipts_with_such_a_field"])
    Path(a.out).write_text(json.dumps(counts, indent=1) + "\n")
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
