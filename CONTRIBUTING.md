# Contributing

fieldproof is a small, focused project. Issues and pull requests are welcome.

## Development setup

```bash
uv sync --extra dev --extra ocr
uv run pytest
uv run ruff check src tests
uv run mypy src

cd web && npm ci && npm run typecheck && npm run lint && npm run build
```

## Guidelines

- Keep the core (`document`, `schemas`, `extract`, `ground`, `verify`) free
  of I/O and UI concerns - it should stay usable as a library.
- New verification logic needs a test with an independent expected value
  (a hand-computed number, a known date, a fixed fuzzy-match score) rather
  than a snapshot of whatever the code currently produces.
- Run `uv run python scripts/generate_samples.py` and
  `uv run python scripts/build_demo_data.py` after changing the sample
  documents or their fixtures, and check `uv run pytest tests/test_e2e.py`
  still passes - it pins down exactly which planted error each sample is
  expected to surface.
- Match the existing code style; `ruff format` and `prettier` are the
  source of truth for formatting, not personal preference.

## Reporting issues

Open a GitHub issue with a minimal reproduction - for a grounding or
verification bug, the PDF (or a page from it) and the extraction JSON that
triggered it are the most useful things to include.

## Community and private reports

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Anton Soloviev
maintains this project and handles conduct reports at
[anton@praviel.com](mailto:anton@praviel.com).

Use the bug or improvement forms for public issues. For a suspected security
vulnerability or a conduct concern, email the maintainer privately with the
repository name and relevant details. Do not post credentials, personal data,
private logs, or confidential documents in a public issue.
