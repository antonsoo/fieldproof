# Resume a review after a restart

Available in the source checkout; not yet released. The local review server
keeps sessions in memory. Value exports let another tool consume results, but
do not retain enough information to reopen the document review.

1. Finish or cancel any open correction. Choose **Save archive** in the top bar.
2. Keep the downloaded `fieldproof-review.zip`. It contains every saved
   decision, regardless of the value-export scope, plus the full source PDF.
3. After restarting `fieldproof serve`, choose **Open review archive** on the
   upload screen. From another document, choose **New document** first; its
   existing session remains available under **Sessions**.
4. Continue reviewing and save another archive when you want a new checkpoint.

No model is called during restore. The built-in invoice, receipt and contract
schemas are supported, with the same text-layer PDF limits as ordinary uploads.
The static demo has no archive controls; this workflow needs the local server.

```text
PDF + original claims + all saved decisions
                  |
             Save archive
                  |
          fieldproof-review.zip
                  |
           server can restart
                  |
          Open review archive
                  |
    validate inputs + recompute checks
                  |
       new session + saved decisions
```

The archive does not store rendered pages or automated verdicts. Restore
regenerates both using the current verifier. Corrections never replace the
original claims during this calculation, and a saved approval does not
establish that a new automated check passed. The UI marks reopened documents
as coming from an archive. Provider/model labels describe the original
extraction; opening it does not call that provider.

An archive is an explicit snapshot of the server's saved session. Unsaved
correction drafts, filters, zoom and scroll position are not stored. Changes
in another browser tab can affect the server snapshot; JSON/CSV/XLSX value
exports instead snapshot the decisions displayed in their exporting tab.
The download-start message does not confirm that the browser finished saving
the file. There is no automatic backup after later edits.

## API

| Request | Result |
| --- | --- |
| `GET /api/documents/{id}/archive` | ZIP snapshot; requires an extraction and no extraction currently running |
| `POST /api/archives` with multipart `file` | `{document, extraction}` for a new, fully restored session |

The returned `document` is a normal document summary with
`restored_from_archive: true`. `extraction` has the same shape as the report
route, with newly computed checks and the restored review overlay. Existing
sessions are not replaced or evicted. Reopening the same archive twice creates
two independent sessions. A cancelled request or lost connection can race with
completion; check **Sessions** before retrying to avoid duplicate copies.

## Version 1 format

A normal ZIP with exactly four files. Saving uses stored entries, so a saved
archive can be inspected with ordinary ZIP tools. Stored and deflated entries
are accepted when opening; encryption and other compression methods are not.

| Member | Contents | Uncompressed limit |
| --- | --- | --- |
| `manifest.json` | Format/version, original filename, schema, provider/model, producer package version, SHA-256 of the other three members | 8 KiB |
| `document.pdf` | Original uploaded PDF bytes | 25 MiB |
| `extraction.json` | Original validated schema data, including values, quotes and claimed pages | 2 MiB |
| `review.json` | Every field path mapped to `{status, edited_value}` | 2 MiB |

`format` is `fieldproof-review` and `version` is the integer `1`.
`producer_version` is informational: unreleased source revisions may share a
package version. It is not a Git revision or a verifier compatibility promise.
Member hashes catch corruption or accidentally mixed files. They are unsigned
and editable, and do **not** authenticate the document, extraction or reviewer.
The archive is unencrypted and contains the whole PDF, including content that
was never extracted. Its decisions have no author identity or signature.

The ZIP upload is limited to 30 MiB before decoding. Duplicate/missing/extra
members, mismatched hashes, duplicate JSON keys, invalid Unicode, nonfinite
numbers and unsupported versions are rejected. Members are read into bounded
buffers; no member paths are extracted to disk. The standard-library ZIP reader
also checks CRCs. See [Python's ZIP documentation](https://docs.python.org/3/library/zipfile.html).

Schema data must round-trip exactly through the current built-in schema;
unrecognized fields, coercions or missing defaults are refused rather than
silently dropped. Every original field needs exactly one decision, with a
valid status and a correction of its original scalar type. Pending decisions
cannot have corrections; approved and rejected decisions can retain one.
The existing 2,000-field and 1 MiB total correction limits still apply.

Serialization has its own size limits: a session whose pretty-printed claims
exceed 2 MiB cannot be archived even if its original compact fixture fit the
upload limit. The server returns an error and retains the session. A future
schema change may also require a migration tool before an older archive can be
opened. The PDF and JSON remain independently readable with ordinary tools.

## Evidence

The [restart study](../studies/review-archives/README.md) uses four synthetic
repository PDF/fixture pairs. It stops the server process, starts an empty
server without an API key, restores each review, renders the pages and compares
its report, decisions and exported values. It is a recovery check, not an
extraction-accuracy evaluation on real documents.
