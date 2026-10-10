"""Keep compact, input-matched evidence from the PDF and receipt replays."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_summary(records: list[dict]) -> list[dict]:
    groups = []
    for default in (None, "dmy"):
        for quote in ("printed", "iso"):
            subset = [r for r in records if r["default"] == default and r["quote_style"] == quote]
            correct = [r for r in subset if r["variant"] == "as_written"]
            wrong = [r for r in subset if r["variant"] != "as_written"]
            groups.append(
                {
                    "default": default,
                    "quote_style": quote,
                    "correct_claims": len(correct),
                    "correct_verified_at_gold_location": sum(
                        r["status"] == "verified" and r["place_ok"] is True for r in correct
                    ),
                    "correct_verified_elsewhere": [
                        r
                        for r in correct
                        if r["status"] == "verified" and r["place_ok"] is not True
                    ],
                    "correct_verdicts": dict(Counter(r["status"] for r in correct)),
                    "wrong_claims": len(wrong),
                    "wrong_verified": [r for r in wrong if r["status"] == "verified"],
                    "wrong_verdicts": dict(Counter(r["status"] for r in wrong)),
                }
            )
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pdf-before", "pdf-after", "receipts-before", "receipts-after", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    pb, pa, rb, ra = [
        json.loads(path.read_text())
        for path in (args.pdf_before, args.pdf_after, args.receipts_before, args.receipts_after)
    ]
    for key in ("scope", "cases"):
        assert pb[key] == pa[key]
    pdf_rows = []
    for before, after in zip(pb["results"], pa["results"], strict=True):
        assert {k: v for k, v in before.items() if k not in ("result", "detected_order")} == {
            k: v for k, v in after.items() if k not in ("result", "detected_order")
        }
        pdf_rows.append(
            {
                **{k: after[k] for k in ("case", "default", "value", "expected", "pdf_sha256")},
                "before": before["result"]["status"],
                "after": after["result"]["status"],
            }
        )
    for key in ("input_sha256", "documents", "date_checks", "skipped"):
        assert rb[key] == ra[key]
    conventions, records = [], []
    for before, after in zip(rb["conventions"], ra["conventions"], strict=True):
        assert {k: v for k, v in before.items() if k != "order"} == {
            k: v for k, v in after.items() if k != "order"
        }
        if before != after:
            conventions.append({**after, "order_before": before["order"]})
    for before, after in zip(rb["records"], ra["records"], strict=True):
        assert {
            k: v for k, v in before.items() if k not in ("status", "place_ok", "n_candidates")
        } == {k: v for k, v in after.items() if k not in ("status", "place_ok", "n_candidates")}
        if before != after:
            records.append({"before": before, "after": after})
    result = {
        "baseline_commit": "7be880a",
        "scope": "Constructed PDFs and existing receipt annotations; no OCR or model run.",
        "pdf": {
            "before": {k: v for k, v in pb.items() if k != "results"},
            "after": {k: v for k, v in pa.items() if k != "results"},
            "claims": pdf_rows,
        },
        "receipts": {
            **{k: ra[k] for k in ("input_sha256", "documents", "date_checks", "skipped")},
            "full_replay_sha256": {
                "before": digest(args.receipts_before),
                "after": digest(args.receipts_after),
            },
            "convention_changes": conventions,
            "claim_changes": records,
            "before": receipt_summary(rb["records"]),
            "after": receipt_summary(ra["records"]),
        },
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"PDF mismatches {pb['mismatches']} -> {pa['mismatches']}; "
        f"receipt claim changes: {len(records)}, convention changes: {len(conventions)}"
    )


if __name__ == "__main__":
    main()
