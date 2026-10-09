// Start the installed wheel's server separately on port 4297, then run this
// config using web/node_modules/.bin/playwright. No checkout server is started.
import { fileURLToPath } from 'node:url';

export default {
  testDir: fileURLToPath(new URL('../../web/tests/browser', import.meta.url)),
  testMatch: /live\.spec\.mjs/,
  grep: /quoted but inconsistent line arithmetic/,
  timeout: 30000,
  workers: 1,
  reporter: 'list',
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || '/tmp/claude-1000/fieldproof-arithmetic/browser',
  use: {
    baseURL: process.env.FIELDPROOF_BROWSER_URL || 'http://127.0.0.1:4297/',
    viewport: { width: 1440, height: 960 },
  },
  projects: ['chromium', 'firefox'].map(browserName => ({ name: browserName, use: { browserName } })),
};
