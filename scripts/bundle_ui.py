"""Build the review UI and copy it into the package, so a wheel built afterwards
serves it from `fieldproof serve` with no Node toolchain on the user's machine.

    uv run python scripts/bundle_ui.py && uv build

The copy (src/fieldproof/server/static/) is build output and stays out of git;
pyproject.toml lists it as a build artifact so the wheel and sdist include it.
Source maps and the static demo's fixture data are left out.
"""

import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
web = root / "web"
static = root / "src" / "fieldproof" / "server" / "static"

subprocess.run(["npm", "ci"], cwd=web, check=True)
subprocess.run(["npm", "run", "build"], cwd=web, check=True)

if static.exists():
    shutil.rmtree(static)
(static / "assets").mkdir(parents=True)
shutil.copy(web / "dist" / "index.html", static / "index.html")
for asset in (web / "dist" / "assets").iterdir():
    if asset.suffix != ".map":
        shutil.copy(asset, static / "assets" / asset.name)
files = sorted(p.relative_to(static).as_posix() for p in static.rglob("*") if p.is_file())
print(f"bundled {len(files)} UI files into {static.relative_to(root)}: {', '.join(files)}")
