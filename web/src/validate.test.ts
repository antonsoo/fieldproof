import { expect, it } from "vitest";
import invoice from "../public/demo-data/invoice/data.json";
import { validateDocument, validateExtraction } from "./validate";

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
