import type { DocumentSummary, ExtractionResult, FieldStatus, SessionList } from "./types";
import { validatedOverlay } from "./review";

function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function validateTextSource(value: Record<string, unknown>, pageCount: number): void {
  if (
    value.text_mode !== undefined &&
    !["native", "ocr-missing", "ocr-all"].includes(value.text_mode as string)
  )
    throw new Error("Invalid document text source.");
  const ocr = value.ocr;
  if (value.text_mode === "native" && ocr) throw new Error("Native text mode conflicts with OCR provenance.");
  if (value.text_mode === "ocr-all" && !ocr) throw new Error("All-page OCR has no recognition provenance.");
  if (ocr === undefined || ocr === null) return;
  const pageList = (pages: unknown): pages is number[] =>
    Array.isArray(pages) &&
    pages.length <= pageCount &&
    new Set(pages).size === pages.length &&
    pages.every((p) => Number.isSafeInteger(p) && p >= 1 && p <= pageCount);
  if (
    !object(ocr) ||
    ocr.page_count !== pageCount ||
    ![ocr.engine, ocr.version, ocr.language].every(
      (s) => typeof s === "string" && s.length > 0 && s.length <= 128,
    ) ||
    typeof ocr.note !== "string" ||
    ocr.note.length > 2000 ||
    !Number.isSafeInteger(ocr.render_dpi) ||
    (ocr.render_dpi as number) < 1 ||
    (ocr.render_dpi as number) > 1200 ||
    !pageList(ocr.empty_pages) ||
    (ocr.processed_pages !== undefined && !pageList(ocr.processed_pages))
  )
    throw new Error("Invalid OCR provenance.");
  if (
    Array.isArray(ocr.processed_pages) &&
    (ocr.processed_pages.length === 0 ||
      (value.text_mode === "ocr-all" && ocr.processed_pages.length !== pageCount))
  )
    throw new Error("OCR page coverage conflicts with its source mode.");
  if (ocr.processed_pages && ocr.empty_pages.some((p) => !(ocr.processed_pages as number[]).includes(p)))
    throw new Error("Empty OCR pages were not processed.");
}

export function validateSessions(value: unknown): SessionList {
  if (
    !object(value) ||
    !Array.isArray(value.documents) ||
    !Number.isSafeInteger(value.max_sessions) ||
    (value.max_sessions as number) < 1 ||
    (value.max_sessions as number) > 64 ||
    value.documents.length > (value.max_sessions as number) ||
    !Number.isSafeInteger(value.max_pdf_bytes) ||
    (value.max_pdf_bytes as number) < 1 ||
    !Number.isSafeInteger(value.max_pages) ||
    (value.max_pages as number) < 1
  ) {
    throw new Error("Invalid session list.");
  }
  const ids = new Set<string>();
  for (const entry of value.documents) {
    const document = validateDocument(entry);
    if (
      !object(entry) ||
      ids.has(document.id) ||
      typeof entry.has_extraction !== "boolean" ||
      typeof entry.busy !== "boolean" ||
      !Number.isSafeInteger(entry.pdf_bytes) ||
      (entry.pdf_bytes as number) < 1 ||
      !Number.isSafeInteger(entry.field_count) ||
      (entry.field_count as number) < 0 ||
      !Number.isSafeInteger(entry.reviewed_count) ||
      (entry.reviewed_count as number) < 0 ||
      (entry.reviewed_count as number) > (entry.field_count as number)
    ) {
      throw new Error("Invalid session summary.");
    }
    ids.add(document.id);
  }
  return value as unknown as SessionList;
}

export function validateDocument(value: unknown): DocumentSummary {
  if (
    !object(value) ||
    typeof value.id !== "string" ||
    !value.id ||
    typeof value.filename !== "string" ||
    (value.restored_from_archive !== undefined && typeof value.restored_from_archive !== "boolean") ||
    !Number.isSafeInteger(value.page_count) ||
    (value.page_count as number) < 1 ||
    !Array.isArray(value.pages) ||
    value.pages.length !== value.page_count
  ) {
    throw new Error("Invalid document summary.");
  }
  const seen = new Set<number>();
  validateTextSource(value, value.page_count as number);
  if (
    value.source_credit !== undefined &&
    (typeof value.source_credit !== "string" || value.source_credit.length > 500)
  )
    throw new Error("Invalid document attribution.");
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
  validateTextSource({ ...value.report, text_mode: value.text_mode }, document.page_count);
  if (document.ocr && object(value.report.ocr)) {
    const observed = value.report.ocr;
    for (const key of ["engine", "version", "language", "render_dpi", "page_count"] as const)
      if (document.ocr[key] !== observed[key])
        throw new Error("Report OCR provenance differs from the loaded document.");
    for (const key of ["processed_pages", "empty_pages"] as const)
      if (JSON.stringify(document.ocr[key]) !== JSON.stringify(observed[key]))
        throw new Error("Report OCR pages differ from the loaded document.");
  }
  if (document.ocr && !value.report.ocr)
    throw new Error("OCR document report lost its recognition provenance.");
  if (document.text_mode && document.text_mode !== "native" && document.text_mode !== value.text_mode)
    throw new Error("Report text source differs from the loaded document.");
  if (!document.ocr && value.report.ocr)
    throw new Error("Report OCR provenance is absent from the loaded document.");
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
