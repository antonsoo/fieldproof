import { strToU8, zipSync } from "fflate";
import type { ExportRow } from "./export";

export const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const columns = [
  "field",
  "value",
  "original_value",
  "value_source",
  "verification_status",
  "review_status",
  "page",
] as const;
const ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
const rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const packageRel = "http://schemas.openxmlformats.org/package/2006/relationships";

function cell(value: unknown, address: string): string {
  if (value === null) return `<c r="${address}"/>`;
  if (typeof value === "boolean") return `<c r="${address}" t="b"><v>${value ? 1 : 0}</v></c>`;
  if (typeof value === "number" && Number.isFinite(value))
    return `<c r="${address}" t="n"><v>${value}</v></c>`;
  let problem: string | undefined;
  if (typeof value !== "string") problem = "is not a finite scalar";
  // The Unicode flag recognizes valid surrogate pairs as a single code point.
  else if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ud800-\udfff\ufffe\uffff]/u.test(value))
    problem = "contains text that XLSX cannot safely represent";
  else if (value.length > 32767) problem = "exceeds the XLSX limit of 32,767 UTF-16 units";
  if (problem) throw new Error(`Cell ${address} ${problem}. Export JSON to keep the complete data.`);
  // Match server/spreadsheet.py: source OOXML escape sequences are literal;
  // CR is escaped only afterward to preserve it through XML normalization.
  const text = (value as string)
    .replace(/_x[0-9a-fA-F]{4}_/g, (m) => "_x005F_" + m.slice(1))
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\r/g, "_x000D_");
  return `<c r="${address}" t="inlineStr"><is><t xml:space="preserve">${text}</t></is></c>`;
}

/** One-sheet OOXML writer. Text never becomes a formula or hyperlink. */
export function rowsToXlsx(rows: ExportRow[]): Uint8Array<ArrayBuffer> {
  if (rows.length > 1048575)
    throw new Error("XLSX supports 1,048,575 data rows. Export JSON to keep all rows.");
  const line = (values: unknown[], index: number) =>
    `<row r="${index}">${values.map((v, i) => cell(v, `${String.fromCharCode(65 + i)}${index}`)).join("")}</row>`;
  const data = [
    line([...columns], 1),
    ...rows.map((r, i) =>
      line(
        columns.map((key) => r[key]),
        i + 2,
      ),
    ),
  ].join("");
  const parts: Record<string, string> = {
    "[Content_Types].xml": `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`,
    "_rels/.rels": `<Relationships xmlns="${packageRel}"><Relationship Id="rId1" Type="${rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    "xl/workbook.xml": `<workbook xmlns="${ns}" xmlns:r="${rel}"><sheets><sheet name="Fields" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": `<Relationships xmlns="${packageRel}"><Relationship Id="rId1" Type="${rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
    "xl/worksheets/sheet1.xml": `<worksheet xmlns="${ns}"><dimension ref="A1:G${rows.length + 1}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="3" width="32" customWidth="1"/><col min="4" max="6" width="22" customWidth="1"/></cols><sheetData>${data}</sheetData><autoFilter ref="A1:G${rows.length + 1}"/></worksheet>`,
  };
  return zipSync(
    Object.fromEntries(
      Object.entries(parts).map(([name, xml]) => [
        name,
        strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${xml}`),
      ]),
    ),
    { level: 6, mtime: new Date(2000, 0, 1) },
  );
}
