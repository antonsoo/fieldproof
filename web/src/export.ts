import type { ExtractionResult } from "./types";

export interface ExportRow {
  field: string;
  value: unknown;
  verification_status: string;
  review_status: string;
  page: number | null;
}

/** Mirrors fieldproof.server.app._exported_rows: an edited value overrides
 * the extracted one, a rejected field is dropped, everything else passes
 * through with both its verification and review status attached. Shared by
 * the demo (no server to ask) and as a fallback if a live export request
 * fails. */
export function computeExportRows(extraction: ExtractionResult): ExportRow[] {
  const rows: ExportRow[] = [];
  for (const field of extraction.report.fields) {
    const review = extraction.review[field.path] ?? { status: "pending", edited_value: null };
    if (review.status === "rejected") continue;
    rows.push({
      field: field.path,
      value: review.status === "edited" ? review.edited_value : field.value,
      verification_status: field.status,
      review_status: review.status,
      page: field.page,
    });
  }
  return rows;
}

export function rowsToCsv(rows: ExportRow[]): string {
  const header = "field,value,verification_status,review_status,page";
  const escape = (v: unknown): string => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [r.field, r.value, r.verification_status, r.review_status, r.page].map(escape).join(","),
  );
  return [header, ...lines].join("\r\n") + "\r\n";
}

export function downloadBlob(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
