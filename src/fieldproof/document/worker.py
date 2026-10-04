"""Disposable PDF process used by the local server, never a model provider."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.render import render_page_png


def _set_process_limits() -> None:
    try:
        import resource
    except ImportError:  # Windows still gets the parent's wall-clock timeout.
        return
    for kind, target in (
        (resource.RLIMIT_AS, 768 * 1024 * 1024),
        (resource.RLIMIT_CPU, 20),
        (resource.RLIMIT_FSIZE, 64 * 1024 * 1024),
    ):
        inherited = [value for value in resource.getrlimit(kind) if value != resource.RLIM_INFINITY]
        maximum = min([target, *inherited])
        resource.setrlimit(kind, (maximum, maximum))


def main() -> int:
    _set_process_limits()
    action, source, destination, argument = sys.argv[1:]
    limits = DocumentLimits()
    try:
        if action == "load":
            document = load_pdf(Path(source), label=argument, limits=limits)
            Path(destination).write_text(json.dumps(asdict(document)), encoding="utf-8")
        elif action == "render":
            Path(destination).write_bytes(
                render_page_png(Path(source), int(argument), max_pixels=limits.max_pixels)
            )
        else:
            raise ValueError("unknown PDF operation")
    except EmptyDocumentError:
        print(
            "PDF has no extractable text; this review server needs a PDF text layer",
            file=sys.stderr,
        )
        return 2
    except (DocumentLimitError, MemoryError) as exc:
        print(str(exc) or "PDF exceeded the worker memory budget", file=sys.stderr)
        return 3
    except Exception:
        print(
            "could not read or render PDF; check that it is valid and not encrypted",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
