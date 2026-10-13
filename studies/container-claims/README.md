# Custom containers must not hide unsupported claims

At baseline `9814cf203a010c886c6e66ac30da8f045a10f2aa`, a valid custom Pydantic
model could contain both a supported vendor name and an unsupported bank-account
claim, yet return no verification fields and zero in every count. The generic
walker visited models and lists but omitted dictionaries and tuples.

An independent path collision also dropped a claim: a literal model field named
`a.b` and a nested `a.b` had the same report path. Converting the walk to a
dictionary kept only the later claim. In this replay, that erased the unsupported
field and left one verified result.

## Controlled PDF replay

[synthetic-containers.pdf](synthetic-containers.pdf) is explicitly labelled
synthetic. It contains a vendor and two different rows with the same amount.
[fixture.py](fixture.py) regenerates it with the development ReportLab dependency.
[replay.py](replay.py) builds ten custom-model cases, loads the PDF through the
real document reader and calls the public verification API. It checks the
expected verdicts and saves schema, input, paths, report, source locations and
runtime versions. No model or external service is called.

| Case | Baseline | Current source |
| --- | --- | --- |
| Ordinary model and list controls | One verified, one unsupported | Identical reports |
| String-keyed mapping, tuple, nested combination | No report fields | One verified, one unsupported |
| Literal `a.b` plus nested `a.b` | Unsupported claim overwritten | Two distinct report paths and both verdicts |
| Mapping keys resembling row paths | No report fields | Name verified; repeated amount still needs review |
| Real list of row models inside a mapping | No report fields | Both claims verified, with an explicit locality note |
| Non-string mapping keys | No report fields | Explicit error |

[before.json](before.json) and [after.json](after.json) retain the full records.
The ordinary model/list controls retain the same reports, and the repeated
amount controls keep their ambiguity. This measures traversal and grounding
on controlled inputs; it does not estimate extraction accuracy on real forms.

## Path identity and row context

Model identifiers retain their existing dotted paths and list/tuple positions
use numeric brackets. Mapping keys always use JSON-quoted brackets. A model
field whose name is not an identifier also uses quoted brackets:

| Structure | Path |
| --- | --- |
| Model field `vendor` | `vendor` |
| Nested model `a`, field `b` | `a.b` |
| Literal model field `a.b` | `["a.b"]` |
| Mapping key `a.b` under `claims` | `claims["a.b"]` |
| List/tuple position zero | `claims[0]` |
| Mapping key `0` | `claims["0"]` |

Quotes, backslashes, newlines and non-ASCII keys use JSON escaping. The walker
retains insertion/sequence order. It supports models, lists, tuples and
string-keyed mappings with `Evidenced` leaves; non-string mapping keys fail
explicitly. Unordered collections are not a supported schema shape.

Row locality still needs an actual positional model member. The verifier masks
quoted members before finding row indices, so a key literally containing
`items[0].amount` cannot lend authority to another claim. Real row-model lists
inside mappings retain their locality hints. Explicit `RowEvidenceRule`
configuration remains limited to dotted model paths pointing to lists of models;
this change does not add rules for arbitrary mappings or infer their business
meaning. A matching quote/location does not prove a field's semantic role.

Custom schemas are a Python-library integration. The CLI and server schema
selector still offer invoice, receipt and contract templates. This work does
not add a custom-schema UI, change those templates, or make a package release.

## Clean archive and installed packages

[verification.json](verification.json) records a fresh 693-file archive of
implementation `b3e0f26ad28c92dd5274f778114ed4f751479616`. All archived tracked
files remain unchanged after the checks. The wheel and source distribution
contain the same 37 Python files and 23 UI assets as the build, and both fresh
wheel installations match those files. Dependency compatibility checks pass.

| Environment | Pydantic | Full Python suite | Container replay |
| --- | --- | --- | --- |
| Locked source, Python 3.12.12 | 2.13.5 | 584 passed, one OCR skip | Ten expected outcomes |
| Installed wheel, Python 3.11.13, lowest direct dependencies | 2.12.0 | 584 passed, one OCR skip | [Ten expected outcomes](installed-minimum.json) |
| Installed wheel, Python 3.14.7, current dependencies | 2.14.1 | 584 passed, one OCR skip | [Ten expected outcomes](installed-current.json) |

Tesseract is unavailable, so the real-OCR case is skipped. Lint, Python and web
types, web formatting, 62 web unit checks, both web builds and 86 production
browser checks pass. The 23 bundled UI files are byte-identical to the prior
claim-integrity build; this change adds no UI controls. The previous 15-case
CLI/API/SDK import-boundary replay retains its outcomes and valid report hashes.

These local wheel/source archives still carry version 0.2.7 and differ from the
previously published package. The final evidence commit changes no tested
runtime files. No PyPI release or hosted deployment accompanies this repair.

## Reproduce

With the source development environment installed:

```sh
uv run python studies/container-claims/replay.py /tmp/containers-after.json --source .
```

Archive the baseline commit to a separate directory, then use `--source PATH
--expect before` for its behavior. To check an installed wheel, invoke this
script with that installation's Python and omit `--source`. The committed PDF
does not require ReportLab to replay. Use `fixture.py` only to regenerate it.
