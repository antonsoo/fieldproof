"""Portable review inputs, not a cached or trusted verification verdict.

Members are read into bounded buffers, never extracted to filesystem paths.
Restoring re-parses the PDF and verifies the original claims with this server.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
import zlib
from dataclasses import dataclass
from typing import Any

from fieldproof import __version__
from fieldproof.document.limits import DocumentLimitError
from fieldproof.extract.base import ExtractionError, ExtractionResult, validate_data
from fieldproof.schemas import BUILTIN_SCHEMAS, iter_evidenced_fields
from fieldproof.server.body_limit import MAX_ARCHIVE_BYTES, MAX_FIXTURE_BYTES, MAX_PDF_BYTES
from fieldproof.server.store import DocumentSession, ReviewState

MEMBER_LIMITS = {
    "manifest.json": 8 * 1024,
    "document.pdf": MAX_PDF_BYTES,
    "extraction.json": MAX_FIXTURE_BYTES,
    "review.json": 2 * 1024 * 1024,
}


def valid_correction(original: Any, value: Any) -> bool:
    if isinstance(original, bool):
        return isinstance(value, bool)
    if isinstance(original, (int, float)):
        try:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
        except OverflowError:
            return False
    return isinstance(value, str)


def _json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode(
            "utf-8"
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Archive JSON must contain finite numbers and valid Unicode") from exc


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("Archive JSON must contain finite numbers")


def _read_json(content: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite
        )
        # Also rejects overflowed float literals and escaped lone surrogates.
        _json_bytes(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"Invalid archive JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Archive JSON members must contain objects")
    return raw


def _text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"Archive {name} must be nonempty text of at most {maximum} characters")
    return value


def validate_review(raw: dict[str, Any], extraction: ExtractionResult) -> dict[str, ReviewState]:
    fields = {path: field.value for path, field in iter_evidenced_fields(extraction.data)}
    if len(fields) > 2_000:
        raise DocumentLimitError("Extraction exceeds the 2,000-field review limit")
    if raw.keys() != fields.keys():
        raise ValueError("Archive decisions must name every extracted field exactly once")
    result: dict[str, ReviewState] = {}
    correction_bytes = 0
    for path, original in fields.items():
        entry = raw[path]
        if not isinstance(entry, dict) or entry.keys() != {"status", "edited_value"}:
            raise ValueError(f"Invalid archived decision for {path}")
        status, edited = entry["status"], entry["edited_value"]
        if not isinstance(status, str) or status not in {
            "pending",
            "approved",
            "edited",
            "rejected",
        }:
            raise ValueError(f"Invalid archived review status for {path}")
        if (status == "pending" and edited is not None) or (status == "edited" and edited is None):
            raise ValueError(f"Archived correction conflicts with review status for {path}")
        if edited is not None:
            if not valid_correction(original, edited):
                raise ValueError(f"Archived correction must keep the field's scalar type: {path}")
            correction_bytes += len(json.dumps(edited, ensure_ascii=False).encode("utf-8"))
        result[path] = ReviewState(status=status, edited_value=edited)
    if correction_bytes > 1024 * 1024:
        raise DocumentLimitError("Archived corrections exceed the 1 MiB limit")
    return result


@dataclass
class ArchivedReview:
    filename: str
    pdf_bytes: bytes
    schema_name: str
    extraction: ExtractionResult
    review: dict[str, ReviewState]


def encode_archive(session: DocumentSession) -> bytes:
    """Caller holds review_lock and checks that extraction is not in progress."""
    if session.extraction is None or session.report is None or session.schema_name is None:
        raise ValueError("Run an extraction before saving a review archive")
    members = {
        "document.pdf": session.pdf_bytes,
        "extraction.json": _json_bytes(session.extraction.data.model_dump(mode="json")),
        "review.json": _json_bytes(
            {
                path: {"status": r.status, "edited_value": r.edited_value}
                for path, r in session.review.items()
            }
        ),
    }
    members["manifest.json"] = _json_bytes(
        {
            "format": "fieldproof-review",
            "version": 1,
            "producer_version": __version__,
            "filename": session.filename,
            "schema": session.schema_name,
            "provider": session.extraction.provider,
            "model": session.extraction.model,
            "sha256": {
                name: hashlib.sha256(content).hexdigest() for name, content in members.items()
            },
        }
    )
    for name, content in members.items():
        if len(content) > MEMBER_LIMITS[name]:
            raise DocumentLimitError(
                f"{name} exceeds the archive's {MEMBER_LIMITS[name] // 1024:,} KiB limit"
            )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in members.items():
            # Fixed metadata makes an unchanged review produce identical bytes.
            archive.writestr(zipfile.ZipInfo(name), content)
    return out.getvalue()


def decode_archive(content: bytes) -> ArchivedReview:
    if len(content) > MAX_ARCHIVE_BYTES:
        raise DocumentLimitError("Review archive exceeds the 30 MiB limit")
    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (
                len(entries) != len(MEMBER_LIMITS)
                or {entry.filename for entry in entries} != MEMBER_LIMITS.keys()
            ):
                raise ValueError(
                    "A review archive must contain exactly manifest.json, document.pdf, "
                    "extraction.json and review.json"
                )
            for entry in entries:
                if entry.orig_filename != entry.filename:
                    raise ValueError("Archive member names must not contain null characters")
                limit = MEMBER_LIMITS[entry.filename]
                if entry.file_size > limit:
                    raise DocumentLimitError(
                        f"Archived {entry.filename} exceeds its {limit // 1024:,} KiB limit"
                    )
                if entry.flag_bits & 1 or entry.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    raise ValueError(
                        "Archive members must be unencrypted, stored or deflated ZIP entries"
                    )
                with archive.open(entry) as stream:
                    data = stream.read(limit + 1)
                if len(data) > limit:
                    raise DocumentLimitError(f"Archived {entry.filename} is too large")
                members[entry.filename] = data
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise ValueError("Could not read review ZIP archive") from exc

    manifest = _read_json(members["manifest.json"])
    expected = {
        "format",
        "version",
        "producer_version",
        "filename",
        "schema",
        "provider",
        "model",
        "sha256",
    }
    if manifest.keys() != expected or manifest.get("format") != "fieldproof-review":
        raise ValueError("Not a supported Fieldproof review manifest")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("Unsupported review archive version")
    digests = manifest["sha256"]
    if not isinstance(digests, dict) or digests.keys() != MEMBER_LIMITS.keys() - {"manifest.json"}:
        raise ValueError("Archive manifest must identify all three content members")
    for name, digest in digests.items():
        if digest != hashlib.sha256(members[name]).hexdigest():
            raise ValueError(f"Archive checksum mismatch for {name}")
    filename = _text(manifest["filename"], "filename", 255)
    schema_name = _text(manifest["schema"], "schema", 64)
    provider = _text(manifest["provider"], "provider", 255)
    _text(manifest["producer_version"], "producer version", 64)
    model = manifest["model"]
    if model is not None and not isinstance(model, str):
        raise ValueError("Archived model must be text or null")
    if schema_name not in BUILTIN_SCHEMAS:
        raise ValueError(f"Unsupported archived schema: {schema_name}")
    raw_data = _read_json(members["extraction.json"])
    try:
        extracted_data = validate_data(
            raw_data,
            BUILTIN_SCHEMAS[schema_name],
            "Archived extraction",
        )
    except ExtractionError as exc:
        raise ValueError(str(exc)) from exc
    if json.dumps(raw_data, sort_keys=True) != json.dumps(
        extracted_data.model_dump(mode="json"), sort_keys=True
    ):
        raise ValueError(
            "Archived claims do not exactly match this server's schema; no fields were restored"
        )
    extraction = ExtractionResult(
        schema_name=BUILTIN_SCHEMAS[schema_name].__name__,
        data=extracted_data,
        provider=provider,
        model=model,
    )
    review = validate_review(_read_json(members["review.json"]), extraction)
    return ArchivedReview(filename, members["document.pdf"], schema_name, extraction, review)
