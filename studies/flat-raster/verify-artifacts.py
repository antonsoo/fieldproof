"""Check source, distributions and installed replay bytes; no publication claim."""

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.scratch
    source = root / "clean/src/fieldproof"
    runtime = {
        str(path.relative_to(source)): path.read_bytes()
        for path in sorted(source.rglob("*"))
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed")
    }
    static = {
        str(path.relative_to(source)): path.read_bytes()
        for path in sorted((source / "server/static").rglob("*"))
        if path.is_file()
    }
    artifacts = []
    for path in sorted((root / "artifacts").iterdir()):
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                found = {
                    name.removeprefix("fieldproof/"): archive.read(name)
                    for name in archive.namelist()
                    if name.startswith("fieldproof/") and not name.endswith("/")
                }
        elif path.name.endswith(".tar.gz"):
            found = {}
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if "/src/fieldproof/" in member.name and member.isfile():
                        stream = archive.extractfile(member)
                        assert stream is not None
                        found[member.name.split("/src/fieldproof/", 1)[1]] = stream.read()
        else:
            continue
        assert found == runtime | static, path.name
        artifacts.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
                "packageFilesMatch": len(found),
            }
        )
    assert len(artifacts) == 2
    expected = json.loads((root / "clean/studies/flat-raster/results/after.json").read_text())
    hashes = {name: digest(raw) for name, raw in runtime.items()}
    assert expected["runtimeFiles"] == hashes
    observations = []
    for label in ("clean-replay", "installed-current", "installed-floor"):
        replay = json.loads((root / f"{label}.json").read_text())
        assert replay["runtimeFiles"] == hashes
        assert replay["observations"] == expected["observations"], label
        assert replay["mismatches"] == 0
        observations.append(
            {
                "label": label,
                "python": replay["python"],
                "versions": replay["versions"],
                "pdfs": replay["pdfs"],
                "claims": replay["claims"],
                "runtimeFilesMatch": len(hashes),
                "allVerdictsReasonsGeometryMatch": True,
            }
        )
    report = {
        "scope": __doc__,
        "sourceRevision": (root / "source-revision").read_text().strip(),
        "runtimeFiles": hashes,
        "bundledUIFiles": {n: digest(b) for n, b in static.items()},
        "artifacts": artifacts,
        "installations": observations,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"{len(runtime)} runtime and {len(static)} UI files match both artifacts; all installed claims match"
    )


if __name__ == "__main__":
    main()
