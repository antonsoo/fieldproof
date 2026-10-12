// Run against a separately launched installed wheel; opt in to the whole suite.
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const all = process.env.FIELDPROOF_BROWSER_FULL === '1';
const liveURL = process.env.FIELDPROOF_BROWSER_URL || 'http://127.0.0.1:4300/';
const demoURL = process.env.FIELDPROOF_DEMO_URL || 'http://127.0.0.1:4301/fieldproof/';
export default {
  testDir: fileURLToPath(new URL('../../web/tests/browser', import.meta.url)),
  ...(all ? {} : { grep: /explicit headers expose/ }),
  timeout: 30000, workers: 1, fullyParallel: false, reporter: 'list',
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || join(tmpdir(), 'fieldproof-column-evidence-browser'),
  use: { viewport: { width: 1440, height: 960 }, trace: 'retain-on-failure' },
  projects: ['chromium', 'firefox'].flatMap(browserName => [
    { name: `${browserName}-live`, testMatch: /live\.spec\.mjs/, use: { browserName, baseURL: liveURL } },
    ...(all ? [{ name: `${browserName}-demo`, testMatch: /demo\.spec\.mjs/, use: { browserName, baseURL: demoURL } }] : []),
  ]),
};
