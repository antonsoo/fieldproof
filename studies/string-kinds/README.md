# A candidate's name is not a calendar date

At baseline `6ec047d33cd69fb7a02154e90bc3049f1e072f16`, an exact PDF quote
supporting `candidate_name = "Example Works"` became `needs_review` because
the value was not a calendar date. The same value and quote named `name`
verified. The engine searched for the substring `date` anywhere in the full
field path. It also disabled requested text tolerance and added date-conflict
explanations based on that substring.

That affected `updated_by`, `validate_status`, enclosing date-related objects
and literal mapping keys. Conversely, a field named `effective` had no way to
declare date intent in its wrapper: a literal invalid date could pass ordinary
text checking, while an ISO claim supported by a written date could fail it.

## Changes and boundaries

`EvidencedDate` and `EvidencedText` are explicit string wrappers for custom
schemas. They inherit the existing `{value, evidence, page}` shape; the
declared schema determines their kind, not a model-supplied JSON switch.
Invalid date strings remain intact, then receive a verification verdict.
Reports retain `declared_kind` even when evidence is missing or unresolved.
It is separate from tolerance notes and does not disable valid row anchors.

These are ordinary subclasses of the parameterized Pydantic model; see
[Pydantic's generic-model documentation](https://pydantic.dev/docs/validation/latest/concepts/models/#generic-models).
The fixture/roundtrip replay and real SDK streaming test verify that the
declared types survive parsing. The SDK transport is synthetic; this does not
test acceptance by a live provider or estimate model accuracy.

For plain `Evidenced[str]`, the fallback uses the final named member, decoding
JSON-quoted keys and retaining collection names across numeric indices. It
recognizes complete `date`, `dates`, `birthdate` and `birthdates` words,
splitting snake_case, camelCase, punctuation and numeric suffixes. Ancestors
cannot impose a date kind on their descendants. This is a documented naming
convention, not semantic inference: use `EvidencedDate` for an unseparated name
such as `issuedate`, or `EvidencedText` for a literal label containing `date`.
Likewise, declare `dict[str, EvidencedDate]` for date-valued mappings; their
arbitrary keys do not inherit a date kind from the mapping's name. Custom
schemas relying on whole-path substring matches must migrate those fields
explicitly. The built-in schema declarations remain unchanged.

One decision now governs value checking, text tolerance and conflict warnings.
Real dates still require one calendar-valid ISO claim, supported evidence and
an unambiguous reading. Document-wide defaults cannot override conflicting
observed date conventions. Date fields never receive letter-edit tolerance.

## Controlled replay

[fixtures.py](fixtures.py) generates two explicitly labelled synthetic PDFs
and [23 cases](cases.json). [replay.py](replay.py) uses the real fixture
extractor, PDF loader and verification API, then serializes and revalidates
each model and verifies it again. It asserts each expected verdict, preserves
input values, and records schemas, report reasons, notes, source rectangles,
hashes and runtime versions in [before.json](before.json) and [after.json](after.json).

| Input or declaration | Baseline | Current source |
| --- | --- | --- |
| Exact text in `candidate_name`, `updated_by`, `validate_status` | Invalid-date warning | Verified as text |
| Ordinary name under a date-related ancestor | Invalid-date warning | Verified as text |
| Requested one-letter text tolerance on `candidate_name` | Disabled by accidental date match | Accepted with the edit recorded |
| Text mismatch in a document with mixed date conventions | Unrelated date-conflict explanation | Text mismatch without that explanation |
| Valid written date under conventional `issue_date` | Verified | Identical report |
| Invalid conventional date, including indexed `dates` | Needs review | Identical report |
| `effective: EvidencedDate` with an invalid date | Generic text accepts it | Needs review |
| `effective: EvidencedDate` with ISO value and written evidence | Generic text rejects it | Verified as date |
| `date_label: EvidencedText` containing `YYYY-MM-DD` | Invalid-date warning | Verified as literal text |
| Explicit text row anchor | Name and repeated amount need review | Both verified, with a locality note for the amount |

The explicit-kind cases deliberately change the schema annotation: their
baseline uses `Evidenced[str]`, while the current run opts into the new wrapper.
Their input JSON bytes remain identical. These rows demonstrate the new API,
not a claim that an unavailable baseline type already carried that intent.

[builtin_replay.py](builtin_replay.py) separately invokes the actual CLI for
invoice, receipt and contract fixtures. All three reports match their baseline
bytes; [builtin-controls.json](builtin-controls.json) retains hashes and counts.
All three built-in JSON Schema hashes and five unchanged study-control reports
match too.

Custom schemas remain a Python-library integration. The built-in CLI/server
schema selector is unchanged. No new UI controls, PyPI release or hosted
deployment accompany this work.

## Clean archive and installed artifacts

[verification.json](verification.json) records a fresh 707-file archive of
implementation `bd1aa39eb90141ad250bc73f65fe79c9b80c3f60`, locked installation,
lint/type/format checks, both web builds and packaging. All archived tracked
files remain unchanged after checking. The wheel, source distribution and
both fresh installations match all 37 Python files and 23 bundled UI assets.
Those UI assets are also byte-identical to the preceding container-claims build.

| Environment | Pydantic | Python suite | PDF replay |
| --- | --- | --- | --- |
| Locked source, Python 3.12.12 | 2.13.5 | 612 passed, one OCR skip | 23 expected outcomes |
| Installed wheel, Python 3.11.13, lowest direct dependencies | 2.12.0 | 612 passed, one OCR skip | [23 expected outcomes](installed-minimum.json) |
| Installed wheel, Python 3.14.7, current dependencies | 2.14.1 | 612 passed, one OCR skip | [23 expected outcomes](installed-current.json) |

The real-OCR case is skipped because Tesseract is unavailable. All five control
reports and 23 input hashes match the baseline in every environment. Actual
invoice, receipt and contract CLI reports are byte-identical before/after in
each environment and across them. The three built-in JSON Schemas also match
before/after under each tested Pydantic version.

The Python suites exercise actual Anthropic SDK streaming and structured-schema
requests on versions 0.77.0, 1.11.0 and 1.13.0. Their HTTP transports supply
synthetic replies; invalid date strings remain available for verification, and
JSON cannot override the schema's kind. This is parser/transport evidence,
not a live service or model evaluation.

The clean web run passes 62 unit checks and 86 production-browser checks.
The previous 15-case import-boundary replay retains its outcomes and valid
report hashes; all ten previous container records remain identical. No new
screenshots are needed for this library change: the UI source and all 23 built
assets are unchanged, and the existing live/demo browser workflows pass.

Local artifacts retain version 0.2.7 and are distinct from the previously
published package. The final evidence/documentation commit changes no tested
runtime files. Migration notes describe the narrower naming convention and
explicit date declarations for custom schemas.

## Reproduce

Choose an unused output directory with the development environment installed:

```sh
uv run python studies/string-kinds/replay.py /tmp/string-kinds-after after --source .
```

Archive the baseline commit to another directory, then use `before --source
PATH` for its behavior. To replay an installed wheel, invoke the script with
that environment's Python and omit `--source`. The PDFs are committed; running
`fixtures.py` to regenerate them requires the development ReportLab dependency.
