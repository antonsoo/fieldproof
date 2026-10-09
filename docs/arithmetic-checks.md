# Cross-field arithmetic

Available in the source checkout; not yet published. Fieldproof checks whether
the original extracted claims agree with each other. Grounding still checks
whether each claim has support in the document. Neither establishes that every
line was extracted or that the transaction is correct.

| Rule | Calculation | Required inputs |
| --- | --- | --- |
| `invoice.line_extension` | quantity times unit price = line amount | All three fields on that line |
| `invoice.items_subtotal` | sum of line amounts = subtotal | At least one item, all amounts, subtotal |
| `invoice.subtotal_tax_total` | subtotal + tax = total | All three fields |
| `invoice.due_date_order` | due date is on or after issue date | Both claimed dates parse |
| `receipt.items_subtotal` | sum of item amounts = subtotal | At least one item, all amounts, subtotal |
| `receipt.subtotal_tax_total` | subtotal + tax = total | All three fields |

Receipt items have no unit-price field, so they have no line-extension rule.
Contract and custom schemas currently have no built-in cross-field rules.
Date interpretation is unchanged; this audit uses the claimed dates.

`verify(data, document).to_dict()` and the CLI/API reports include a
`cross_field_checks` array. The inconsistent example's first entry contains:

```json
{
  "rule": "invoice.line_extension",
  "fields": ["line_items[0].quantity", "line_items[0].unit_price", "line_items[0].amount"],
  "status": "failed",
  "operands": {
    "line_items[0].quantity": "3.0",
    "line_items[0].unit_price": "19.95",
    "line_items[0].amount": "39.9"
  },
  "computed": "59.85",
  "observed": "39.9",
  "difference": "-19.95",
  "tolerance": "0.02"
}
```

The full entry also includes a readable `message`. Numeric operands and results
are strings so JSON consumers do not round them back to binary floats.
`difference` is always observed minus computed.

| Status | Meaning | Effect on field verification |
| --- | --- | --- |
| `passed` | Absolute difference is at most the tolerance | Does not upgrade unsupported or weakly grounded fields |
| `failed` | Absolute difference exceeds the tolerance, or date order fails | Participating fields need review; unsupported fields remain unsupported |
| `not_checked` | Missing/non-finite input, no item amounts, or unparseable dates | No arithmetic verdict; existing grounding verdict remains |

Absent inputs are `null` in `operands`. A missing tax is not a zero tax, and a
missing quantity is not one. Explicit zero, negative and fractional quantities
are calculated. For a skipped calculation, `computed`, `observed` and
`difference` are `null`; available operands are still recorded.

`cross_field_issues` remains the failed subset for existing consumers. Library
callers can use `fieldproof.verify.audit_cross_field(data)` without a PDF, or
`audit_invoice` / `audit_receipt` from `fieldproof.verify.cross_field` with a
custom finite, non-negative `tolerance`. The document verifier and server use
the existing absolute `0.02` tolerance, inclusive on either side.

## Numerical and business limits

Calculations convert validated numeric claims with `Decimal(str(value))` and
allocate enough precision for exact sums, products and differences. They do
not depend on Python's summation version or the caller's decimal context.
This prevents additional calculation error; it cannot recover digits already
lost while a provider, JSON parser or float-typed schema parsed the claim.

The tolerance is in the extracted amount's units. It is not a currency-aware
rounding policy. No per-line rounding, tax policy, price base quantity, unit
conversion, discount or allowance is inferred. A product is explicitly
**before discounts or adjustments**. Review can therefore be appropriate for
a legitimate adjusted invoice. Do not use `passed` as an accounting approval.

## Review and reproducibility

The audit belongs to the **original extraction**. Editing quantity from three
to two records a human correction; it does not silently rewrite source claims
or recompute the audit. Reviewed JSON/CSV retains `original_value`, `value_source`
and the original verification status. For a newly calculated audit, explicitly
validate and verify a new set of evidenced claims against the document; a
human edit alone does not become documentary evidence.

From a source checkout:

```bash
uv run --locked fieldproof extract examples/line-arithmetic.pdf --schema invoice \
  --provider fixture --fixture examples/fixtures/line-arithmetic.json --out result.json
uv run --locked fieldproof verify result.json examples/line-arithmetic.pdf
```

Both produce seven verified fields, three requiring review, and zero unsupported.
For interactive review, build the UI and run `fieldproof serve` as described in
the main README, then upload those two example files. The
[study](../studies/arithmetic-evidence/README.md) provides the independent oracle,
before/after replay and the static demo build commands.
