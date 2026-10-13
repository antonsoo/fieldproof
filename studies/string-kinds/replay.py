"""Replay synthetic PDF claims through fixture extraction and public verification.

Use NEW_OUTPUT_DIRECTORY before|after [--source CHECKOUT]. Omit --source for
an installed package. Explicit-kind cases use plain Evidenced[str] at baseline;
their input JSON is unchanged, but the new schema opts into a declared kind.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('output',type=Path)
p.add_argument('mode',choices=['before','after'])
p.add_argument('--source',type=Path)
args=p.parse_args()
if args.source: sys.path.insert(0,str(args.source.resolve()/'src'))
args.output.mkdir(parents=True,exist_ok=False)

import pydantic
from pydantic import create_model
from fieldproof.document import load_pdf
from fieldproof.extract import FixtureExtractor
from fieldproof import schemas
from fieldproof.verify import verify

here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
E=schemas.Evidenced[str]
def model_and_input(case):
    wrapper = E if args.mode=='before' or case['kind']=='inferred' else getattr(schemas,'Evidenced'+case['kind'].title())
    claim={'value':case['value'],'evidence':[case['quote']] if case['quote'] else [],'page':1}
    name=case['name']
    leaf=create_model('Leaf',**{name:(wrapper,...)})
    shape=case['shape']
    if shape=='leaf': return leaf,{name:claim}
    if shape=='nested': return create_model('Envelope',date_record=(leaf,...)),{'date_record':{name:claim}}
    if shape=='mapping': return create_model('Mapped',claims=(dict[str,wrapper],...)),{'claims':{name:claim}}
    if shape=='mapped-model': return create_model('Mapped',claims=(dict[str,leaf],...)),{'claims':{'x"].issue_date':{name:claim}}}
    if shape=='sequence': return create_model('Sequence',**{name:(tuple[wrapper,...],...)}),{name:[claim]}
    if shape=='mapped-sequence': return create_model('Mapped',schedule=(dict[str,tuple[wrapper,...]],...)),{'schedule':{name:[claim]}}
    if shape=='row':
        row=create_model('Row',**{name:(wrapper,...),'amount':(schemas.Evidenced[float],...)})
        return create_model('Rows',rows=(list[row],...)),{'rows':[{name:claim,'amount':{'value':10.0,'evidence':['10.00'],'page':1}}]}
    raise ValueError(shape)

records=[]
for case in json.loads((here/'cases.json').read_text())['cases']:
    schema,raw=model_and_input(case)
    payload=json.dumps({'schema':schema.__name__,'data':raw},indent=2).encode()
    fixture=args.output/(case['id']+'.json');fixture.write_bytes(payload)
    pdf=here/(case['pdf']+'.pdf');doc=load_pdf(pdf)
    extraction=FixtureExtractor(fixture).extract(doc,schema)
    assert extraction.data.model_dump(mode='json')==raw
    restored=schema.model_validate_json(extraction.data.model_dump_json())
    options=dict(text_edit_tolerance=case['tolerance'],default_date_order=case['defaultDateOrder'])
    report=verify(extraction.data,doc,**options).to_dict()
    assert verify(restored,doc,**options).to_dict()==report
    expected=case['expectedBefore' if args.mode=='before' else 'expectedAfter']
    assert [f['status'] for f in report['fields']]==expected,(case['id'],report)
    conflict=any('date conventions' in reason for field in report['fields'] for reason in field['reasons'])
    if case['expectedConflict'] is not None:
        assert conflict==case['expectedConflict'][args.mode=='after'],(case['id'],report)
    if args.mode=='after' and case['kind']!='inferred':
        assert report['fields'][0]['declared_kind']==case['kind']
    records.append(dict(case=case['id'],inputSha256=sha(payload),documentSha256=sha(pdf.read_bytes()),
                        declaredKind=case['kind'],schema=schema.model_json_schema(),data=raw,options=options,report=report))
    print(case['id'],[f['status'] for f in report['fields']],flush=True)
record=dict(mode=args.mode,python=sys.version.split()[0],pydantic=pydantic.__version__,
            package='source' if args.source else 'installed',fixtureInputsPreserved=True,jsonRoundtripReportsIdentical=True,
            builtinSchemaSha256={name:sha(json.dumps(model.model_json_schema(),sort_keys=True).encode()) for name,model in schemas.BUILTIN_SCHEMAS.items()},
            cases=records,liveModelCalled=False)
(args.output/'results.json').write_text(json.dumps(record,indent=2)+'\n')
