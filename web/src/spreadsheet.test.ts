import { describe, expect, it } from "vitest";
import { strFromU8, unzipSync } from "fflate";
import { rowsToXlsx } from "./spreadsheet";
import type { ExportRow } from "./export";
import cases from "../../studies/spreadsheet-export/cases.json";

const rows = cases as ExportRow[];
const sheet = (input: ExportRow[]) => strFromU8(unzipSync(rowsToXlsx(input))["xl/worksheets/sheet1.xml"]!);

describe("literal spreadsheet export", () => {
  it("stores identifiers and formula-like values as strings, while retaining scalar types", () => {
    const xml = sheet(rows);
    expect(xml).not.toMatch(/<f[ >]|hyperlink|externalLink/);
    for (const text of ["00034", "=1+1", "1E10", "12345678901234567890", "café 漢字 😀"])
      expect(xml).toContain(`t="inlineStr"><is><t xml:space="preserve">${text}</t></is>`);
    expect(xml).toContain('<c r="B24" t="b"><v>1</v></c>');
    expect(xml).toContain('<c r="B25" t="b"><v>0</v></c>');
    expect(xml).toContain('<c r="B26" t="n"><v>0</v></c>');
    expect(xml).toContain('<c r="B27" t="n"><v>-12.5</v></c>');
    expect(xml).toContain('<c r="B28"/>');
  });
  it("escapes XML and OOXML without altering source text", () => {
    const xml = sheet(rows);
    expect(xml).toContain(">_x005F_x0041_</t>");
    expect(xml).toContain(">_x005F_x005F_x0041_</t>");
    expect(xml).toContain(">a_x000D_\nb</t>");
    expect(xml).toContain('>&amp;&lt;&gt;"</t>');
  });
  it.each([9007199254740991, 1.2345678901234567, 1e-309, 1e308])(
    "preserves the current numeric spelling outside spreadsheet precision (%s)",
    (value) => {
      const xml = sheet([{ ...rows[0]!, value, original_value: value }]);
      for (const column of ["B", "C"])
        expect(xml).toContain(
          `<c r="${column}2" t="inlineStr"><is><t xml:space="preserve">${value}</t></is></c>`,
        );
    },
  );
  it.each([999999999999999, -999999999999999, 123.456789012345, 1e-307])(
    "keeps ordinary numeric cells through the supported boundary (%s)",
    (value) => expect(sheet([{ ...rows[0]!, value }])).toContain(`<c r="B2" t="n"><v>${value}</v></c>`),
  );
  it.each(["\0", "\v", "\ud800", "\udfff", "\ufffe", "a".repeat(32768), "😀".repeat(16384), Infinity, {}])(
    "rejects unrepresentable cells without a partial download (%#)",
    (value) => {
      for (const column of Object.keys(rows[0]!))
        expect(() => rowsToXlsx([{ ...rows[0]!, [column]: value }])).toThrow(/Cell [A-G]2 .*Export JSON/);
    },
  );
  it("accepts the UTF-16 length boundary and empty row sets", () => {
    for (const value of ["a".repeat(32767), "😀".repeat(16383) + "a"])
      expect(sheet([{ ...rows[0]!, value }])).toContain(`>${value}</t>`);
    expect(sheet([])).toContain('dimension ref="A1:G1"');
    expect(() => rowsToXlsx(new Array<ExportRow>(1048576))).toThrow("1,048,575 data rows");
  });
});
