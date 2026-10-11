// Exercise the actual local review server; fixtures are synthetic, no model calls.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../web/package.json', import.meta.url));
const { chromium, firefox } = require('playwright');
const { expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const [baseURL, outcome, output] = process.argv.slice(2);
assert(['rejected', 'accepted'].includes(outcome));
const destination = resolve(output);
await mkdir(destination, { recursive: true });
const fixture = fileURLToPath(new URL('fixtures/rows-100.json', import.meta.url));
const pdf = fileURLToPath(new URL('fixtures/rows-100.pdf', import.meta.url));
const origin = new URL(baseURL).origin;
const receipt = [];
for (const [engine, browserType] of Object.entries(outcome === 'rejected' ? { chromium } : { chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of outcome === 'rejected' ? [1440] : [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 960 },
        colorScheme: width === 1440 ? 'dark' : 'light' });
      const errors = [], external = [], csp = [];
      let documentId;
      try {
        await context.route('**/*', async route => {
          const url = route.request().url();
          if (/^https?:/.test(url) && new URL(url).origin !== origin) {
            external.push(url);
            await route.abort();
          } else await route.continue();
        });
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
          window.evidenceCsp = [];
          addEventListener('securitypolicyviolation', event => window.evidenceCsp.push(event.violatedDirective));
        });
        await page.goto(baseURL);
        const uploadResponse = page.waitForResponse(response => response.url().endsWith('/api/documents')
          && response.request().method() === 'POST');
        await page.getByLabel('PDF document').setInputFiles(pdf);
        const upload = await uploadResponse;
        assert.equal(upload.status(), 200);
        documentId = (await upload.json()).id;
        await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
        await page.getByLabel('Fixture JSON').setInputFiles(fixture);
        const responsePromise = page.waitForResponse(response => response.url().endsWith('/extract'), { timeout: 40000 });
        const start = performance.now();
        await page.getByRole('button', { name: 'Run extraction' }).click();
        const response = await responsePromise;
        const elapsed = (performance.now() - start) / 1000;
        const body = await response.json();
        const screenshots = [];
        let exported = null, reportSha256 = null;
        if (outcome === 'rejected') {
          assert.equal(response.status(), 413);
          await expect(page.getByText('PDF worker exceeded its resource budget', { exact: false })).toBeVisible();
          const name = `${engine}-${width}-rejected.png`;
          await page.screenshot({ path: resolve(destination, name) });
          screenshots.push(name);
        } else {
          assert.equal(response.status(), 200);
          assert.deepEqual(body.report.counts, { verified: 201, needs_review: 203, unsupported: 0 });
          assert.equal(body.report.fields.length, 404);
          reportSha256 = createHash('sha256').update(JSON.stringify(body.report)).digest('hex');
          const search = page.getByRole('searchbox', { name: 'Search fields' });
          await expect(search).toBeAttached();
          if (!await search.isVisible()) await page.getByRole('button', { name: 'Filters', exact: true }).click();
          await search.fill('line_items[99].quantity');
          const row = page.locator('.field-row');
          await expect(row).toHaveCount(1);
          await expect(row.locator('.status-chip')).toHaveAttribute('data-status', 'verified');
          await row.getByRole('button', { name: 'Inspect line_items[99].quantity', exact: true }).click();
          const highlight = page.locator('.highlight-rect[data-path="line_items[99].quantity"]');
          await expect(highlight).toBeVisible();
          await expect(page.locator('#page-frame img')).toHaveAttribute('src', /\/pages\/2\.png$/);
          await expect.poll(() => page.locator('#page-frame img').evaluate(image => image.complete && image.naturalWidth > 0),
            { timeout: 35000 }).toBe(true);
          await highlight.scrollIntoViewIfNeeded();
          const name = `${engine}-${width}-evidence.png`;
          await page.screenshot({ path: resolve(destination, name) });
          screenshots.push(name);
          if (width === 375) await page.getByRole('button', { name: 'Fields', exact: true }).click();
          await row.getByRole('button', { name: 'Approve', exact: true }).click();
          const downloadPromise = page.waitForEvent('download');
          await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
          const download = await downloadPromise;
          const stream = await download.createReadStream();
          const chunks = [];
          for await (const chunk of stream) chunks.push(chunk);
          exported = JSON.parse(Buffer.concat(chunks).toString());
          assert.equal(exported.length, 1);
          assert.equal(exported[0].field, 'line_items[99].quantity');
          assert.equal(exported[0].value, 1);
          assert.equal(exported[0].verification_status, 'verified');
          await search.fill('line_items[99].amount');
          await expect(row).toHaveCount(1);
          await expect(row.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
          await expect(row.locator('.field-reasons')).toContainText('ambiguous (appears 200 times)');
          if (width === 375) {
            const name = `${engine}-${width}-review.png`;
            await page.screenshot({ path: resolve(destination, name) });
            screenshots.push(name);
          }
          const after = await (await context.request.get(`${baseURL}api/documents/${documentId}/report`)).json();
          assert.deepEqual(after.report, body.report);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        }
        const violations = (await new AxeBuilder({ page }).analyze()).violations.map(item => item.id);
        csp.push(...await page.evaluate(() => window.evidenceCsp));
        assert.deepEqual(violations, []);
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
        assert.deepEqual(csp, []);
        receipt.push({ engine, version: browser.version(), width, outcome,
          status: response.status(), seconds: elapsed, reportSha256, exported,
          errors, externalRequests: external, cspViolations: csp, accessibilityViolations: violations,
          screenshots: await Promise.all(screenshots.map(async file => ({ file,
            sha256: createHash('sha256').update(await readFile(resolve(destination, file))).digest('hex') }))) });
      } finally {
        if (documentId) assert.equal((await context.request.delete(`${baseURL}api/documents/${documentId}`)).status(), 204);
        await context.close();
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(destination, 'browser.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log(`Checked ${receipt.length} actual-server browser workflows (${outcome}).`);
