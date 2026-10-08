// Run against the locally installed wheel's review server at :4294. Uses the
// actual upload, fixture extraction, PDF rendering, review and download paths.
import { chromium, firefox, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);
const pdf = fileURLToPath(new URL('examples/signed-amount.pdf', root));
const fixture = fileURLToPath(new URL('examples/fixtures/signed-amount.json', root));
const assets = fileURLToPath(new URL('docs/assets/', root));
const base = process.env.NUMERIC_REVIEW_URL ?? 'http://127.0.0.1:4294/';
const evidence = [];
await mkdir(assets, { recursive: true });

for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: width === 375 ? 812 : 960 } });
      const page = await context.newPage();
      const errors = [], external = [], scans = [];
      page.on('pageerror', error => errors.push(String(error)));
      page.on('request', request => {
        if (new URL(request.url()).origin !== new URL(base).origin) external.push(request.url());
      });
      const scan = async () => {
        const result = await new AxeBuilder({ page }).analyze();
        expect(result.violations).toEqual([]);
        scans.push({ rules: result.passes.length, violations: 0 });
      };
      await page.goto(base, { waitUntil: 'domcontentloaded' });
      await page.getByLabel('PDF document').setInputFiles(pdf);
      await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
      await page.getByLabel('Fixture JSON').setInputFiles(fixture);
      await page.getByRole('button', { name: 'Run extraction' }).click();
      const field = page.locator('.field-row[data-path="total"]');
      await expect(field.locator('.status-chip')).toHaveText('needs review');
      await expect(field.locator('.field-evidence')).toContainText('- $100.00');
      await expect(field.locator('.field-reasons')).toContainText('does not match -100');
      if (width === 375) await page.getByRole('button', { name: 'Filters', exact: true }).click();
      await page.getByRole('button', { name: 'Needs review 1', exact: true }).click();
      if (width === 375) await page.getByRole('button', { name: 'Filters', exact: true }).click();
      const image = page.locator('#page-frame img');
      const documentUrl = (await image.getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
      await expect(image).toHaveJSProperty('complete', true);
      expect(await image.evaluate(el => el.naturalWidth)).toBeGreaterThan(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await scan();
      const capture = `${assets}/numeric-${name}-${width}.png`;
      await page.screenshot({ path: capture, fullPage: true });
      if (width === 375) {
        await page.getByRole('button', { name: 'Inspect total', exact: true }).click();
        await expect(page.locator('.highlight-rect[data-path="total"]')).toBeVisible();
        await scan();
        if (name === 'chromium') await page.screenshot({ path: `${assets}/numeric-mobile-document.png`, fullPage: true });
        await page.getByRole('button', { name: 'Fields', exact: true }).click();
      }
      const reportResponse = await page.request.get(new URL(`${documentUrl}/report`, base).href);
      expect(reportResponse.ok()).toBe(true);
      const originalReport = await reportResponse.json();
      // Make the human correction with the keyboard, then compare a real download
      // with the API export. Its original automated verdict must remain intact.
      await field.getByRole('button', { name: 'Edit', exact: true }).focus();
      await page.keyboard.press('Enter');
      const input = field.getByRole('textbox', { name: 'Correction for total' });
      await expect(input).toBeFocused();
      await input.fill('-100');
      await input.press('Enter');
      await expect(field.locator('.field-value')).toHaveText('-100.00');
      await field.getByRole('button', { name: 'Approve', exact: true }).click();
      await expect(field.locator('.review-badge')).toHaveText('approved');
      const pending = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export JSON' }).click();
      const download = await pending;
      const chunks = [];
      for await (const chunk of await download.createReadStream()) chunks.push(chunk);
      const exported = JSON.parse(Buffer.concat(chunks).toString());
      expect(exported).toEqual([{
        field: 'total', value: -100, original_value: 100, value_source: 'correction',
        verification_status: 'needs_review', review_status: 'approved', page: 1,
      }]);
      const api = await page.request.get(new URL(`${documentUrl}/export.json?scope=reviewed`, base).href);
      expect(await api.json()).toEqual(exported);
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
      evidence.push({ browser: name, version: browser.version(), width, originalReport, exported, scans, errors, external });
      expect((await page.request.delete(new URL(documentUrl, base).href)).status()).toBe(204);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
const sha256 = data => createHash('sha256').update(data).digest('hex');
const result = { pdfSha256: sha256(await readFile(pdf)), fixtureSha256: sha256(await readFile(fixture)), evidence };
await writeFile(new URL('docs/verification-numeric-browser.json', root), JSON.stringify(result, null, 2) + '\n');
console.log(`${evidence.length} installed-wheel browser workflows passed; original signed evidence, keyboard correction and downloads retained.`);
