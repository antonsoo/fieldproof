import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 30_000,
  // Capacity and deletion checks share one disposable in-memory API server.
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { viewport: { width: 1440, height: 900 }, trace: 'retain-on-failure' },
  projects: ['chromium', 'firefox'].flatMap(browserName => [
    { name: `${browserName}-demo`, testMatch: /demo\.spec\.mjs/, use: { browserName, baseURL: 'http://127.0.0.1:4290/fieldproof/' } },
    { name: `${browserName}-live`, testMatch: /live\.spec\.mjs/, use: { browserName, baseURL: 'http://127.0.0.1:4289/' } },
  ]),
  webServer: [
    { command: 'npm run preview -- --mode demo --outDir dist-demo --host 127.0.0.1 --port 4290 --strictPort', wait: { stdout: /Local:\s+http:\/\/127\.0\.0\.1:4290\/fieldproof\// }, timeout: 15_000 },
    { command: 'cd .. && uv run --locked --extra dev uvicorn fieldproof.server.app:app --host 127.0.0.1 --port 4289', env: { FIELDPROOF_STATIC_DIR: fileURLToPath(new URL('./dist', import.meta.url)) }, wait: { stderr: /Uvicorn running on http:\/\/127\.0\.0\.1:4289/ }, timeout: 15_000 },
  ],
});
