"""CLI, API and real SDK parser replay. No network API or live model.
python replay.py NEW_OUTPUT_DIRECTORY before|after [--source CHECKOUT]
The installed-artifact run omits --source. HTTP tests require the dev httpx dependency.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('mode', choices=['before', 'after'])
parser.add_argument('--source', type=Path)
args = parser.parse_args()
if args.source:
    sys.path.insert(0, str(args.source.resolve() / 'src'))
    os.environ['PYTHONPATH'] = str(args.source.resolve() / 'src')
else:
    os.environ.pop('PYTHONPATH', None)
args.output.mkdir(parents=True, exist_ok=False)

import anthropic
import fieldproof
import pydantic
from fastapi.testclient import TestClient
from fieldproof.document import load_pdf
from fieldproof.extract.anthropic_provider import AnthropicExtractor
from fieldproof.extract.base import ExtractionError
from fieldproof.schemas import Invoice
from fieldproof.server.app import app
from fieldproof.server.store import store
from fieldproof.verify import verify

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
pdf = (FIXTURES / 'synthetic-invoice.pdf').read_bytes()
document = load_pdf(pdf)
cases = json.loads((HERE / 'cases.json').read_text())['cases']
sha = lambda b: hashlib.sha256(b).hexdigest()
control = (FIXTURES / 'valid.json').read_bytes()
client = TestClient(app, raise_server_exceptions=False)
http = next(importlib.import_module(c.__module__.split('.')[0]) for c in anthropic.DefaultHttpxClient.__mro__[1:] if c.__module__.startswith('httpx'))

def sdk_reply(text):
    message = {'id': 'msg_synthetic', 'type': 'message', 'role': 'assistant', 'model': 'controlled-fixture',
               'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 0}}
    events = [{'type': 'message_start', 'message': message},
              {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}]
    events.extend({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text[i:i+17]}} for i in range(0, len(text), 17))
    events += [{'type': 'content_block_stop', 'index': 0},
               {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 300}},
               {'type': 'message_stop'}]
    return ''.join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()

def invoke(arguments):
    p = subprocess.run([sys.executable, '-m', 'fieldproof.cli', *map(str, arguments)], capture_output=True, timeout=45)
    clean = lambda b: b.decode('utf-8', errors='replace').replace(str(args.output.resolve()), 'OUTPUT').replace(str(FIXTURES), 'FIXTURES')
    return {'exit': p.returncode, 'stdout': clean(p.stdout), 'stderr': clean(p.stderr)}

def upload():
    r = client.post('/api/documents', files={'file': ('synthetic-invoice.pdf', pdf, 'application/pdf')})
    assert r.status_code == 200, r.text
    return r.json()['id']

def extract(docid, body, name):
    return client.post(f'/api/documents/{docid}/extract', data={'schema': 'invoice', 'provider': 'fixture'},
                       files={'fixture': (name, body, 'application/json')})

rows = []
for case in cases:
    name = case['id']; raw = (FIXTURES / case['fixture']).read_bytes()
    folder = args.output / name; folder.mkdir()
    target = folder / 'report.json'; sentinel = b'PREVIOUS REPORT MUST SURVIVE\n'; target.write_bytes(sentinel)
    cli = invoke(['extract', FIXTURES / 'synthetic-invoice.pdf', '--provider', 'fixture', '--fixture', FIXTURES / case['fixture'], '--out', target])
    cli['previousReportPreserved'] = target.read_bytes() == sentinel
    if cli['exit'] == 0:
        parsed = json.loads(target.read_bytes())
        cli['counts'] = parsed['report']['counts']; cli['fields'] = [f['path'] for f in parsed['report']['fields']]
        cli['reportSha256'] = sha(target.read_bytes())
    saved = folder / 'saved-result.json'; saved.write_bytes(raw)
    reverify = invoke(['verify', saved, FIXTURES / 'synthetic-invoice.pdf'])
    reverify['originalClaimsPreserved'] = saved.read_bytes() == raw

    store._sessions.clear()
    docid = upload(); assert extract(docid, control, 'valid.json').status_code == 200
    assert client.post(f'/api/documents/{docid}/review', json={'path': 'total', 'action': 'edit', 'value': 123.5}).status_code == 200
    before = client.get(f'/api/documents/{docid}/report').content
    response = extract(docid, raw, case['fixture'])
    after = client.get(f'/api/documents/{docid}/report').content
    api = {'status': response.status_code, 'previousReportAndCorrectionPreserved': after == before,
           'body': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text}
    retry = extract(docid, control, 'valid.json'); api['validRetryStatus'] = retry.status_code
    assert retry.status_code == 200
    sdk = None
    if case['reply']:
        reply = (FIXTURES / case['reply']).read_text(); requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            return http.Response(200, headers={'content-type': 'text/event-stream'}, content=sdk_reply(reply))
        transport = http.MockTransport(handle)
        with anthropic.Anthropic(api_key='synthetic-test-key', http_client=http.Client(transport=transport), max_retries=0) as sdk_client:
            try:
                result = AnthropicExtractor(client=sdk_client).extract(document, Invoice)
                report = verify(result.data, document)
                sdk = {'accepted': True, 'counts': report.counts, 'fields': [f.path for f in report.fields]}
            except ExtractionError as error:
                sdk = {'accepted': False, 'error': str(error)}
        assert len(requests) == 1
        sdk['requestCount'] = len(requests)
        sdk['replySha256'] = sha(reply.encode())
    if args.mode == 'after':
        if case['accepted']:
            assert cli['exit'] == reverify['exit'] == 0, (name, cli, reverify)
            assert api['status'] == 200, (name, api)
            if sdk: assert sdk['accepted'], (name, sdk)
        else:
            assert cli['exit'] != 0 and cli['previousReportPreserved'], (name, cli)
            assert reverify['exit'] != 0 and reverify['originalClaimsPreserved'], (name, reverify)
            assert api['status'] == 422 and api['previousReportAndCorrectionPreserved'], (name, api)
            if sdk: assert not sdk['accepted'], (name, sdk)
    rows.append({'case': name, 'expectedAccepted': case['accepted'], 'inputSha256': sha(raw), 'cli': cli, 'reverify': reverify, 'api': api, 'sdk': sdk})
    print(f"{name}: CLI {cli['exit']}, verify {reverify['exit']}, API {api['status']}, SDK {sdk and sdk['accepted']}", flush=True)

record = {'mode': args.mode, 'python': sys.version.split()[0], 'pydantic': pydantic.__version__, 'anthropic': anthropic.__version__,
          'sourceImport': 'source/src/fieldproof' if args.source else 'installed site-packages/fieldproof',
          'documentSha256': sha(pdf), 'cases': rows, 'liveModelCalled': False}
(args.output / 'results.json').write_text(json.dumps(record, indent=2, ensure_ascii=True) + '\n')
