"""Capture actual CLI reports for all three built-in fixtures from a chosen package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('output',type=Path)
p.add_argument('--source',type=Path)
args=p.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parents[2]
env=dict(os.environ)
if args.source: env['PYTHONPATH']=str(args.source.resolve()/'src')
else: env.pop('PYTHONPATH',None)
records=[]
for name in ['invoice','receipt','contract']:
    target=args.output/(name+'.json')
    command=[sys.executable,'-m','fieldproof.cli','extract',str(root/'examples'/f'{name}.pdf'),
             '--schema',name,'--provider','fixture','--fixture',str(root/'examples/fixtures'/f'{name}.json'),
             '--out',str(target)]
    result=subprocess.run(command,env=env,capture_output=True,timeout=60)
    assert result.returncode==0,(name,result.stdout,result.stderr)
    data=target.read_bytes()
    report=json.loads(data)['report']
    records.append(dict(schema=name,exit=result.returncode,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                        counts=report['counts'],fields=len(report['fields'])))
(args.output/'results.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
