import { expect, it } from "vitest";
import invoice from "../public/demo-data/invoice/data.json";
import { validateDocument, validateExtraction, validateSessions } from "./validate";

it("accepts the actual pipeline fixture and derives verification counts from fields", () => {
  const document = validateDocument(invoice.document);
  const raw = structuredClone(invoice.extraction);
  raw.report.counts.verified = 0;
  const extraction = validateExtraction(raw, document);
  expect(extraction.report.counts).toEqual({ verified: 21, needs_review: 3, unsupported: 1 });
  expect(extraction.report.fields).toEqual(invoice.extraction.report.fields);
});

it.each([
  null,
  { ...invoice.document, page_count: 2 },
  { ...invoice.document, pages: [{ ...invoice.document.pages[0], width: NaN }] },
  { ...invoice.document, pages: [{ ...invoice.document.pages[0], height: 0 }] },
  { ...invoice.document, pages: [{ ...invoice.document.pages[0], number: 0 }] },
])("rejects damaged document geometry %#", (value) => {
  expect(() => validateDocument(value)).toThrow();
});

it.each([
  { value: Infinity },
  { status: "unknown" },
  { page: 2 },
  { match_score: NaN },
  { reasons: [null] },
  { rects: [{ x0: 20, x1: 10, top: 0, bottom: 10 }] },
])("rejects damaged evidence %#", (change) => {
  const raw = structuredClone(invoice.extraction);
  Object.assign(raw.report.fields[0]!, change);
  expect(() => validateExtraction(raw, invoice.document)).toThrow();
});

it("rejects duplicate field paths instead of attaching one decision to multiple fields", () => {
  const raw = structuredClone(invoice.extraction);
  raw.report.fields[1]!.path = raw.report.fields[0]!.path;
  expect(() => validateExtraction(raw, invoice.document)).toThrow();
});

const sessions = {
  documents: [
    {
      ...invoice.document,
      pdf_bytes: 2388,
      has_extraction: true,
      busy: false,
      field_count: 25,
      reviewed_count: 4,
    },
  ],
  max_sessions: 8,
  max_pdf_bytes: 25 * 1024 * 1024,
  max_pages: 64,
};

it("accepts valid session metadata without losing original summaries", () => {
  expect(validateSessions(sessions)).toBe(sessions);
});

it.each([
  { ...sessions, max_sessions: 0 },
  { ...sessions, max_sessions: 1000000 },
  { ...sessions, documents: [...sessions.documents, ...sessions.documents] },
  { ...sessions, documents: [{ ...sessions.documents[0], reviewed_count: 26 }] },
  { ...sessions, documents: [{ ...sessions.documents[0], busy: "false" }] },
  { ...sessions, documents: [{ ...sessions.documents[0], field_count: -1 }] },
])("rejects malformed or duplicated session metadata %#", (value) => {
  expect(() => validateSessions(value)).toThrow();
});

it("preserves real OCR source metadata and rejects missing or conflicting provenance", async () => {
  const { default: cord } = await import("../public/demo-data/cord-ocr/data.json");
  const document = validateDocument(cord.document);
  expect(validateExtraction(cord.extraction, document).report.ocr).toEqual(cord.document.ocr);
  for (const change of [
    { text_mode: "native" },
    { ocr: { ...cord.document.ocr, processed_pages: [] } },
    { ocr: { ...cord.document.ocr, processed_pages: [2] } },
    { ocr: { ...cord.document.ocr, empty_pages: [2] } },
  ])
    expect(() => validateDocument({ ...cord.document, ...change })).toThrow();
  for (const change of [
    { text_mode: undefined },
    { text_mode: "ocr-missing" },
    { report: { ...cord.extraction.report, ocr: undefined } },
    { report: { ...cord.extraction.report, ocr: { ...cord.document.ocr, version: "changed" } } },
  ])
    expect(() => validateExtraction({ ...cord.extraction, ...change }, document)).toThrow();
});
