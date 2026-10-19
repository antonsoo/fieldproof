// Exercise an installed server and its bundled UI; write only retained evidence.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../web/package.json', import.meta.url));
const { chromium, firefox } = require('playwright');
const { unzipSync } = require('fflate');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const study = fileURLToPath(new URL('./', import.meta.url));
const source = resolve(study, 'fixtures/covered-native-total.pdf');
const fixture = resolve(study, 'claim.json');
const [baseURL, output, expectedPNG] = process.argv.slice(2);
assert(baseURL && output && expectedPNG, 'usage: node browser.mjs BASE_URL OUTPUT EXPECTED_REVIEW_PNG');
await mkdir(output, { recursive: true });
const expectedHash = sha(await readFile(expectedPNG));
const receipts = [];
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  try {
    const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 960 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [], external = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).origin !== new URL(baseURL).origin) external.push(request.url());
    });
    await page.goto(baseURL);
    await page.getByLabel('PDF document').setInputFiles(source);
    await page.getByRole('button', { name: 'Run extraction', exact: true }).waitFor();
    await page.getByLabel('Fixture JSON').setInputFiles(fixture);
    await page.getByRole('button', { name: 'Run extraction', exact: true }).click();
    const total = page.locator('.field-row').filter({ has: page.getByRole('button', { name: 'Inspect total', exact: true }) });
    await total.waitFor();
    assert.equal(await total.locator('.status-chip').getAttribute('data-status'), 'needs_review');
    await total.getByRole('button', { name: 'Inspect total', exact: true }).click();
    await page.waitForFunction(() => {
      const image = document.querySelector('#page-frame img');
      return image?.complete && image.naturalWidth > 0;
    });
    const listing = await (await context.request.get(new URL('/api/documents', baseURL).href)).json();
    assert.equal(listing.documents.length, 1);
    const id = listing.documents[0].id;
    const report = await (await context.request.get(new URL(`/api/documents/${id}/report`, baseURL).href)).json();
    assert.deepEqual(report.report.counts, { verified: 3, needs_review: 1, unsupported: 0 });
    const image = await context.request.get(await page.locator('#page-frame img').getAttribute('src'));
    const imageHash = sha(await image.body());
    assert.equal(imageHash, expectedHash);
    const screenshots = [];
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 960 });
      if (width === 375) await page.getByRole('button', { name: 'Document', exact: true }).click();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const path = resolve(output, `${name}-${width}.png`);
      await page.screenshot({ path, fullPage: true });
      screenshots.push({ width, file: `${name}-${width}.png`, sha256: sha(await readFile(path)) });
    }
    await page.setViewportSize({ width: 1440, height: 960 });
    await total.getByRole('button', { name: 'Edit', exact: true }).click();
    await total.getByRole('textbox').fill('100');
    await total.getByRole('button', { name: 'Save', exact: true }).click();
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
    const exported = JSON.parse(await readFile(await (await downloadEvent).path(), 'utf8'));
    assert.deepEqual(exported, [{ field: 'total', value: 100, original_value: 900,
      value_source: 'correction', verification_status: 'needs_review', review_status: 'edited', page: 1 }]);
    const archiveEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Save archive', exact: true }).click();
    const archivePath = await (await archiveEvent).path();
    const archive = await readFile(archivePath);
    const members = unzipSync(archive);
    const retainedPDF = Object.entries(members).find(([path]) => path.endsWith('.pdf'));
    assert(retainedPDF);
    assert.equal(sha(retainedPDF[1]), sha(await readFile(source)));
    assert.equal((await context.request.delete(new URL(`/api/documents/${id}`, baseURL).href)).status(), 204);
    await page.reload();
    await page.getByLabel('Review archive', { exact: true }).setInputFiles(archivePath);
    await page.getByRole('button', { name: 'Inspect total', exact: true }).waitFor();
    const restored = (await (await context.request.get(new URL('/api/documents', baseURL).href)).json()).documents[0];
    const restoredReport = await (await context.request.get(new URL(`/api/documents/${restored.id}/report`, baseURL).href)).json();
    assert.deepEqual(restoredReport.report, report.report);
    assert.equal(await total.locator('.field-value').textContent(), '100.00');
    const restoredImage = await context.request.get(new URL(`/api/documents/${restored.id}/pages/1.png`, baseURL).href);
    assert.equal(sha(await restoredImage.body()), expectedHash);
    assert.equal((await context.request.delete(new URL(`/api/documents/${restored.id}`, baseURL).href)).status(), 204);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    receipts.push({ browser: name, browser_version: browser.version(), source_sha256: sha(await readFile(source)),
      review_png_sha256: imageHash, screenshots, original_report: report.report, exported,
      archive_sha256: sha(archive), archive_source_unchanged: true, restored_report_equal: true,
      restored_review_png_equal: true, errors, external });
    await context.close();
  } finally {
    await browser.close();
  }
}
await writeFile(resolve(output, 'browser.json'), JSON.stringify(receipts, null, 2) + '\n');
process.stdout.write(JSON.stringify({ browsers: receipts.map(item => item.browser),
  screenshots: receipts.reduce((sum, item) => sum + item.screenshots.length, 0),
  corrected_value: 100, original_value: 900, automated_status: 'needs_review' }) + '\n');
