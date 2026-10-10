"""Replay document-wide date convention poisoning through actual PDF text and boxes.

Generate once per context, then verify both readings with/without an explicit
locale default. Expectations are specified independently of Fieldproof's parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path

CONTEXTS = [
    ("no-context", "", None),
    ("valid-dmy", "Other date: 14/03/2026", "dmy"),
    ("valid-mdy", "Other date: 03/14/2026", "mdy"),
    ("valid-leap", "Other date: 29/02/2024", "dmy"),
    ("valid-century-leap", "Other date: 29/02/2000", "dmy"),
    ("valid-day-first-dot", "Other date: 14.03.2026", "dmy"),
    ("valid-month-first-hyphen", "Other date: 03-14-26", "mdy"),
    ("valid-labeled", "Date:14/03/2026", "dmy"),
    ("valid-parentheses", "Date (14/03/2026).", "dmy"),
    ("equal-day-month", "Other date: 11/11/2026", None),
    ("iso-neutral", "Other date: 2026-03-14", None),
    ("invalid-day-99", "Reference: 99/01/2026", None),
    ("invalid-february", "Reference: 02/31/2026", None),
    ("invalid-april", "Reference: 31/04/2026", None),
    ("invalid-leap", "Reference: 29/02/2025", None),
    ("invalid-century-leap", "Reference: 29/02/1900", None),
    ("invalid-zero-month", "Reference: 19/00/2026", None),
    ("invalid-zero-day", "Reference: 00/19/2026", None),
    ("identifier-prefix", "Reference: ABC14/03/2026", None),
    ("identifier-suffix", "Reference: 14/03/2026XYZ", None),
    ("identifier-underscore", "Reference: ref_14/03/2026", None),
    ("identifier-hyphen", "Reference: ref-14/03/2026", None),
    ("identifier-hyphen-suffix", "Reference: 14/03/2026-XYZ", None),
    ("identifier-slash-suffix", "Reference: 14/03/2026/99", None),
    ("identifier-dot-suffix", "Reference: 14/03/2026.7", None),
    ("long-year", "Reference: 14/03/20261", None),
    ("valid-with-invalid-opposite", "Other date: 03/14/2026; reference: 99/01/2026", "mdy"),
    ("valid-with-identifier-opposite", "Other date: 14/03/2026; ref: ABC03/14/2026XYZ", "dmy"),
]


QUOTED_IDENTIFIERS = [
    "ABC03/04/2026",
    "03/04/2026XYZ",
    "ref_03/04/2026",
    "ref-03/04/2026",
    "03/04/2026-XYZ",
    "03/04/2026/99",
    "03/04/2026.7",
    "ABC2026-04-03XYZ",
    "2026-04-03/99",
    "2026-04-03.7",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))
    from pydantic import BaseModel
    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify
    from fieldproof.verify.value_checks import numeric_date_order

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)

    class Claim(BaseModel):
        issue_date: Evidenced[str]

    Claim.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    cases = [
        (name, context, convention, "03/04/2026", False) for name, context, convention in CONTEXTS
    ]
    cases += [
        (f"quoted-identifier-{i}", f"Reference: {token}", None, f"Reference: {token}", True)
        for i, token in enumerate(QUOTED_IDENTIFIERS)
    ]
    cases += [
        (
            f"quoted-invalid-iso-{i}",
            f"Issue: 03/04/2026; reference: {token}",
            None,
            f"Issue: 03/04/2026; reference: {token}",
            False,
        )
        for i, token in enumerate(("2026-99-99", "2026-02-29", "ABC2026-99-99XYZ"))
    ]
    # A literal ISO quote denotes April 3 regardless of the caller's convention.
    cases.append(("quoted-iso-control", "Date:2026-04-03.", "dmy", "Date:2026-04-03.", False))
    for name, context, convention, quote, identifier_quote in cases:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        canvas.setFont("Helvetica", 12)
        canvas.drawString(
            36, 720, "Reference-only example" if identifier_quote else "Issue: 03/04/2026"
        )
        if context:
            canvas.drawString(36, 690, context)
        canvas.save()
        pdf = stream.getvalue()
        (args.out / f"{name}.pdf").write_bytes(pdf)
        document = load_pdf(pdf)
        assert context in document.full_text()
        for default in (None, "mdy", "dmy"):
            for reading, value in (("mdy", "2026-03-04"), ("dmy", "2026-04-03")):
                data = Claim(issue_date=Evidenced[str](value=value, evidence=[quote], page=1))
                expected = (
                    "verified"
                    if not identifier_quote and reading == (convention or default)
                    else "needs_review"
                )
                report = verify(data, document, default_date_order=default)
                result = report.fields[0]
                rows.append(
                    {
                        "case": name,
                        "context": context,
                        "quote": quote,
                        "default": default,
                        "value": value,
                        "expected": expected,
                        "detected_order": numeric_date_order(document.full_text()),
                        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                        "result": result.to_dict(),
                    }
                )
    mismatches = [r for r in rows if r["result"]["status"] != r["expected"]]
    output = {
        "scope": f"{len(cases)} constructed PDFs; two readings and three defaults; no model calls.",
        "cases": len(rows),
        "mismatches": len(mismatches),
        "wrong_or_unsupported_verified": sum(
            r["result"]["status"] == "verified" for r in mismatches
        ),
        "supported_sent_to_review": sum(r["result"]["status"] != "verified" for r in mismatches),
        "verdicts": dict(Counter(r["result"]["status"] for r in rows)),
        "results": rows,
    }
    (args.out / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print({key: value for key, value in output.items() if key != "results"})
    if not args.observe_only:
        assert not mismatches, [(r["case"], r["default"], r["value"]) for r in mismatches]


if __name__ == "__main__":
    main()
