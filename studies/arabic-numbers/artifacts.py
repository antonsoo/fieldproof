"""Check the installed parser and locally served UI against the built distributions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import fieldproof
from fieldproof.ground import values


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--sdist", required=True, type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    assert Path(fieldproof.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    number_parser = Path(values.__file__).read_bytes()
    files = []
    sources = []
    with zipfile.ZipFile(args.wheel) as wheel, tarfile.open(args.sdist) as sdist:
        assert wheel.read("fieldproof/ground/values.py") == number_parser
        source = next(
            m for m in sdist.getmembers() if m.name.endswith("/src/fieldproof/ground/values.py")
        )
        source_file = sdist.extractfile(source)
        assert source_file is not None and source_file.read() == number_parser
        package = Path(fieldproof.__file__).resolve().parent
        source_members = {
            m.name.split("/src/", 1)[1]: m
            for m in sdist.getmembers()
            if "/src/" in m.name and m.name.endswith(".py")
        }
        wheel_sources = {
            name
            for name in wheel.namelist()
            if name.startswith("fieldproof/") and name.endswith(".py")
        }
        installed_sources = {
            "fieldproof/" + p.relative_to(package).as_posix() for p in package.rglob("*.py")
        }
        assert wheel_sources == installed_sources == set(source_members)
        for name in sorted(wheel_sources):
            content = wheel.read(name)
            assert (package / name.removeprefix("fieldproof/")).read_bytes() == content, name
            stream = sdist.extractfile(source_members[name])
            assert stream is not None and stream.read() == content, name
            sources.append({"file": name, "sha256": digest(content)})
        prefix = "fieldproof/server/static/"
        for name in sorted(wheel.namelist()):
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = name.removeprefix(prefix)
            original = wheel.read(name)
            url = args.url.rstrip("/") + "/" + ("" if relative == "index.html" else relative)
            with urllib.request.urlopen(url, timeout=10) as response:
                served = response.read()
                assert response.status == 200
            assert original == served, relative
            files.append({"file": relative, "bytes": len(original), "sha256": digest(original)})
    assert len(files) > 1
    output = {
        "scope": "Locally served installed wheel; no public hosting or registry release claim.",
        "wheel": {
            "file": args.wheel.name,
            "bytes": args.wheel.stat().st_size,
            "sha256": digest(args.wheel.read_bytes()),
        },
        "sdist": {
            "file": args.sdist.name,
            "bytes": args.sdist.stat().st_size,
            "sha256": digest(args.sdist.read_bytes()),
        },
        "parser_sha256": digest(number_parser),
        "installed_wheel_sdist_parser_identical": True,
        "installed_wheel_sdist_all_python_identical": True,
        "python_sources": sources,
        "served_files": files,
    }
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    print(
        f"{len(sources)} Python modules identical in wheel, sdist and installation; "
        f"{len(files)} served UI files identical."
    )


if __name__ == "__main__":
    main()
