"""fieldproof CLI: extract, verify, serve."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import typer
import uvicorn

from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.model import Document
from fieldproof.extract.anthropic_provider import DEFAULT_MODEL, AnthropicExtractor
from fieldproof.extract.base import ExtractionError, ExtractionResult, read_extraction_json
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas import BUILTIN_SCHEMAS, resolve_schema
from fieldproof.verify.engine import verify as run_verify

app = typer.Typer(
    name="fieldproof",
    help="Document extraction that shows its work: every field linked to the words it came from.",
    no_args_is_help=True,
)


def _fail(message: str, code: int = 1) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _load_document(path: Path) -> Document:
    """The PDF, or a one-line error: a file that isn't a PDF is the caller's to
    fix, and pdfplumber's own exception for it is a page of traceback."""
    try:
        return load_pdf(path)
    except EmptyDocumentError as exc:
        _fail(str(exc))
    except Exception as exc:  # pdfplumber raises a variety of parse errors
        _fail(f"could not read {path} as a PDF: {exc}")


@app.command()
def extract(
    document: Path = typer.Argument(..., exists=True, readable=True, help="PDF to extract from"),
    schema: str = typer.Option(
        "invoice", "--schema", help=f"one of: {', '.join(sorted(BUILTIN_SCHEMAS))}"
    ),
    provider: str = typer.Option(
        "fixture", "--provider", help="anthropic (needs ANTHROPIC_API_KEY) or fixture"
    ),
    fixture: Path | None = typer.Option(
        None, "--fixture", help="stored JSON extraction to replay (required for --provider fixture)"
    ),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", help="Anthropic model id (only used with --provider anthropic)"
    ),
    out: Path = typer.Option(..., "--out", help="where to write the verified result JSON"),
) -> None:
    """Extract a schema from DOCUMENT, ground and verify it, write the result to --out."""
    schema_cls = BUILTIN_SCHEMAS.get(schema)
    if schema_cls is None:
        typer.echo(
            f"error: unknown schema {schema!r}; choose one of {sorted(BUILTIN_SCHEMAS)}", err=True
        )
        raise typer.Exit(code=2)

    if provider not in ("fixture", "anthropic"):
        _fail(f"unknown provider {provider!r}", code=2)
    if provider == "fixture" and fixture is None:
        _fail("--provider fixture requires --fixture <path>", code=2)

    doc = _load_document(document)
    try:
        if fixture is not None and provider == "fixture":
            result = FixtureExtractor(fixture_path=fixture).extract(doc, schema_cls)
        else:
            result = AnthropicExtractor(model=model).extract(doc, schema_cls)
    except (ExtractionError, OSError) as exc:
        _fail(str(exc))

    report = run_verify(result.data, doc)
    # Write the registry key ("invoice"), not result.schema_name (the class
    # name, "Invoice") - so `fieldproof verify result.json doc.pdf` on our
    # own output resolves the schema without needing resolve_schema's
    # class-name fallback below.
    payload = {**result.to_dict(), "schema": schema, "report": report.to_dict()}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    counts = report.counts
    typer.echo(
        f"wrote {out} - {counts['verified']} verified, {counts['needs_review']} needs review, "
        f"{counts['unsupported']} unsupported"
    )


@app.command()
def verify(
    result: Path = typer.Argument(..., exists=True, readable=True, help="extraction result JSON"),
    document: Path = typer.Argument(
        ..., exists=True, readable=True, help="the PDF it was extracted from"
    ),
    out: Path | None = typer.Option(
        None, "--out", help="write the re-verified result here (default: overwrite RESULT)"
    ),
) -> None:
    """Re-ground and re-verify an extraction JSON against DOCUMENT.

    Useful for extractions produced by other tools: RESULT just needs a
    `schema` name (one of fieldproof's built-ins) and a `data` object shaped
    like that schema, with `{value, evidence, page}` at every leaf.
    """
    try:
        raw = read_extraction_json(result.read_bytes(), result.name)
        schema_name = raw.get("schema", "")
        schema_cls = resolve_schema(schema_name)
        if schema_cls is None:
            _fail(
                f'{result.name}\'s "schema" is {schema_name!r}; must name one of '
                f"{sorted(BUILTIN_SCHEMAS)} (by registry key or class name) "
                "to re-verify from the CLI",
                code=2,
            )
        extraction = ExtractionResult.from_dict(raw, schema_cls, source=result.name)
    except ExtractionError as exc:
        _fail(str(exc), code=2)
    doc = _load_document(document)
    report = run_verify(extraction.data, doc)

    destination = out or result
    destination.write_text(
        json.dumps({**extraction.to_dict(), "report": report.to_dict()}, indent=2), encoding="utf-8"
    )

    counts = report.counts
    typer.echo(
        f"wrote {destination} - {counts['verified']} verified, "
        f"{counts['needs_review']} needs review, {counts['unsupported']} unsupported"
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(
        False, "--reload", help="auto-reload on source changes (development)"
    ),
) -> None:
    """Run the review server (API + UI) at http://HOST:PORT."""
    uvicorn.run("fieldproof.server.app:app", host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
