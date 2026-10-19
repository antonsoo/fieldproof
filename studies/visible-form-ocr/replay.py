"""Exercise actual extract/verify commands on a native-text PDF with a saved form value."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("python", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("phase", choices=["before", "after"])
    args = parser.parse_args()
    # Keep the virtual environment entrypoint; resolving its symlink bypasses
    # pyvenv.cfg and can select the base interpreter's unrelated packages.
    python = str(args.python.absolute())
    entrypoint = str(args.python.absolute().with_name("fieldproof"))
    args.output.mkdir(parents=True, exist_ok=True)
    identity = subprocess.check_output(
        [
            python,
            "-I",
            "-c",
            "import hashlib,importlib.metadata as m,json,platform; "
            "from pathlib import Path; import fieldproof; p=Path(fieldproof.__file__).parent; "
            "print(json.dumps({'python':platform.python_version(),'versions':"
            "{k:m.version(k) for k in ['fieldproof','pypdfium2','pytesseract','Pillow']},"
            "'sources':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() "
            "for f in p.rglob('*.py')}}))",
        ],
        text=True,
    )
    source = ROOT / "studies/form-appearances/fixtures/covered-native-total.pdf"
    records = []
    for command in ("extract", "verify"):
        for mode in ("native", "missing", "all"):
            for value in (100, 900):
                folder = args.output / f"{command}-{mode}-{value}"
                folder.mkdir()
                claim = (
                    HERE / "visible-claim.json"
                    if value == 100
                    else HERE.parent / "form-appearances/claim.json"
                )
                shutil.copyfile(source, folder / "form.pdf")
                shutil.copyfile(claim, folder / "claim.json")
                original = {p.name: sha(p) for p in folder.iterdir()}
                arguments = (
                    ["extract", "form.pdf", "--fixture", "claim.json"]
                    if command == "extract"
                    else ["verify", "claim.json", "form.pdf"]
                )
                if mode != "native":
                    arguments.append("--ocr-all-pages" if mode == "all" else "--ocr-missing-pages")
                arguments.extend(["--out", "result.json"])
                process = subprocess.run(
                    [python, "-I", entrypoint, *arguments],
                    cwd=folder,
                    env=dict(os.environ, OMP_THREAD_LIMIT="1"),
                    text=True,
                    capture_output=True,
                )
                (folder / "stdout.txt").write_text(process.stdout)
                (folder / "stderr.txt").write_text(process.stderr)
                assert all(sha(folder / name) == value for name, value in original.items())
                unsupported = args.phase == "before" and mode == "all"
                assert process.returncode == (2 if unsupported else 0), process.stderr
                record = {
                    "command": command,
                    "mode": mode,
                    "claim": value,
                    "exit_code": process.returncode,
                    "inputs_unchanged": True,
                }
                if unsupported:
                    assert not (folder / "result.json").exists()
                    assert "--ocr-all-pages" in process.stderr
                else:
                    result = json.loads((folder / "result.json").read_text())
                    total = next(f for f in result["report"]["fields"] if f["path"] == "total")
                    assert total["value"] == value
                    assert total["status"] == (
                        "verified" if mode == "all" and value == 100 else "needs_review"
                    )
                    assert total["matched_text"] == (
                        "Authorized total: $100.00"
                        if mode == "all"
                        else "Authorized total: $900.00"
                    )
                    provenance = result["report"].get("ocr")
                    if mode == "all":
                        assert provenance["processed_pages"] == [1]
                        assert "replaces native text" in provenance["note"]
                    else:
                        assert provenance is None
                    record.update(
                        {
                            "total": total,
                            "ocr": provenance,
                            "result_sha256": sha(folder / "result.json"),
                        }
                    )
                records.append(record)
                print(json.dumps({"completed": len(records), "case": folder.name}), flush=True)
    receipt = {
        "phase": args.phase,
        "script_sha256": sha(Path(__file__)),
        "identity": json.loads(identity),
        "source_sha256": sha(source),
        "runs": records,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
