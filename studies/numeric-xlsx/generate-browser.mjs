// Directly invoke the browser's exported writer, keeping its current Number spellings.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const [rootArg, outputArg, label, observe] = process.argv.slice(2);
assert(rootArg && outputArg && label, 'Expected CRATE_ROOT OUTPUT LABEL [--observe-only]');
const root = resolve(rootArg), output = resolve(outputArg);
const { rowsToXlsx } = await import(pathToFileURL(resolve(root, 'web/src/spreadsheet.ts')));
const require = createRequire(pathToFileURL(resolve(root, 'web/package.json')));
const { strFromU8, unzipSync } = require('fflate');
mkdirSync(output, { recursive: true });
const cases = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url)));
const rows = [], records = [];
for (const item of cases.filter(item => Object.hasOwn(item, 'value'))) {
  const value = item.value;
  const row = { field: item.id, value, original_value: value, value_source: 'extracted', verification_status: 'verified', review_status: 'approved', page: 1 };
  const payload = rowsToXlsx([row]);
  const xml = strFromU8(unzipSync(payload)['xl/worksheets/sheet1.xml']);
  const target = /<c r="B2"(?: t="([^"]+)")?>(.*?)<\/c>|<c r="B2"\/>/.exec(xml);
  assert(target, item.id);
  const type = target[1] ?? 'blank';
  const text = type === 'inlineStr' ? /<t[^>]*>(.*?)<\/t>/.exec(target[2])?.[1] : null;
  const agrees = type === item.cell && (type !== 'inlineStr' || text === String(value));
  const name = `writer-${item.id}.xlsx`;
  writeFileSync(resolve(output, name), payload);
  rows.push(row); records.push({ case: item.id, agrees, sourceSpelling: String(value), type, text, file: name, sha256: createHash('sha256').update(payload).digest('hex') });
}
writeFileSync(resolve(output, 'writer-all.xlsx'), rowsToXlsx(rows));
const result = { label, node: process.version, workflows: records.length, disagreements: records.filter(row => !row.agrees).length, records };
writeFileSync(resolve(output, 'observations.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ label, workflows: result.workflows, disagreements: result.disagreements }));
assert(observe === '--observe-only' || result.disagreements === 0);
