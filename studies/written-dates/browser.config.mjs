// Exercise a separately installed wheel and its bundled review UI.
import config from '../row-association/browser.config.mjs';
export default {
  ...config,
  grep: /a written date keeps every printed year digit/,
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || '/tmp/fieldproof-written-date-browser',
};
