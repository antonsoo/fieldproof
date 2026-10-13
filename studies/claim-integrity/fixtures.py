"""Generate explicitly synthetic claims; requires the development ReportLab dependency."""
import json
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
FIXTURES.mkdir(exist_ok=True)
pdf = Canvas(str(FIXTURES / "synthetic-invoice.pdf"), invariant=True)
for index, text in enumerate([
    "SYNTHETIC INVOICE - extraction parser controls", "Example Works", "Invoice TEST-1",
    "Issued 2026-10-13", "Widget 1 100.00 100.00", "Total $100.00",
]):
    pdf.drawString(40, 760 - index * 26, text)
pdf.save()

data = {
    "vendor_name": {"value": "Example Works", "evidence": ["Example Works"], "page": 1},
    "invoice_number": {"value": "TEST-1", "evidence": ["Invoice TEST-1"], "page": 1},
    "issue_date": {"value": "2026-10-13", "evidence": ["Issued 2026-10-13"], "page": 1},
    "total": {"value": 100.0, "evidence": ["Total $100.00"], "page": 1},
}
base = json.dumps(data)
def changed(fn):
    copy = json.loads(base)
    fn(copy)
    return json.dumps(copy)

cases = [
    ("valid", base, True),
    ("valid-defaults", changed(lambda d: d.update(line_items=[], currency=None)), True),
    ("duplicate-value", base.replace('"total": {', '"total": {"value": 900, '), False),
    ("duplicate-escaped-value", base.replace('"total": {"value":', '"total": {"val\\u0075e": 900, "value":'), False),
    ("duplicate-evidence", base.replace('"evidence": ["Total $100.00"]', '"evidence": ["Total $900.00"], "evidence": ["Total $100.00"]'), False),
    ("duplicate-total", base.replace('"total": {', '"total": {"value":900,"evidence":["Total $900.00"],"page":1},"total": {'), False),
    ("unknown-claim", changed(lambda d: d.update(bank_account={"value": "SYNTHETIC-UNSUPPORTED", "evidence": ["No such account"], "page": 1})), False),
    ("unknown-wrapper", changed(lambda d: d["total"].update(original_value=900)), False),
    ("unknown-row", changed(lambda d: d.update(line_items=[{
        "description": {"value": "Widget", "evidence": ["Widget"], "page": 1},
        "amount": {"value": 100, "evidence": ["Widget 1 100.00 100.00"], "page": 1},
        "discount": {"value": 900, "evidence": ["No such discount"], "page": 1},
    }])), False),
    ("nonfinite", base.replace('"value": 100.0', '"value": NaN'), False),
    ("overflow", base.replace('"value": 100.0', '"value": 1e999'), False),
    ("unpaired-surrogate", base.replace("Example Works", "\\ud800"), False),
]
manifest = []
for name, text, accepted in cases:
    raw = ('{"schema":"invoice","provider":"fixture","model":"synthetic-claims",'
           '"data":' + text + '}\n')
    (FIXTURES / f"{name}.json").write_text(raw)
    (FIXTURES / f"{name}.reply.txt").write_text(text)
    manifest.append({"id": name, "accepted": accepted, "fixture": f"{name}.json", "reply": f"{name}.reply.txt"})
for name, encoding, bom in [("valid-utf8-bom", "utf-8", b'\xef\xbb\xbf'), ("valid-utf16le", "utf-16-le", b'\xff\xfe'), ("valid-utf16be", "utf-16-be", b'\xfe\xff')]:
    path = FIXTURES / f"{name}.json"
    path.write_bytes(bom + (FIXTURES / "valid.json").read_text().encode(encoding))
    manifest.append({"id": name, "accepted": True, "fixture": path.name, "reply": None})
(HERE / "cases.json").write_text(json.dumps({"label": "Synthetic malformed extraction controls; no provider API called", "cases": manifest}, indent=2) + '\n')
