// Run against a separately launched installed wheel.
import config from '../column-evidence/browser.config.mjs';

export default {
  ...config,
  grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /unpainted PDF evidence \(zero-opacity\)/,
};
