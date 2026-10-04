import type { DocumentSummary, ExtractionResult, FieldStatus } from "./types";
import { validatedOverlay } from "./review";

function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function validateDocument(value: unknown): DocumentSummary {
  if (
    !object(value) ||
    typeof value.id !== "string" ||
    !value.id ||
    typeof value.filename !== "string" ||
    !Number.isSafeInteger(value.page_count) ||
    (value.page_count as number) < 1 ||
    !Array.isArray(value.pages) ||
    value.pages.length !== value.page_count
  ) {
    throw new Error("Invalid document summary.");
  }
  const seen = new Set<number>();
  for (const page of value.pages) {
    if (
      !object(page) ||
      !Number.isSafeInteger(page.number) ||
      (page.number as number) < 1 ||
      (page.number as number) > (value.page_count as number) ||
      seen.has(page.number as number) ||
      !finite(page.width) ||
      page.width <= 0 ||
      !finite(page.height) ||
      page.height <= 0
    ) {
      throw new Error("Invalid document page geometry.");
    }
    seen.add(page.number as number);
  }
  return value as unknown as DocumentSummary;
}

export function validateExtraction(value: unknown, document: DocumentSummary): ExtractionResult {
  if (
    !object(value) ||
    typeof value.schema !== "string" ||
    typeof value.provider !== "string" ||
    !object(value.report) ||
    !Array.isArray(value.report.fields) ||
    !Array.isArray(value.report.cross_field_issues)
  ) {
    throw new Error("Invalid extraction report.");
  }
  const paths = new Set<string>();
  const counts = { verified: 0, needs_review: 0, unsupported: 0 };
  for (const field of value.report.fields) {
    if (
      !object(field) ||
      typeof field.path !== "string" ||
      !field.path ||
      paths.has(field.path) ||
      !(typeof field.value === "string" || typeof field.value === "boolean" || finite(field.value)) ||
      typeof field.status !== "string" ||
      !Object.hasOwn(counts, field.status) ||
      !Array.isArray(field.reasons) ||
      !field.reasons.every((reason) => typeof reason === "string") ||
      !(field.matched_text === null || typeof field.matched_text === "string") ||
      !(
        field.match_score === null ||
        (finite(field.match_score) && field.match_score >= 0 && field.match_score <= 100)
      ) ||
      !(
        field.page === null ||
        (Number.isSafeInteger(field.page) &&
          (field.page as number) >= 1 &&
          (field.page as number) <= document.page_count)
      ) ||
      !Array.isArray(field.rects)
    ) {
      throw new Error("Invalid extracted field or evidence.");
    }
    paths.add(field.path);
    counts[field.status as FieldStatus]++;
    for (const rect of field.rects) {
      if (
        !object(rect) ||
        !finite(rect.x0) ||
        !finite(rect.x1) ||
        !finite(rect.top) ||
        !finite(rect.bottom) ||
        rect.x1 < rect.x0 ||
        rect.bottom < rect.top
      ) {
        throw new Error("Invalid evidence rectangle.");
      }
    }
  }
  const extraction = value as unknown as ExtractionResult;
  return {
    ...extraction,
    report: { ...extraction.report, counts },
    review: validatedOverlay(value.review, extraction.report.fields),
  };
}
