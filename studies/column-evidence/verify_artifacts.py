"""Verify the retained study artifact layout after clean builds and installed replays."""

import argparse
import hashlib
import json
import platform
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", required=True, type=Path)
parser.add_argument("--scratch", required=True, type=Path)
args = parser.parse_args()
root = args.repo.resolve()
s = args.scratch.resolve()
clean = s / "clean"


def digest(b):
    return hashlib.sha256(b).hexdigest()


def info(p):
    b = p.read_bytes()
    return {"file": p.name, "bytes": len(b), "sha256": digest(b)}


core = subprocess.check_output(["git", "rev-parse", "6dfb2ee"], cwd=root, text=True).strip()
tracked = subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", core], cwd=root, text=True
).splitlines()
inputs = [
    p
    for p in tracked
    if p.startswith(("src/", "tests/", "web/src/", "examples/"))
    or p
    in (
        "README.md",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "web/package.json",
        "web/package-lock.json",
        "web/index.html",
        "web/tsconfig.json",
        "web/vite.config.ts",
        "scripts/bundle_ui.py",
    )
]
for p in inputs:
    assert (root / p).read_bytes() == (clean / p).read_bytes(), p
sdist = clean / "dist/fieldproof-0.2.7.tar.gz"
wheel = clean / "dist/fieldproof-0.2.7-py3-none-any.whl"
with zipfile.ZipFile(wheel) as z, tarfile.open(sdist) as t:
    package = {
        n: z.read(n) for n in z.namelist() if n.startswith("fieldproof/") and not n.endswith("/")
    }
    for name, b in package.items():
        assert b == (clean / "src" / name).read_bytes(), name
        assert b == t.extractfile("fieldproof-0.2.7/src/" + name).read(), name
        for version in ("311", "314"):
            site = next((s / f"installed{version}/lib").glob("python*/site-packages"))
            assert b == (site / name).read_bytes(), (version, name)
    modules = [n for n in package if n.endswith(".py")]
assets = []
local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for p in sorted((clean / "src/fieldproof/server/static").rglob("*")):
    if p.is_file():
        rel = p.relative_to(clean / "src/fieldproof/server/static").as_posix()
        for port in (4393, 4394):
            assert (
                local_http.open(f"http://127.0.0.1:{port}/{rel}", timeout=5).read()
                == p.read_bytes()
            ), (port, rel)
        assets.append(rel)
for v in ("311", "314"):
    for p in (s / "current").glob("*.json"):
        assert p.read_bytes() == (s / f"replay{v}" / p.name).read_bytes(), (v, p.name)
cli = list((s / "cli311").glob("*.json"))
assert len(cli) == 20
for p in cli:
    assert p.read_bytes() == (s / "cli314" / p.name).read_bytes(), p.name
for browser in ("chromium", "firefox"):
    observation = json.loads(
        (root / f"docs/assets/column-evidence/after-{browser}.json").read_text()
    )
    assert (
        observation["report"]
        == json.loads((s / "cli314/column-evidence.json").read_text())["report"]
    )
    before = json.loads((root / f"docs/assets/column-evidence/before-{browser}.json").read_text())
    assert before["report"] == json.loads(
        (s / "before/0-1-2-3-left-swapped-token.report.json").read_text()
    )
    for a, b in zip(before["exported"], observation["exported"], strict=True):
        assert {k: v for k, v in a.items() if k != "verification_status"} == {
            k: v for k, v in b.items() if k != "verification_status"
        }
logs = [
    "clean-checks.log",
    "clean-build.log",
    "clean-web-checks.log",
    "package-build.log",
    "installed311-tests.log",
    "installed314-tests.log",
    "browser-before.log",
    "browser-after.log",
    "browser-full.log",
]
for name in ("clean-checks.log", "installed311-tests.log", "installed314-tests.log"):
    assert "437 passed, 1 skipped" in (s / name).read_text(), name
for name in ("browser-before.log", "browser-after.log"):
    assert "2 passed" in (s / name).read_text(), name
full = (s / "browser-full.log").read_text()
assert "76 passed" in full, full[-1500:]
result = {
    "baseline": "4cb9624f6a8342003bd81d7aea11e5e7cc1ddb25",
    "production_commit": core,
    "platform": platform.platform(),
    "cpu_count": subprocess.check_output(["nproc"], text=True).strip(),
    "runtime_versions": {
        v: subprocess.check_output(
            [str(s / f"installed{v}/bin/python"), "--version"], text=True
        ).strip()
        for v in ("311", "314")
    },
    "clean_runtime": (s / "clean-runtime.txt").read_text().strip(),
    "source_inputs_identical": len(inputs),
    "package_files_identical": len(package),
    "python_modules_identical": len(modules),
    "package_comparison": (
        "clean source, sdist, wheel, independent Python 3.11 and 3.14 installations"
    ),
    "archives": [info(sdist), info(wheel)],
    "served_assets_identical": len(assets),
    "served_comparison": "baseline server and installed current server, all 23 built UI assets",
    "installed_case_replays": {
        "cases_per_interpreter": 308,
        "files_per_interpreter": len(list((s / "current").glob("*.json"))),
        "byte_identical": True,
    },
    "installed_cli": {
        "workflows_per_interpreter": 20,
        "json_files_per_interpreter": len(cli),
        "byte_identical_between_interpreters": True,
    },
    "browser": {
        "full_scenarios": 76,
        "paired_scenarios": 4,
        "paired_viewports": 8,
        "engines": ["Chromium", "Firefox"],
        "widths": [1440, 375],
        "report_matches_cli": True,
        "scope": "Local native-PDF UI; source push only; no hosted deployment",
    },
    "tests": {"python_each": "437 passed, 1 skipped (real Tesseract unavailable)", "web_unit": 50},
    "logs": [info(s / name) for name in logs],
    "browser_harness": {
        "archive_sha256": digest((clean / "web/tests/browser/live.spec.mjs").read_bytes()),
        "final_sha256": digest((root / "web/tests/browser/live.spec.mjs").read_bytes()),
        "difference": (
            "Final screenshot capture filters the visible list to line_items "
            "using its accessible searchbox; runtime source unchanged."
        ),
    },
}
(root / "studies/column-evidence/results/artifacts.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(
    json.dumps(
        {
            k: result[k]
            for k in (
                "source_inputs_identical",
                "package_files_identical",
                "python_modules_identical",
                "served_assets_identical",
                "archives",
            )
        }
    )
)
