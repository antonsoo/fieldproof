import type { ExtractionResult } from "./types";
import { reviewValue } from "./review";

export interface ExportRow {
  field: string;
  value: unknown;
  original_value: unknown;
  value_source: "extraction" | "correction";
  verification_status: string;
  review_status: string;
  page: number | null;
}

/** Mirrors fieldproof.server.app._exported_rows. Human corrections retain
 * their source value and the original verification verdict. Both browser
 * modes download this snapshot of the decisions visible in the tab. */
export function computeExportRows(
  extraction: ExtractionResult,
  scope: "reviewed" | "all" = "all",
): ExportRow[] {
  const rows: ExportRow[] = [];
  for (const field of extraction.report.fields) {
    const review = extraction.review[field.path] ?? { status: "pending", edited_value: null };
    if (review.status === "rejected") continue;
    if (scope === "reviewed" && review.status !== "approved" && review.status !== "edited") continue;
    rows.push({
      field: field.path,
      value: reviewValue(field, review),
      original_value: field.value,
      value_source: review.status !== "pending" && review.edited_value !== null ? "correction" : "extraction",
      verification_status: field.status,
      review_status: review.status,
      page: field.page,
    });
  }
  return rows;
}

export function rowsToCsv(rows: ExportRow[]): string {
  const header = "field,value,original_value,value_source,verification_status,review_status,page";
  const escape = (v: unknown): string => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [r.field, r.value, r.original_value, r.value_source, r.verification_status, r.review_status, r.page]
      .map(escape)
      .join(","),
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
  // Revoking in the same task can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
