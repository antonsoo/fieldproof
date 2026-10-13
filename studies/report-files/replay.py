"""Replay CLI report writes against disposable copies of the bundled invoice.

Usage: python replay.py NEW_DIRECTORY before|after [--source CHECKOUT]
The POSIX file-size limit applies only to two child processes, never this host.
No live provider is called. Omit --source to check an installed package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHILD = """
import os, sys
os.umask(0o022)
if sys.argv.pop(1) == 'limited':
    import resource, signal
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))
from fieldproof.cli import app
app()
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("phase", choices=["before", "after"])
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(NO_COLOR="1", COLUMNS="180", PYTHONDONTWRITEBYTECODE="1")
    if args.source:
        env["PYTHONPATH"] = str(args.source.resolve() / "src")
    pdf = (ROOT / "examples/invoice.pdf").read_bytes()
    fixture = (ROOT / "examples/fixtures/invoice.json").read_bytes()
    extract = [
        "extract",
        "invoice.pdf",
        "--schema",
        "invoice",
        "--provider",
        "fixture",
        "--fixture",
        "fixture.json",
    ]

    def prepare(name):
        directory = root / name
        directory.mkdir()
        (directory / "invoice.pdf").write_bytes(pdf)
        (directory / "fixture.json").write_bytes(fixture)
        return directory

    def invoke(directory, command, limited=False):
        result = subprocess.run(
            [sys.executable, "-c", CHILD, "limited" if limited else "normal", *command],
            cwd=directory,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        return {
            "exit": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr_has_traceback": "Traceback" in result.stderr,
            "stderr_tail": result.stderr.strip().splitlines()[-1:],
        }

    seed_dir = prepare("seed")
    assert invoke(seed_dir, [*extract, "--out", "result.json"])["exit"] == 0
    seed = (seed_dir / "result.json").read_bytes()
    seed_counts = json.loads(seed)["report"]["counts"]
    cases = []
    for operation, protected in [
        ("extract", "invoice.pdf"),
        ("extract", "fixture.json"),
        ("verify", "invoice.pdf"),
    ]:
        for alias in ["direct", "normalized", "parent-link", "symbolic", "hard"]:
            name = f"{operation}-{protected}-{alias}"
            directory = prepare(name)
            (directory / "result.json").write_bytes(seed)
            destination = protected
            if alias == "normalized":
                (directory / "sub").mkdir()
                destination = "sub/../" + protected
            elif alias == "parent-link":
                (directory / "alias").symlink_to(".", target_is_directory=True)
                destination = "alias/" + protected
            elif alias == "symbolic":
                destination = "output.json"
                (directory / destination).symlink_to(protected)
            elif alias == "hard":
                destination = "output.json"
                os.link(directory / protected, directory / destination)
            originals = {
                p: (directory / p).read_bytes()
                for p in ["invoice.pdf", "fixture.json", "result.json"]
            }
            command = (
                extract if operation == "extract" else ["verify", "result.json", "invoice.pdf"]
            )
            outcome = invoke(directory, [*command, "--out", destination])
            unchanged = {p: (directory / p).read_bytes() == data for p, data in originals.items()}
            assert outcome["exit"] == (2 if args.phase == "after" else 0), (name, outcome)
            assert all(unchanged.values()) if args.phase == "after" else not unchanged[protected]
            assert not outcome["stderr_has_traceback"]
            cases.append({"case": name, **outcome, "inputs_unchanged": unchanged})

    for dangling in [False, True]:
        name = "dangling-output-link" if dangling else "existing-output-link"
        directory = prepare(name)
        target = directory / "previous.json"
        previous = b'{"previous_report": true}\n'
        if not dangling:
            target.write_bytes(previous)
        (directory / "output.json").symlink_to(target.name)
        outcome = invoke(directory, [*extract, "--out", "output.json"])
        preserved = not target.exists() if dangling else target.read_bytes() == previous
        assert outcome["exit"] == (2 if args.phase == "after" else 0)
        assert preserved is (args.phase == "after")
        cases.append(
            {
                "case": name,
                **outcome,
                "link_preserved": (directory / "output.json").is_symlink(),
                "target_preserved": preserved,
            }
        )

    for operation in ["extract", "verify"]:
        directory = prepare(operation + "-short-write")
        (directory / "result.json").write_bytes(seed)
        command = (
            [*extract, "--out", "result.json"]
            if operation == "extract"
            else ["verify", "result.json", "invoice.pdf"]
        )
        outcome = invoke(directory, command, limited=True)
        remaining = (directory / "result.json").read_bytes()
        preserved = remaining == seed
        assert outcome["exit"] == (2 if args.phase == "after" else 1), outcome
        assert preserved is (args.phase == "after")
        assert (directory / "invoice.pdf").read_bytes() == pdf
        assert (directory / "fixture.json").read_bytes() == fixture
        leftovers = sorted(
            p.name
            for p in directory.iterdir()
            if p.name not in {"invoice.pdf", "fixture.json", "result.json"}
        )
        assert not leftovers, leftovers
        cases.append(
            {
                "case": operation + "-short-write",
                **outcome,
                "previous_report_preserved": preserved,
                "previous_bytes": len(seed),
                "remaining_bytes": len(remaining),
                "temporary_files_left": leftovers,
            }
        )

    controls = []
    directory = prepare("normal-workflow")
    for name, command, output in [
        ("extract", [*extract, "--out", "result.json"], "result.json"),
        ("verify-in-place", ["verify", "result.json", "invoice.pdf"], "result.json"),
        (
            "verify-copy",
            ["verify", "result.json", "invoice.pdf", "--out", "copy.json"],
            "copy.json",
        ),
    ]:
        outcome = invoke(directory, command)
        report = json.loads((directory / output).read_bytes())
        assert outcome["exit"] == 0 and report["report"]["counts"] == seed_counts
        mode = stat.S_IMODE((directory / output).stat().st_mode)
        if args.phase == "after":
            assert mode == 0o600
        controls.append(
            {
                "case": name,
                **outcome,
                "counts": report["report"]["counts"],
                "mode": oct(mode),
                "report_sha256": digest((directory / output).read_bytes()),
            }
        )
    assert (directory / "invoice.pdf").read_bytes() == pdf
    assert (directory / "fixture.json").read_bytes() == fixture
    print(
        json.dumps(
            {
                "phase": args.phase,
                "scope": "Bundled synthetic invoice, actual CLI subprocesses, no remote provider.",
                "inputs": {
                    "invoice.pdf": {"bytes": len(pdf), "sha256": digest(pdf)},
                    "fixture.json": {"bytes": len(fixture), "sha256": digest(fixture)},
                },
                "child_write_limit_bytes": 4096,
                "cases": cases,
                "controls": controls,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
