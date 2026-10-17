// The server is an independently installed wheel with its bundled production UI.
import config from '../column-evidence/browser.config.mjs';
export default { ...config, grep: process.env.FIELDPROOF_BROWSER_FULL === '1' ? undefined : /Arabic amount fragments/ };
