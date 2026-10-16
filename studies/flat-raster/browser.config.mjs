// Use a separately installed wheel and production UI builds.
import config from '../column-evidence/browser.config.mjs';
export default { ...config, grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /flat-raster|hidden-text/ };
