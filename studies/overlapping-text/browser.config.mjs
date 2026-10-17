// The live API must come from the separately installed wheel under test.
import config from '../column-evidence/browser.config.mjs';
export default { ...config, grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /overlapping-text/ };
