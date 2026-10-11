// Real upload, review, PDF rendering and exported decisions from a local server.
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
const [base, phase, destination] = process.argv.slice(2);
assert(['before', 'after'].includes(phase));
await mkdir(destination, { recursive: true });
const observations = [];
for (const [engine, browserType] of Object.entries(phase === 'before' ? { chromium } : { chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of phase === 'before' ? [1440] : [1440, 375]) {
      for (const id of width === 1440 && phase === 'after' ? ['repeated-name', 'complete-expanded-word'] : ['repeated-name']) {
        const context = await browser.newContext({ viewport: { width, height: 960 }, colorScheme: width === 1440 ? 'dark' : 'light' });
        const errors = [], external = [];
        let documentId;
        try {
          await context.route('**/*', async route => {
            const url = route.request().url();
            if (/^https?:/.test(url) && new URL(url).origin !== new URL(base).origin) {
              external.push(url); await route.abort();
            } else await route.continue();
          });
          const page = await context.newPage();
          page.on('pageerror', error => errors.push(error.message));
          await page.addInitScript(() => {
            window.evidenceCsp = [];
            addEventListener('securitypolicyviolation', event => window.evidenceCsp.push(event.violatedDirective));
          });
          await page.goto(base);
          const uploadPromise = page.waitForResponse(r => r.url().endsWith('/api/documents') && r.request().method() === 'POST');
          await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL(`fixtures/${id}.pdf`, import.meta.url)));
          const uploaded = await uploadPromise;
          assert.equal(uploaded.status(), 200);
          documentId = (await uploaded.json()).id;
          await page.locator('#schema-select').selectOption('receipt');
          await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL(`fixtures/${id}.json`, import.meta.url)));
          const extractionPromise = page.waitForResponse(r => r.url().endsWith('/extract'));
          await page.getByRole('button', { name: 'Run extraction' }).click();
          const extraction = await extractionPromise;
          assert.equal(extraction.status(), 200);
          const result = await extraction.json();
          const merchant = result.report.fields.find(f => f.path === 'merchant_name');
          const status = phase === 'after' && id === 'repeated-name' ? 'needs_review' : 'verified';
          assert.equal(merchant.status, status);
          const search = page.getByRole('searchbox', { name: 'Search fields' });
          await expect(search).toBeAttached();
          if (!await search.isVisible()) await page.getByRole('button', { name: 'Filters', exact: true }).click();
          await search.fill('merchant_name');
          const row = page.locator('.field-row');
          await expect(row).toHaveCount(1);
          await expect(row.locator('.status-chip')).toHaveAttribute('data-status', status);
          if (status === 'needs_review') {
            assert.deepEqual(merchant.rects, []);
            await expect(row.locator('.field-reasons')).toContainText('ambiguous (appears 2 times)');
          } else {
            await row.getByRole('button', { name: 'Inspect merchant_name', exact: true }).click();
            await expect(page.locator('.highlight-rect[data-path="merchant_name"]')).toBeVisible();
            assert.equal(merchant.matched_text, id === 'complete-expanded-word' ? 'Straße' : 'Acme');
          }
          if (width === 1440) await expect.poll(() => page.locator('#page-frame img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
          const screenshot = `${engine}-${width}-${id}-${phase}.png`;
          await page.screenshot({ path: resolve(destination, screenshot) });
          await row.getByRole('button', { name: 'Approve', exact: true }).click();
          const downloadPromise = page.waitForEvent('download');
          await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
          const download = await downloadPromise;
          const stream = await download.createReadStream();
          const chunks = []; for await (const chunk of stream) chunks.push(chunk);
          const exported = JSON.parse(Buffer.concat(chunks).toString());
          assert.equal(exported.length, 1);
          assert.equal(exported[0].field, 'merchant_name');
          assert.equal(exported[0].verification_status, status);
          assert.equal(exported[0].review_status, 'approved');
          assert.deepEqual((await (await context.request.get(`${base}api/documents/${documentId}/report`)).json()).report, result.report);
          const accessibility = (await new AxeBuilder({ page }).analyze()).violations.map(v => v.id);
          const csp = await page.evaluate(() => window.evidenceCsp);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          for (const findings of [errors, external, accessibility, csp]) assert.deepEqual(findings, []);
          observations.push({ engine, version: browser.version(), width, id, merchant, exported,
            errors, external, accessibility, csp, screenshot,
            screenshot_sha256: createHash('sha256').update(await readFile(resolve(destination, screenshot))).digest('hex') });
        } finally {
          if (documentId) assert.equal((await context.request.delete(`${base}api/documents/${documentId}`)).status(), 204);
          await context.close();
        }
      }
    }
  } finally { await browser.close(); }
}
await writeFile(resolve(destination, 'browser.json'), JSON.stringify(observations, null, 2) + '\n');
