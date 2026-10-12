"""Download in a browser, stop the server, then reopen in a fresh browser/server."""

import argparse
import subprocess
from pathlib import Path

from restart import server

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--python", required=True)
parser.add_argument("--node", default="node")
parser.add_argument(
    "--tools", type=Path, required=True, help="web/ containing installed Playwright"
)
parser.add_argument(
    "--static", type=Path, required=True, help="Exact built assets served by the server"
)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--installed", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
for phase in ["save", "restore"]:
    with server(
        args.source.resolve(), args.python, args.output / "server.log", installed=args.installed
    ) as client:
        assert client.get("/api/documents").json()["documents"] == []
        subprocess.run(
            [
                args.node,
                str(Path(__file__).with_suffix(".mjs")),
                "--url",
                str(client.base_url),
                "--phase",
                phase,
                "--source",
                str(args.source.resolve()),
                "--tools",
                str(args.tools.resolve()),
                "--static",
                str(args.static.resolve()),
                "--output",
                str(args.output.resolve()),
            ],
            check=True,
        )
