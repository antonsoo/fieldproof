// Use the installed wheel's API and bundled UI, with no source server fallback.
import config from '../column-evidence/browser.config.mjs';
export default { ...config, grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /native glyph overhang/ };
