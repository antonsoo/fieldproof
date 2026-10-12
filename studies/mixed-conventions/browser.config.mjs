// Target the separately installed wheel and its bundled review UI.
import config from '../row-association/browser.config.mjs';

export default {
  ...config,
  grep: /conflicting document conventions stay explicit/,
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || '/tmp/fieldproof-mixed-browser',
};
