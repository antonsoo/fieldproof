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
  text_mode?: string;
  text_source?: string;
}

const baseColumns = [
  "field",
  "value",
  "original_value",
  "value_source",
  "verification_status",
  "review_status",
  "page",
] as const;
export function exportColumns(rows: ExportRow[]): (keyof ExportRow)[] {
  return [
    ...baseColumns,
    ...(["text_mode", "text_source"] as const).filter((key) => rows.some((r) => r[key] !== undefined)),
  ];
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
      ...((extraction.text_mode && extraction.text_mode !== "native") || extraction.report.ocr
        ? {
            ...(extraction.text_mode ? { text_mode: extraction.text_mode } : {}),
            text_source:
              field.page === null
                ? "Unlocated evidence"
                : extraction.report.ocr &&
                    (extraction.report.ocr.processed_pages === undefined ||
                      extraction.report.ocr.processed_pages.includes(field.page))
                  ? `OCR: ${extraction.report.ocr.engine} ${extraction.report.ocr.version}; ${extraction.report.ocr.language}; ${extraction.report.ocr.render_dpi} dpi`
                  : "Native PDF text",
          }
        : {}),
    });
  }
  return rows;
}

export function rowsToCsv(rows: ExportRow[]): string {
  const columns = exportColumns(rows);
  const header = columns.join(",");
  const escape = (v: unknown): string => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    columns
      .map((key) => r[key])
      .map(escape)
      .join(","),
  );
  return [header, ...lines].join("\r\n") + "\r\n";
}

export function downloadBlob(filename: string, content: BlobPart, mime: string): void {
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
