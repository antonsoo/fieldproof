import { describe, expect, it } from "vitest";
import { nextReview, parseEditValue, validatedOverlay } from "./review";
import { computeExportRows, rowsToCsv } from "./export";
import type { ExtractionResult, FieldVerification } from "./types";

const field = (path: string, value: FieldVerification["value"]): FieldVerification => ({
  path,
  value,
  status: "verified",
  reasons: [],
  match_score: 100,
  matched_text: String(value),
  page: 1,
  rects: [],
});

describe("typed corrections", () => {
  it.each([
    ["321.50", 321.5],
    ["0", 0],
    ["-12.5", -12.5],
    [".5", 0.5],
    ["1e2", 100],
  ])("parses %s as a number", (text, expected) => {
    expect(parseEditValue(100, text as string)).toBe(expected);
  });
  it.each(["", " ", "NaN", "Infinity", "1e309", "$12", "1,234", "0x10", "1 2"])(
    "refuses invalid numeric input %s",
    (text) => {
      expect(() => parseEditValue(100, text)).toThrow();
    },
  );
  it("preserves string identifiers and explicit false", () => {
    expect(parseEditValue("00012", "00034")).toBe("00034");
    expect(parseEditValue(true, "false")).toBe(false);
    expect(() => parseEditValue(false, "yes")).toThrow();
  });
  it.each([321.5, 0, false, "00034", ""])("approve/reject preserve correction %s until reset", (value) => {
    const original = typeof value === "number" ? 100 : typeof value === "boolean" ? true : "original";
    let review = nextReview(original, undefined, "edit", value);
    review = nextReview(original, review, "approve");
    expect(review).toEqual({ status: "approved", edited_value: value });
    review = nextReview(original, review, "reject");
    expect(review).toEqual({ status: "rejected", edited_value: value });
    expect(nextReview(original, review, "reset")).toEqual({ status: "pending", edited_value: null });
  });
  it.each([null, "123", true, {}, [], Infinity, NaN])("rejects a numeric field correction of %s", (value) => {
    expect(() => nextReview(100, undefined, "edit", value)).toThrow();
  });
});

describe("stored decisions and export contract", () => {
  it("discards unknown paths, corrupt status and mismatched corrections", () => {
    const fields = [field("amount", 100), field("identifier", "00012"), field("active", true)];
    const raw = {
      amount: { status: "edited", edited_value: "" },
      identifier: { status: "approved", edited_value: "00034" },
      active: { status: "edited", edited_value: false },
      unknown: { status: "approved", edited_value: null },
    };
    expect(validatedOverlay(raw, fields)).toEqual({ identifier: raw.identifier, active: raw.active });
    expect(validatedOverlay([], fields)).toEqual({});
    expect(validatedOverlay({ amount: { status: "made_up", edited_value: null } }, fields)).toEqual({});
  });
  it("an approved correction of zero is exported, pending fields require all scope, rejected fields stay out", () => {
    const extraction: ExtractionResult = {
      schema: "invoice",
      provider: "fixture",
      model: null,
      data: {},
      report: {
        fields: [field("amount", 100), field("pending", "pending"), field("rejected", "secret")],
        counts: { verified: 3, needs_review: 0, unsupported: 0 },
        cross_field_issues: [],
      },
      review: {
        amount: { status: "approved", edited_value: 0 },
        rejected: { status: "rejected", edited_value: null },
      },
    };
    const reviewed = computeExportRows(extraction, "reviewed");
    expect(reviewed).toEqual([
      {
        field: "amount",
        value: 0,
        original_value: 100,
        value_source: "correction",
        verification_status: "verified",
        review_status: "approved",
        page: 1,
      },
    ]);
    expect(computeExportRows(extraction, "all").map((row) => row.field)).toEqual(["amount", "pending"]);
    expect(extraction.report.fields[0]!.value).toBe(100);
  });
  it("quotes carriage returns, newlines, commas and double quotes in CSV", () => {
    const value = 'a,b\rline\n"quoted"';
    expect(
      rowsToCsv([
        {
          field: "name",
          value,
          original_value: "original",
          value_source: "correction",
          verification_status: "verified",
          review_status: "edited",
          page: null,
        },
      ]),
    ).toBe(
      'field,value,original_value,value_source,verification_status,review_status,page\r\nname,"a,b\rline\n""quoted""",original,correction,verified,edited,\r\n',
    );
  });
});
