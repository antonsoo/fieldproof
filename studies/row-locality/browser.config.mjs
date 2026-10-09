// Start the installed wheel server separately; these tests do not import source.
import { fileURLToPath } from 'node:url';

export default {
  testDir: fileURLToPath(new URL('../../web/tests/browser', import.meta.url)),
  testMatch: /live\.spec\.mjs/,
  grep: /a repeated quantity from another row/,
  timeout: 30000,
  workers: 1,
  reporter: 'list',
  outputDir: process.env.FIELDPROOF_BROWSER_OUTPUT || '/tmp/claude-1000/fieldproof-locality/browser',
  use: {
    baseURL: process.env.FIELDPROOF_BROWSER_URL || 'http://127.0.0.1:4298/',
    viewport: { width: 1440, height: 960 },
  },
  projects: ['chromium', 'firefox'].map(browserName => ({ name: browserName, use: { browserName } })),
};
