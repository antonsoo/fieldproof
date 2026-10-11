"""Replay complete written-date evidence through actual PDF text and word boxes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path

# Expectations describe literal printed dates, independently of the parser.
CASES = [
    ("long-year", "May 1, 20260", "2026-05-01", False),
    ("long-year-day-first", "1 May 20260", "2026-05-01", False),
    ("long-day", "111 January 2026", "2026-01-11", False),
    ("long-day-zero-prefix", "001 January 2026", "2026-01-01", False),
    ("year-letter", "May 1, 2026A", "2026-05-01", False),
    ("year-underscore", "May 1, 2026_ref", "2026-05-01", False),
    ("month-word", "XMay 1, 2026", "2026-05-01", False),
    ("day-word", "X1 May 2026", "2026-05-01", False),
    ("identifier-prefix", "ref-May 1, 2026", "2026-05-01", False),
    ("identifier-suffix", "May 1, 2026-X", "2026-05-01", False),
    ("slash-suffix", "May 1, 2026/99", "2026-05-01", False),
    ("decimal-suffix", "May 1, 2026.7", "2026-05-01", False),
    ("invalid-leap", "February 29, 2026", "2026-02-28", False),
    ("invalid-day", "April 31, 2026", "2026-04-30", False),
    ("month-comma", "May 1, 2026", "2026-05-01", True),
    ("month-no-comma", "May 1 2026", "2026-05-01", True),
    ("month-upper", "MAY 1, 2026", "2026-05-01", True),
    ("month-short", "Jan 1, 2026", "2026-01-01", True),
    ("month-short-period", "Jan. 1, 2026", "2026-01-01", True),
    ("day-full", "1 January 2026", "2026-01-01", True),
    ("day-short", "1 Jan 2026", "2026-01-01", True),
    ("day-short-period", "1 Jan. 2026", "2026-01-01", True),
    ("parentheses", "(May 1, 2026)", "2026-05-01", True),
    ("sentence-period", "May 1, 2026.", "2026-05-01", True),
    ("colon-no-space", "Date:May 1, 2026", "2026-05-01", True),
    ("valid-leap", "February 29, 2024", "2024-02-29", True),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))
    from pydantic import BaseModel
    from reportlab.pdfgen.canvas import Canvas

    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    class Claim(BaseModel):
        effective_date: Evidenced[str]

    Claim.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    rows = []
    for name, text, value, supported in CASES:
        quote = f"Effective date: {text}"
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        canvas.setFont("Helvetica", 12)
        canvas.drawString(36, 720, quote)
        canvas.save()
        raw = stream.getvalue()
        document = load_pdf(raw)
        assert quote in document.full_text()
        for style, evidence in (("printed", quote), ("iso", value)):
            claim = Claim(effective_date=Evidenced(value=value, evidence=[evidence], page=1))
            field = verify(claim, document).fields[0]
            # Existing whole-word/numeric-modifier grounding cannot locate these
            # rewritten ISO quotes. Keep that limitation visible, without changing
            # the rule that the full printed quote supplies a supported date.
            grounding_limit = style == "iso" and name in ("parentheses", "colon-no-space")
            agrees = (field.status.value == "verified") == (supported and not grounding_limit)
            rows.append({"case": name, "printed": quote, "quote_style": style,
                         "quote": evidence, "value": value, "supported": supported,
                         "known_grounding_limit": grounding_limit,
                         "agrees": agrees, "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                         "field": field.to_dict()})
    result = {
        "scope": "Constructed PDF boundary and support controls; no model or OCR calls.",
        "pdfs": len(CASES), "cases": len(rows),
        "unsupported_verified": sum(not r["supported"] and r["field"]["status"] == "verified"
                                    for r in rows),
        "supported_not_verified": sum(r["supported"] and r["field"]["status"] != "verified"
                                      for r in rows),
        "results": rows,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    if not args.observe_only:
        assert all(r["agrees"] for r in rows), [
            (r["case"], r["quote_style"], r["field"]["status"]) for r in rows if not r["agrees"]
        ]


if __name__ == "__main__":
    main()
