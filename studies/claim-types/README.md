# A located quote cannot verify an arbitrary value type

This is a labelled synthetic control, not an extraction-accuracy benchmark.
At baseline `27ae6c7e2e473e8d5b503a66a42d53465820866f`, a valid custom Pydantic
model can hold `Evidenced[dict[str, str]]` with an unsupported bank account and
quote `Example Works`. The real PDF loader finds the quote; the verifier then
reports the object as verified without checking its contents. Null, arrays,
Python dates, Decimal values, bytes, model objects and plain enums take the
same successful fallback. Generic type annotations do not prevent these
models from being instantiated.

The repair validates every present wrapper before grounding. Unsupported
actual types raise a `ValueError` naming the full field path. Explicit
`EvidencedDate` and `EvidencedText` wrappers must hold strings, even after a
caller mutates the model. No claim is converted, no partial report is returned,
and no unsupported object can supply a row-location hint. The dispatcher's
successful fallback is removed as well.

| Case | Baseline | Repaired verifier |
| --- | --- | --- |
| Object, null or other unsupported value with an unrelated real quote | Verified | Field-specific error |
| Unsupported object without a located quote | Unsupported or needs review, hiding the type problem | Same type error regardless of quote |
| Object quoted as `Alpha` beside a repeated `10.00` amount | Both object and amount verified; object establishes a row hint | Error before grounding either field |
| Explicit date/text wrapper mutated to integer `13`, quoting `13` | Verified as a number | String-kind error |
| Supported scalar, mismatch and missing-evidence controls | Existing verdicts and locations | Identical reports |
| Optional wrapper set to `None` | No claim field | Unchanged |

## Retained evidence

- `fixture.py` generates the labelled `claims.pdf` using ReportLab's invariant
  PDF output. Every name, number and claim is synthetic.
- `replay.py` exercises 26 fixtures through the actual `FixtureExtractor`, PDF
  loader and public verifier, plus two direct-Python mutation cases. Both
  versions receive the same schemas and fixture bytes. The fixture extractor
  accepts the custom types in both versions; this repair is at verification.
- `before.json` and `after.json` retain input and schema hashes, full reports
  or exact exceptions, dependency versions and the PDF hash.
- Eighteen cases now fail explicitly; fifteen of them were previously verified.
  Three already had quote problems, but those obscured an unsupported value type.
  Ten control reports are unchanged. All supplied model values remain unchanged.
- Baseline reports can contain Python objects that standard `json.dumps`
  cannot serialize. The replay uses Pydantic's serializer only to retain those
  reports as evidence; it does not convert the verifier's input or fix its output.
  Date/Decimal/bytes/enum representations are interpreted with the schema in
  `replay.py`. The two mutation cases are explicitly marked as direct Python
  assignments, not JSON imports.

## Schema migration

Each present wrapper needs a supported actual value: `str`, `int`, `float`
or `bool`. Normal scalar subclasses such as `StrEnum` and `IntEnum` still use
their scalar checks. A broad or nullable annotation can still carry a supported
non-null scalar; it does not authorize verifying objects or null.

Use `dict[str, Evidenced[str]]` or a model of individual wrappers for a set of
claims. Each leaf then has its own evidence. Use `Evidenced[str] | None` for an
absent optional claim. A present `Evidenced[str | None]` holding null is an error.
Use ISO strings in `EvidencedDate` for calendar dates. Arbitrary objects,
Python `date`, Decimal and bytes have no built-in verification rules and are
not silently normalized into supported types.

The error precedes grounding even if another field could verify successfully.
A caller must correct the schema or value rather than accept a partial report
that conceals an uncheckable claim. This is an intentional compatibility change
for custom schemas that previously depended on the successful fallback.
Existing numeric, text, Boolean and calendar checks remain responsible for
whether a supported value agrees with its evidence.

## Reproduce

From a source checkout with development dependencies installed:

```sh
python studies/claim-types/fixture.py
python studies/claim-types/replay.py /tmp/claim-types-after after --source .
git worktree add --detach /tmp/fieldproof-claim-types-before 27ae6c7e2e473e8d5b503a66a42d53465820866f
python studies/claim-types/replay.py /tmp/claim-types-before before --source /tmp/fieldproof-claim-types-before
pytest -q tests/test_claim_value_types.py
```

Output directories must not already exist. For a freshly installed wheel,
run its Python interpreter on `replay.py` without `--source`. The checked-in
PDF's SHA-256 is in each record. No live model or provider is called. These
are custom Python schemas; the CLI/server still expose their three built-in
schema selectors. No new web UI or model-side guarantee is claimed.
