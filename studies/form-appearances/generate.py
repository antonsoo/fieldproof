"""Author static AcroForm controls; all values and invoices are synthetic."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from reportlab.lib.colors import black, white
from reportlab.pdfbase.pdfdoc import PDFArray, PDFDictionary, PDFStream
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
CASES = [
    {"id": "filled-text", "value": "$100.00"},
    {"id": "covered-native-total", "value": "$100.00", "cover": True},
    {"id": "empty-text", "value": ""},
    {"id": "hidden-text", "value": "$100.00", "hidden": True},
    {"id": "checkbox-checked", "checkbox": True, "checked": True},
    {"id": "checkbox-unchecked", "checkbox": True, "checked": False},
    {"id": "choice", "choice": True, "value": "Net 30"},
    *(
        {"id": f"rotation-{angle}", "value": "$100.00", "rotation": angle}
        for angle in (90, 180, 270)
    ),
    {"id": "cropped", "value": "$100.00", "crop": True},
    {"id": "native-only", "plain": True},
    {"id": "form-only", "value": "$100.00", "no_native": True},
    {"id": "xfa-unsupported", "xfa": True},
]


def make(case: dict) -> bytes:
    stream = io.BytesIO()
    pagesize = (792, 612) if case.get("rotation") in (90, 270) else (612, 792)
    pdf = Canvas(stream, pagesize=pagesize, invariant=True, pageCompression=1)
    pdf.setTitle("Synthetic static PDF form appearance control")
    pdf.setAuthor("Fieldproof fixture generator")
    if case.get("rotation"):
        pdf.setPageRotation(case["rotation"])
    if case.get("crop"):
        pdf.setCropBox((20, 420, 570, 770))
    if not case.get("no_native"):
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(48, 724, "SYNTHETIC FORM - no real transaction")
        pdf.setFont("Helvetica", 16)
        pdf.drawString(48, 680, "Visible native amount: $42.00")
        pdf.drawString(48, 620, "Authorized total:")
        if case.get("cover"):
            pdf.drawString(230, 620, "$900.00")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(48, 520, "Saved widget appearances; values are invented controls.")
        if case.get("cover"):
            pdf.drawString(48, 480, "Example Forms Ltd.")
            pdf.drawString(48, 456, "Invoice FORM-001")
            pdf.drawString(48, 432, "Issued: 2026-10-19")
    common = {
        "name": "authorized_total",
        "x": 225,
        "y": 611,
        "fillColor": white,
        "textColor": black,
        "borderColor": black,
        "forceBorder": True,
    }
    if case.get("checkbox"):
        pdf.acroForm.checkbox(**common, size=24, checked=case["checked"], borderWidth=1)
    elif case.get("choice"):
        pdf.acroForm.choice(
            **common,
            width=190,
            height=30,
            fontSize=18,
            value=case["value"],
            options=["Net 30", "Net 60"],
        )
    elif case.get("xfa"):
        pdf._doc.Catalog.AcroForm = PDFDictionary(
            {
                "Fields": PDFArray([]),
                "XFA": PDFStream(content=b'<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/"/>'),
            }
        )
    elif not case.get("plain"):
        pdf.acroForm.textfield(
            **common,
            width=190,
            height=30,
            fontSize=18,
            value=case["value"],
            borderWidth=0,
            annotationFlags="hidden" if case.get("hidden") else "print",
        )
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def main() -> None:
    fixtures = HERE / "fixtures"
    fixtures.mkdir(exist_ok=True)
    manifest = []
    for case in CASES:
        data = make(case)
        (fixtures / f"{case['id']}.pdf").write_bytes(data)
        manifest.append({**case, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (HERE / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    claim = {
        "schema": "invoice",
        "data": {
            "vendor_name": {"value": "Example Forms Ltd.", "evidence": ["Example Forms Ltd."]},
            "invoice_number": {"value": "FORM-001", "evidence": ["FORM-001"]},
            "issue_date": {"value": "2026-10-19", "evidence": ["Issued: 2026-10-19"]},
            "total": {"value": 900, "evidence": ["Authorized total: $900.00"]},
        },
    }
    (HERE / "claim.json").write_text(json.dumps(claim, indent=2) + "\n")


if __name__ == "__main__":
    main()
