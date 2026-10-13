"""Run the actual upload/review/rejection workflow against source or an installed wheel."""
import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'review-archives'))
from restart import server

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--python', required=True)
p.add_argument('--tools', type=Path, required=True)
p.add_argument('--static', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--installed', action='store_true')
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
with server(args.source.resolve(), args.python, args.output / 'server.log', installed=args.installed) as client:
    subprocess.run(['node', str(HERE / 'browser.mjs'), '--url', str(client.base_url),
                    '--fixtures', str(HERE / 'fixtures'), '--tools', str(args.tools.resolve()),
                    '--static', str(args.static.resolve()), '--output', str(args.output.resolve())], check=True)
