// Exercise the separately installed wheel, including its bundled UI.
import config from '../row-association/browser.config.mjs';

export default {
  ...config,
  grep: /an invalid date reference cannot settle/,
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || '/tmp/fieldproof-date-browser',
};
