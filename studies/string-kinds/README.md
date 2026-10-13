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

Custom schemas remain a Python-library integration. The built-in CLI/server
schema selector is unchanged. No new UI controls, PyPI release or hosted
deployment accompany this work.

## Reproduce

Choose an unused output directory with the development environment installed:

```sh
uv run python studies/string-kinds/replay.py /tmp/string-kinds-after after --source .
```

Archive the baseline commit to another directory, then use `before --source
PATH` for its behavior. To replay an installed wheel, invoke the script with
that environment's Python and omit `--source`. The PDFs are committed; running
`fixtures.py` to regenerate them requires the development ReportLab dependency.
