// Capture the runtime's locale formatter, independent of Fieldproof's parser.
import { writeFileSync } from 'node:fs';

const cases = [];
for (const [locale, numberingSystem] of [['ar-EG', 'arab'], ['fa-IR', 'arabext'], ['ar-EG', 'latn']]) {
  for (const [label, input] of [
    ['grouped', '1234.56'], ['decimal', '1.25'], ['million', '1234567.89'],
    ['integer', '1234'], ['negative', '-1234.56'], ['large-integer', '9007199254740993'],
  ]) {
    const integer = ['integer', 'large-integer'].includes(label);
    const options = { numberingSystem, minimumFractionDigits: integer ? 0 : 2, maximumFractionDigits: integer ? 0 : 2 };
    const formatter = new Intl.NumberFormat(locale, options);
    const value = integer ? BigInt(input) : Number(input);
    const parts = formatter.formatToParts(value);
    cases.push({ id: `${numberingSystem}-${label}`, locale, input, options,
      formatted: formatter.format(value), parts,
      numericText: parts.filter(part => part.type !== 'literal').map(part => part.value).join(''), integer });
  }
  const options = { numberingSystem, style: 'percent', maximumFractionDigits: 1 };
  const formatter = new Intl.NumberFormat(locale, options);
  const parts = formatter.formatToParts(.125);
  cases.push({ id: `${numberingSystem}-percent`, locale, input: '0.125', options,
    formatted: formatter.format(.125), parts,
    numericText: parts.filter(part => part.type !== 'literal').map(part => part.value).join(''), percent: true });
}
writeFileSync(new URL('intl.json', import.meta.url), JSON.stringify({
  scope: 'Unmodified native Intl.NumberFormat output and parts. Authored PDF fixtures omit literal bidi marks to isolate numeric evidence.',
  node: process.version, icu: process.versions.icu, unicode: process.versions.unicode, cases,
}, null, 2) + '\n');
