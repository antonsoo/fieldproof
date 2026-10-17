// Capture the formatter's original inputs as the oracle; do not parse its output.
import { writeFileSync } from 'node:fs';

const cases = [];
for (const locale of ['fr-FR', 'ru-RU', 'sv-SE']) {
  for (const input of ['1234.56', '1234567.89', '-1234.56', '1234', '0.5']) {
    const formatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
    const parts = formatter.formatToParts(Number(input));
    cases.push({ id: `${locale}-${input}`, locale, input, parts, text: parts.map(p => p.value).join('') });
  }
}
writeFileSync(new URL('intl.json', import.meta.url), JSON.stringify({ node: process.version, icu: process.versions.icu, cases }, null, 2) + '\n');
