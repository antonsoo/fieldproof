// Exercise a separately installed wheel with the production review UI.
import config from '../column-evidence/browser.config.mjs';

export default {
  ...config,
  grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /unpainted PDF evidence \(clipped-text\)/,
};
