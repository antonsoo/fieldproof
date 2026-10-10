"""Replay date claims and convention discovery on pinned receipt word annotations.

Uses the existing study adapter and its stated day-first interpretation, not a
new OCR/model run. Full OCR text and images are not redistributed in the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    src = args.src.resolve()
    prior = Path(__file__).resolve().parents[1] / "cord-grounding"
    sys.path.insert(0, str(src))
    sys.path.insert(1, str(prior))
    import run as study

    import fieldproof
    from fieldproof.verify.value_checks import numeric_date_order

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)
    manifest = json.loads((prior / "manifest.json").read_text())
    inputs = {}
    for entry in manifest["files"]:
        with (prior / "cache" / entry["name"]).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        assert digest == entry["sha256"]
        inputs[entry["name"]] = digest
    cases = study.load_cases()
    models = study._modelclass()
    records, conventions = [], []
    skipped = Counter()
    for index, case in enumerate(cases):
        text = case.document.full_text()
        conventions.append(
            {
                "document": case.doc_id,
                "dataset": case.dataset,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "order": numeric_date_order(text),
            }
        )
        for gold_index, gold in enumerate(case.golds):
            if gold.kind != "date":
                continue
            expected = study.parse_written_date(gold.text)
            if expected is None:
                skipped["unparseable_annotated_date"] += 1
                continue
            variants = [
                ("as_written", expected),
                ("previous_day", expected - timedelta(days=1)),
                ("next_day", expected + timedelta(days=1)),
            ]
            if expected.day <= 12 and expected.day != expected.month:
                variants.append(("swapped", date(expected.year, expected.day, expected.month)))
            for default in (None, "dmy"):
                study.VERIFY_KW = {"default_date_order": default}
                for quote_style, quote in (("printed", gold.text), ("iso", expected.isoformat())):
                    for variant, value in variants:
                        judged = study.judge(
                            case.document,
                            set(gold.word_idx),
                            quote,
                            value.isoformat(),
                            "date",
                            models,
                        )
                        records.append(
                            {
                                "document": case.doc_id,
                                "gold": gold_index,
                                "default": default,
                                "quote_style": quote_style,
                                "variant": variant,
                                "status": judged["status"],
                                "place_ok": judged["place_ok"],
                                "n_candidates": judged["n_cands"],
                            }
                        )
        if index % 200 == 0:
            print(f"{index}/{len(cases)} documents, {len(records)} date checks", flush=True)
    output = {
        "input_sha256": inputs,
        "documents": len(cases),
        "date_checks": len(records),
        "skipped": dict(skipped),
        "conventions": conventions,
        "records": records,
    }
    args.out.write_text(json.dumps(output, separators=(",", ":")) + "\n")
    print({key: value for key, value in output.items() if key not in ("conventions", "records")})


if __name__ == "__main__":
    main()
