// Check actual browser response bytes against the installed wheel's bundled UI.
// node served-assets.mjs <web-root> <origin> <installed-static-dir> <out.json>
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const [web, originArg, staticArg, out] = process.argv.slice(2);
assert.ok(web && originArg && staticArg && out);
const origin = new URL(originArg).origin;
const staticDir = resolve(staticArg);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { chromium, firefox } = createRequire(join(resolve(web), 'package.json'))('playwright');
const hash = body => createHash('sha256').update(body).digest('hex');
const results = [];
for (const [engine, launcher] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await launcher.launch();
  try {
    const context = await browser.newContext({ baseURL: origin, viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
    try {
      const page = await context.newPage();
      const errors = [], requests = [], pending = [], assets = new Map();
      page.on('pageerror', error => errors.push(error.message));
      context.on('request', request => requests.push(request.url()));
      context.on('response', response => {
        const url = new URL(response.url());
        if (url.origin !== origin || (url.pathname !== '/' && !url.pathname.startsWith('/assets/'))) return;
        pending.push((async () => {
          assert.equal(response.status(), 200);
          const name = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
          const body = await response.body();
          assert.deepEqual(body, await readFile(join(staticDir, name)), name);
          assets.set(name, { bytes: body.length, sha256: hash(body) });
        })());
      });
      await page.goto(`${origin}/`);
      await page.getByLabel('PDF document').setInputFiles(join(root, 'examples/mixed-conventions.pdf'));
      await page.getByRole('button', { name: 'Run extraction' }).waitFor();
      await page.getByLabel('Fixture JSON').setInputFiles(join(root, 'examples/fixtures/mixed-conventions.json'));
      await page.getByRole('button', { name: 'Run extraction' }).click();
      await page.locator('.field-reasons').filter({ hasText: 'conflicting evidence' }).first().waitFor();
      assert.equal(await page.locator('.field-reasons').filter({ hasText: 'conflicting evidence' }).count(), 2);
      await page.getByRole('button', { name: 'Inspect issue_date', exact: true }).click();
      await page.locator('#page-frame img').waitFor();
      await page.evaluate(() => document.fonts.ready);
      await Promise.all(pending);
      assert.deepEqual(errors, []);
      assert.ok(requests.every(url => new URL(url).origin === origin), 'no external requests');
      assert.ok(assets.has('index.html') && [...assets.keys()].some(name => name.endsWith('.js')) && [...assets.keys()].some(name => name.endsWith('.css')));
      const documentUrl = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
      const report = await (await context.request.get(documentUrl + '/report')).json();
      assert.deepEqual(report.report.counts, { verified: 2, needs_review: 2, unsupported: 0 });
      assert.equal((await context.request.delete(documentUrl)).status(), 204);
      results.push({ engine, version: browser.version(), assets: Object.fromEntries([...assets].sort()), externalRequests: 0, pageErrors: errors, counts: report.report.counts });
      console.log(engine, assets.size, 'actual browser asset responses match the installed wheel');
    } finally { await context.close(); }
  } finally { await browser.close(); }
}
await writeFile(out, JSON.stringify({ driverSha256: hash(await readFile(fileURLToPath(import.meta.url))), results }, null, 2) + '\n');
