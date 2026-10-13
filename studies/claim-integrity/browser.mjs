import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
const { values: args } = parseArgs({ options: Object.fromEntries(['url', 'fixtures', 'tools', 'static', 'output'].map(k => [k, { type: 'string' }])) });
args.url = new URL(args.url).href;
const require = createRequire(join(args.tools, 'package.json'));
const { chromium, firefox, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const sha = b => createHash('sha256').update(b).digest('hex');
const row = (page, path) => page.locator('.field-row').filter({ has: page.getByRole('button', { name: `Inspect ${path}`, exact: true }) });
const records = [];
for (const [engine, driver] of Object.entries({ chromium, firefox })) {
  const browser = await driver.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: width === 1440 ? 'dark' : 'light' });
      try {
        const page = await context.newPage(), errors = [], external = [], pending = [], assets = {};
        page.on('pageerror', e => errors.push(e.message));
        await page.addInitScript(() => {
          window.cspErrors = [];
          addEventListener('securitypolicyviolation', event => window.cspErrors.push(event.violatedDirective));
        });
        await context.route('**/*', route => {
          if (new URL(route.request().url()).origin !== new URL(args.url).origin) { external.push(route.request().url()); return route.abort(); }
          return route.continue();
        });
        page.on('response', response => {
          const path = new URL(response.url()).pathname;
          if (response.status() === 200 && (path === '/' || path.startsWith('/assets/'))) {
            pending.push(response.body().then(async bytes => {
              const name = path === '/' ? 'index.html' : path.slice(1);
              assert.equal(sha(bytes), sha(await readFile(join(args.static, name))));
              assets[name] = { bytes: bytes.length, sha256: sha(bytes) };
            }));
          }
        });
        await page.goto(args.url);
        await page.getByLabel('PDF document', { exact: true }).setInputFiles(join(args.fixtures, 'synthetic-invoice.pdf'));
        const fixture = page.getByLabel('Fixture JSON', { exact: true });
        const run = page.getByRole('button', { name: 'Run extraction', exact: true });
        await expect(run).toBeVisible();
        const doc = (await (await context.request.get(`${args.url}api/documents`)).json()).documents.at(-1);
        const root = `${args.url}api/documents/${doc.id}`;
        const attempts = [];
        for (const [name, diagnostic] of [['duplicate-value', 'duplicate JSON member'], ['unknown-claim', 'bank_account'], ['unknown-row', 'line_items.0.discount'], ['unpaired-surrogate', 'invalid Unicode']]) {
          await fixture.setInputFiles(join(args.fixtures, `${name}.json`));
          const pendingResponse = page.waitForResponse(r => r.url() === `${root}/extract` && r.request().method() === 'POST');
          await run.focus(); await page.keyboard.press('Enter');
          const response = await pendingResponse; assert.equal(response.status(), 422);
          await expect(page.locator('#operation-status')).toContainText(diagnostic);
          await expect(page.locator('.field-row')).toHaveCount(0);
          attempts.push({ fixture: name, status: response.status(), diagnostic: await page.locator('#operation-status').innerText(), via: 'file picker before initial extraction' });
          if (name === 'unknown-claim') {
            await page.evaluate(() => document.fonts.ready);
            assert.equal((await new AxeBuilder({ page }).analyze()).violations.length, 0);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
            await page.screenshot({ path: join(args.output, `${engine}-${width}-error.png`), fullPage: true });
          }
        }
        await fixture.setInputFiles(join(args.fixtures, 'valid.json')); await run.click();
        await expect(row(page, 'total')).toBeVisible();
        const total = row(page, 'total');
        await total.getByRole('button', { name: 'Edit', exact: true }).click();
        await total.getByRole('textbox').fill('123.5'); await total.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(total.locator('.review-badge')).toHaveText('edited');
        const before = await (await context.request.get(`${root}/report`)).body();
        // The UI does not offer replacement extraction after review. Exercise that
        // API path explicitly, then download the unchanged human-reviewed result.
        for (const name of ['duplicate-value', 'unknown-claim', 'unknown-row', 'unpaired-surrogate']) {
          const response = await context.request.post(`${root}/extract`, { multipart: {
            schema: 'invoice', provider: 'fixture', fixture: { name: `${name}.json`, mimeType: 'application/json', buffer: await readFile(join(args.fixtures, `${name}.json`)) },
          } });
          assert.equal(response.status(), 422);
          assert.deepEqual(await (await context.request.get(`${root}/report`)).body(), before);
          attempts.push({ fixture: name, via: 'direct HTTP replacement after review', status: 422, priorReportUnchanged: true });
        }
        await expect(total.locator('.field-value')).toHaveText('123.50');
        const downloadPending = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
        const download = await downloadPending, chunks = [];
        for await (const chunk of await download.createReadStream()) chunks.push(chunk);
        const exported = Buffer.concat(chunks), parsed = JSON.parse(exported);
        assert.deepEqual(parsed, await (await context.request.get(`${root}/export.json?scope=reviewed`)).json());
        await writeFile(join(args.output, `${engine}-${width}-export.json`), exported);
        await page.evaluate(() => document.fonts.ready);
        await expect(page.locator('.toast')).toHaveCSS('opacity', '0');
        await page.screenshot({ path: join(args.output, `${engine}-${width}-review.png`), fullPage: true });
        const violations = (await new AxeBuilder({ page }).analyze()).violations;
        assert.equal(violations.length, 0); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await Promise.all(pending); assert.deepEqual(errors, []); assert.deepEqual(external, []);
        assert.deepEqual(await page.evaluate(() => window.cspErrors), []);
        records.push({ engine, version: browser.version(), width, attempts, export: { bytes: exported.length, sha256: sha(exported) }, validRetry: true,
          pageErrors: errors, externalRequests: external, cspViolations: [], axeViolations: 0, overflow: false, assets });
        console.log(`${engine} ${width}: rejected four malformed imports, retained edit/export, valid retry succeeded`);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(join(args.output, 'browser.json'), JSON.stringify({ records }, null, 2) + '\n');
