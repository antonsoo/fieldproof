"""Synthetic PDF replay of supported primitive and unsupported wrapped values.

Run OUTPUT before|after [--source CHECKOUT]. Without --source, use the installed
package. All schemas and fixture bytes are identical in both modes.
"""

import argparse
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("mode", choices=["before", "after"])
parser.add_argument("--source", type=Path)
args = parser.parse_args()
if args.source:
    sys.path.insert(0, str(args.source.resolve() / "src"))
args.output.mkdir(parents=True, exist_ok=False)

import pydantic
from pydantic import BaseModel, create_model
from fieldproof.document import load_pdf
from fieldproof.extract import FixtureExtractor
from fieldproof.schemas import Evidenced, EvidencedDate, EvidencedText
from fieldproof.verify import verify

here = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
pdf = here / "claims.pdf"
document = load_pdf(pdf)


class Details(BaseModel):
    account: str


class Account(Enum):
    UNKNOWN = "UNSUPPORTED"


cases = []


def case(
    name,
    annotation,
    value,
    quote="Example Works",
    *,
    before="verified",
    after="error",
    shape="leaf",
):
    cases.append((name, annotation, value, quote, before, after, shape))


case("object", dict[str, str], {"account": "UNSUPPORTED"})
case("array", list[str], ["UNSUPPORTED"])
case("tuple", tuple[str, ...], ["UNSUPPORTED"])
case("null", str | None, None)
case("decimal", Decimal, "999.99")
case("python-date", date, "2026-05-01")
case("python-datetime", datetime, "2026-05-01T12:00:00")
case("bytes", bytes, "UNSUPPORTED")
case("model", Details, {"account": "UNSUPPORTED"})
case("enum", Account, "UNSUPPORTED")
case("any-object", Any, {"account": "UNSUPPORTED"})
case("nested-object", dict[str, str], {"account": "UNSUPPORTED"}, shape="nested")
case(
    "object-without-quote",
    dict[str, str],
    {"account": "UNSUPPORTED"},
    quote="",
    before="unsupported",
)
case(
    "object-missing-quote",
    dict[str, str],
    {"account": "UNSUPPORTED"},
    quote="Not on this page",
    before="unsupported",
)
case(
    "object-ambiguous-quote",
    dict[str, str],
    {"account": "UNSUPPORTED"},
    quote="10.00",
    before="needs_review",
)
case("object-row-anchor", dict[str, str], {"account": "UNSUPPORTED"}, quote="Alpha", shape="row")
case("text-control", str, "Example Works", after="verified")
case("integer-control", int, 13, quote="13", after="verified")
case("float-control", float, 13.0, quote="13", after="verified")
case("boolean-control", bool, True, quote="Approval: yes", after="verified")
case("nullable-text-control", str | None, "Example Works", after="verified")
case("any-text-control", Any, "Example Works", after="verified")
case("mismatch-control", str, "UNSUPPORTED", before="needs_review", after="needs_review")
case("missing-control", str, "UNSUPPORTED", quote="", before="unsupported", after="unsupported")
case("optional-absent-control", str, None, before="empty", after="empty", shape="optional")
case(
    "outer-mapping-control",
    str,
    "UNSUPPORTED",
    before="needs_review",
    after="needs_review",
    shape="mapping",
)

records = []
for name, annotation, value, quote, before, after, shape in cases:
    wrapped = Evidenced[annotation]
    claim = {"value": value, "evidence": [quote] if quote else [], "page": 1}
    schema = create_model("Claim", account=(wrapped, ...))
    raw = {"account": claim}
    if shape == "nested":
        schema = create_model("Envelope", claims=(dict[str, tuple[wrapped, ...]], ...))
        raw = {"claims": {"slot[0].amount": [claim]}}
    elif shape == "row":
        row = create_model("Row", description=(wrapped, ...), amount=(Evidenced[float], ...))
        schema = create_model("Rows", rows=(list[row], ...))
        raw = {
            "rows": [
                {"description": claim, "amount": {"value": 10.0, "evidence": ["10.00"], "page": 1}}
            ]
        }
    elif shape == "optional":
        schema = create_model("OptionalClaim", account=(Evidenced[str] | None, None))
        raw = {"account": None}
    elif shape == "mapping":
        schema = create_model("Mapping", accounts=(dict[str, Evidenced[str]], ...))
        raw = {"accounts": {"primary": claim}}
    payload = json.dumps({"schema": schema.__name__, "data": raw}, indent=2).encode()
    fixture = args.output / (name + ".json")
    fixture.write_bytes(payload)
    extraction = FixtureExtractor(fixture).extract(document, schema)
    snapshot = extraction.data.model_dump_json()
    record = dict(
        case=name,
        input=raw,
        inputSha256=sha(payload),
        schemaSha256=sha(json.dumps(schema.model_json_schema(), sort_keys=True).encode()),
    )
    try:
        report = verify(extraction.data, document).to_dict()
        # Some baseline values are not JSON-serializable. Preserve them through
        # Pydantic's serializer solely for this evidence file, never as a repair.
        record["report"] = json.loads(pydantic.TypeAdapter(dict).dump_json(report))
        record["outcome"] = report["fields"][0]["status"] if report["fields"] else "empty"
    except ValueError as exc:
        record.update(outcome="error", errorType=type(exc).__name__, error=str(exc))
    assert extraction.data.model_dump_json() == snapshot, name
    assert record["outcome"] == (before if args.mode == "before" else after), record
    records.append(record)
    print(name, record["outcome"], flush=True)

# A caller can mutate a valid Pydantic wrapper after construction. An explicit
# string policy must not quietly switch to numeric checking after such a write.
for wrapper in [EvidencedDate, EvidencedText]:
    schema = create_model("TypedClaim", account=(wrapper, ...))
    data = schema(account=wrapper(value="2026-05-01", evidence=["13"], page=1))
    data.account.value = 13
    record = dict(case="mutated-" + wrapper.__name__, route="direct Python assignment", value=13)
    try:
        record["report"] = verify(data, document).to_dict()
        record["outcome"] = record["report"]["fields"][0]["status"]
    except ValueError as exc:
        record.update(outcome="error", errorType=type(exc).__name__, error=str(exc))
    assert data.account.value == 13
    assert record["outcome"] == ("verified" if args.mode == "before" else "error"), record
    records.append(record)
    print(record["case"], record["outcome"], flush=True)

result = dict(
    mode=args.mode,
    python=sys.version.split()[0],
    pydantic=pydantic.__version__,
    package="source" if args.source else "installed",
    documentSha256=sha(pdf.read_bytes()),
    cases=records,
    claimValuesUnmodified=True,
    liveModelCalled=False,
)
(args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
