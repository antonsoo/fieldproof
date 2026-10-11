"""Generate synthetic Unicode PDFs, or replay them with the current installed package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fieldproof
from fieldproof.document.loader import load_pdf
from fieldproof.ground.align import find_candidates_in_document
from fieldproof.schemas.receipt import Receipt
from fieldproof.verify.engine import verify

HERE = Path(__file__).resolve().parent


def generate(cases: list[dict], font: Path) -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("Source", str(font)))
    (HERE / "fixtures").mkdir(exist_ok=True)
    for case in cases:
        path = HERE / "fixtures" / case["id"]
        pdf = canvas.Canvas(str(path.with_suffix(".pdf")), pagesize=(600, 800), invariant=1)
        for lines in case["pages"]:
            pdf.setFont("Source", 18)
            for index, line in enumerate([*lines, "2026-10-11", "Total 1.00"]):
                pdf.drawString(50, 740 - 40 * index, line)
            pdf.showPage()
        pdf.save()
        data = {
            "merchant_name": {
                "value": case["quote"],
                "evidence": [case["quote"]],
                "page": case.get("hint_page", 1),
            },
            "transaction_date": {"value": "2026-10-11", "evidence": ["2026-10-11"]},
            "total": {"value": 1, "evidence": ["1.00"]},
        }
        path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-font", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api", action="store_true", help="Also compare the actual API worker")
    args = parser.parse_args()
    cases = json.loads((HERE / "cases.json").read_text())
    if args.generate_font:
        generate(cases, args.generate_font)
    results = []
    for case in cases:
        path = HERE / "fixtures" / case["id"]
        document = load_pdf(path.with_suffix(".pdf"))
        data = Receipt.model_validate_json(path.with_suffix(".json").read_bytes())
        for page, lines in zip(document.pages, case["pages"], strict=True):
            assert page.text == " ".join([*lines, "2026-10-11", "Total 1.00"])
        candidates = find_candidates_in_document(
            case["quote"], document, hint_page=case.get("hint_page", 1)
        )
        results.append(
            {
                "id": case["id"],
                "pdf_sha256": hashlib.sha256(path.with_suffix(".pdf").read_bytes()).hexdigest(),
                "source_pages": [page.text for page in document.pages],
                "candidates": [
                    {
                        "page": m.page_number,
                        "start": m.start,
                        "end": m.end,
                        "text": m.matched_text,
                        "strong": m.is_strong,
                        "score": m.score,
                        "words": [{"text": w.text, "bbox": w.bbox.to_dict()} for w in m.words],
                    }
                    for m in candidates
                ],
                "report": verify(data, document).to_dict(),
            }
        )
    api = []
    if args.api:
        from fastapi.testclient import TestClient

        from fieldproof.server.app import app

        with TestClient(app) as client:
            for result in results:
                path = HERE / "fixtures" / result["id"]
                uploaded = client.post(
                    "/api/documents",
                    files={
                        "file": (
                            path.with_suffix(".pdf").name,
                            path.with_suffix(".pdf").read_bytes(),
                            "application/pdf",
                        ),
                    },
                )
                assert uploaded.status_code == 200, uploaded.text
                document_id = uploaded.json()["id"]
                response = client.post(
                    f"/api/documents/{document_id}/extract",
                    data={
                        "schema": "receipt",
                        "provider": "fixture",
                    },
                    files={
                        "fixture": (
                            "fixture.json",
                            path.with_suffix(".json").read_bytes(),
                            "application/json",
                        )
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["report"] == result["report"]
                api.append(
                    {
                        "id": result["id"],
                        "status": response.status_code,
                        "report_matches_library": True,
                    }
                )
                assert client.delete(f"/api/documents/{document_id}").status_code == 204
    result = {
        "implementation_sha256": hashlib.sha256(
            (Path(fieldproof.__file__).parent / "ground/align.py").read_bytes()
        ).hexdigest(),
        "cases": results,
        "api": api,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for case in results:
        print(case["id"], len(case["candidates"]), case["report"]["fields"][0]["status"])


if __name__ == "__main__":
    main()
