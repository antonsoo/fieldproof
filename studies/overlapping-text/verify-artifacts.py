"""Compare the tested source, built distributions and installed package bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    scratch = args.scratch
    source = scratch / "clean/src/fieldproof"
    expected = {
        str(path.relative_to(source)): path.read_bytes()
        for path in sorted(source.rglob("*"))
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed"
                               or "static" in path.parts)
    }
    identities = []
    for artifact in sorted((scratch / "artifacts").iterdir()):
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                actual = {name.removeprefix("fieldproof/"): archive.read(name)
                          for name in archive.namelist()
                          if name.startswith("fieldproof/") and not name.endswith("/")}
        elif artifact.name.endswith(".tar.gz"):
            actual = {}
            with tarfile.open(artifact) as archive:
                for member in archive.getmembers():
                    if "/src/fieldproof/" in member.name and member.isfile():
                        handle = archive.extractfile(member)
                        assert handle is not None
                        actual[member.name.split("/src/fieldproof/", 1)[1]] = handle.read()
        else:
            continue
        assert actual == expected, artifact.name
        identities.append({"file": artifact.name, "bytes": artifact.stat().st_size,
                           "sha256": sha(artifact.read_bytes()), "packageFilesMatch": len(actual)})
    assert len(identities) == 2
    hashes = {name: sha(content) for name, content in expected.items()}
    installed = []
    code = """
import hashlib, json
from pathlib import Path
import fieldproof
root = Path(fieldproof.__file__).parent
print(json.dumps({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in root.rglob('*') if p.is_file() and (p.suffix == '.py' or p.name == 'py.typed'
                                              or 'static' in p.parts)}))
"""
    replay = json.loads((scratch / "clean-replay.json").read_text())
    for name in ("installed", "floor"):
        actual = json.loads(subprocess.check_output([str(scratch / name / "bin/python"), "-c", code]))
        assert hashes == actual, name
        result = json.loads((scratch / ("installed-current.json" if name == "installed"
                                       else "installed-floor.json")).read_text())
        assert result["mismatches"] == 0
        assert result["observations"] == replay["observations"], name
        installed.append({"environment": name, "python": result["python"],
                          "versions": result["versions"], "packageFilesMatch": len(hashes),
                          "allVerdictsReasonsGeometryMatch": True})
    report = {"sourceRevision": (scratch / "source-revision").read_text().strip(),
              "runtimeFiles": sum(name.endswith((".py", "py.typed")) for name in hashes),
              "bundledUIFiles": sum(name.startswith("server/static/") for name in hashes),
              "files": hashes, "artifacts": identities, "installations": installed}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Both distributions and installations match all {len(hashes)} package files")


if __name__ == "__main__":
    main()
