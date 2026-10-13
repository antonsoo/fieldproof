"""CLI report destinations and atomic replacement of private extraction data."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def check_report_destination(path: Path, protected: tuple[Path, ...]) -> None:
    """Refuse source aliases before PDF/provider work and again before writing."""
    if path.is_symlink():
        raise OSError("report output cannot be a symbolic link")
    resolved = path.resolve()
    for source in protected:
        if resolved == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise OSError(
                "report output must be distinct from source documents and extraction fixtures"
            )
    if not path.parent.is_dir():
        raise OSError("report output parent directory does not exist")
    if path.exists() and not path.is_file():
        raise OSError("report output must be a regular file")


def write_report(path: Path, text: str, protected: tuple[Path, ...]) -> None:
    """Replace only after a complete flushed write; failures preserve the old report.

    The sibling temporary file is private (0600 on POSIX). This is not a lock
    against concurrent writers or a whole-machine power-loss guarantee.
    """
    check_report_destination(path, protected)
    temporary: Path | None = None
    try:
        # A valid destination may already use the filesystem's full name length.
        # Keep the temporary prefix independent of that name.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".fieldproof-report-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
