// Capture the retained old installed wheel against the new, authored fixture.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire(new URL('../../web/package.json', import.meta.url));
const { chromium, firefox, expect } = require('@playwright/test');
const destination = fileURLToPath(new URL('../../docs/assets/native-glyph-bounds/', import.meta.url));
mkdirSync(destination, { recursive: true });
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch();
  try {
    const page = await browser.newPage({ baseURL: process.env.FIELDPROOF_BASELINE_URL || 'http://127.0.0.1:4471/', viewport: { width: 1440, height: 960 } });
    await page.goto('./');
    await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('fixtures/Helvetica-Oblique-16-4.pdf', import.meta.url)));
    await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
    await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('fixture.json', import.meta.url)));
    await page.getByRole('button', { name: 'Run extraction' }).click();
    const total = page.locator('.field-row').filter({ has: page.getByRole('button', { name: 'Inspect total', exact: true }) });
    await expect(total.locator('.status-chip')).toHaveAttribute('data-status', 'verified');
    await total.getByRole('button', { name: 'Inspect total', exact: true }).click();
    await expect.poll(() => page.locator('#page-frame img').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
    await page.screenshot({ path: `${destination}/before-${name}-1440.png`, fullPage: true });
    const listing = await (await page.request.get('/api/documents')).json();
    const entry = listing.documents[0];
    const report = await (await page.request.get(`/api/documents/${entry.id}/report`)).json();
    writeFileSync(fileURLToPath(new URL(`results/before-${name}-browser.json`, import.meta.url)), JSON.stringify({ baseline: '61e47c3 runtime, retained installed wheel', field: report.report.fields.find(field => field.path === 'total') }, null, 2) + '\n');
    for (const document of listing.documents) await page.request.delete(`/api/documents/${document.id}`);
  } finally {
    await browser.close();
  }
}
