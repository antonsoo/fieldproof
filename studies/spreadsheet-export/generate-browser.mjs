// Node 24's TypeScript stripping runs the same writer included in the UI.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { rowsToXlsx } from '../../web/src/spreadsheet.ts';
const out = process.argv[2];
const cases = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url)));
writeFileSync(join(out, 'browser-cases.xlsx'), rowsToXlsx(cases));
