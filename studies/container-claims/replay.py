"""Replay declared custom-schema containers against a real, labelled synthetic PDF.

Run with the chosen environment's Python: replay.py OUTPUT.json [--source CHECKOUT].
Omit --source to exercise an installed package. No network or model calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--source', type=Path)
parser.add_argument('--expect', choices=['before', 'after'], default='after')
args = parser.parse_args()
if args.source:
    sys.path.insert(0, str(args.source.resolve() / 'src'))

import pydantic
from pydantic import BaseModel, create_model
from fieldproof.document import load_pdf
from fieldproof.schemas import Evidenced, iter_evidenced_fields
from fieldproof.verify import verify

Claim = Evidenced[str | float]
good = Claim(value='Example Works', evidence=['Example Works'])
missing = Claim(value='UNSUPPORTED BANK ACCOUNT', evidence=[])
name = Claim(value='Alpha', evidence=['Alpha'])
amount = Claim(value=10.0, evidence=['10.00'])

class Scalar(BaseModel):
    vendor: Claim
    bank_account: Claim

class Listed(BaseModel):
    claims: list[Claim]

class Mapped(BaseModel):
    claims: dict[str, Claim]

class Paired(BaseModel):
    claims: tuple[Claim, Claim]

class Nested(BaseModel):
    claims: dict[str, list[tuple[Claim, Claim]]]

class Child(BaseModel):
    b: Claim

Collision = create_model('Collision', **{'a.b': (Claim, ...), 'a': (Child, ...)})

class Row(BaseModel):
    name: Claim
    amount: Claim

class MappedRows(BaseModel):
    groups: dict[str, list[Row]]

class IntegerKeys(BaseModel):
    claims: dict[int, Claim]

cases = [
    ('scalar-control', Scalar(vendor=good, bank_account=missing)),
    ('list-control', Listed(claims=[good, missing])),
    ('mapping', Mapped(claims={'vendor': good, 'bank_account': missing})),
    ('tuple', Paired(claims=(good, missing))),
    ('nested', Nested(claims={'a.b[0]': [(good, missing)]})),
    ('model-name-collision', Collision.model_validate({'a.b': missing, 'a': {'b': good}})),
    ('mapping-row-lookalikes', Mapped(claims={'items[0].name': name, 'items[0].amount': amount})),
    ('quoted-row-lookalikes', Mapped(claims={'x"].items[0].name': name, 'x"].items[0].amount': amount})),
    ('mapped-real-row', MappedRows(groups={'x"].items[9]': [Row(name=name, amount=amount)]})),
    ('non-string-key', IntegerKeys(claims={1: missing})),
]
pdf = Path(__file__).with_name('synthetic-containers.pdf').read_bytes()
document = load_pdf(pdf)
records = []
for label, model in cases:
    try:
        paths = [path for path, _ in iter_evidenced_fields(model)]
        report = verify(model, document).to_dict()
        result = dict(paths=paths, report=report)
    except ValueError as error:
        result = dict(error=str(error))
    if args.expect == 'after' and label == 'non-string-key':
        assert "must use string keys" in result.get('error', ''), result
    else:
        expected = {'verified': 1, 'needs_review': 0, 'unsupported': 1}
        if args.expect == 'before' and label not in ('scalar-control', 'list-control'):
            expected = {'verified': int(label == 'model-name-collision'), 'needs_review': 0, 'unsupported': 0}
        elif args.expect == 'after' and label.endswith('row-lookalikes'):
            expected = {'verified': 1, 'needs_review': 1, 'unsupported': 0}
        elif args.expect == 'after' and label == 'mapped-real-row':
            expected = {'verified': 2, 'needs_review': 0, 'unsupported': 0}
        assert result['report']['counts'] == expected, (label, result)
        if args.expect == 'after':
            assert len(result['paths']) == len(set(result['paths'])) == len(result['report']['fields']) == 2
    records.append(dict(case=label, schema=model.model_json_schema(), data=model.model_dump(mode='json'), **result))
args.output.write_text(json.dumps(dict(python=sys.version.split()[0], pydantic=pydantic.__version__,
    documentSha256=hashlib.sha256(pdf).hexdigest(), inputKind='labelled synthetic PDF and custom Pydantic models',
    package='source' if args.source else 'installed', expected=args.expect, cases=records), indent=2) + '\n')
for record in records:
    print(record['case'], record.get('error', record.get('report', {}).get('counts')))
