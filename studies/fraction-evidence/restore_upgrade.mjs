// Restore an actual archive saved by the baseline server into the corrected UI.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const [baseURL, destination] = process.argv.slice(2);
assert(baseURL && destination, 'Use restore_upgrade.mjs URL OUTPUT');
const output = resolve(destination);
await mkdir(output, { recursive: true });
const archive = fileURLToPath(new URL('fixtures/before-review.zip', import.meta.url));
const bytes = await readFile(archive), records = [];
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  for (const width of [1440, 375]) {
    const context = await browser.newContext({ viewport: { width, height: 960 }, acceptDownloads: true });
    const page = await context.newPage(), errors = [], outside = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (new URL(r.url()).origin !== new URL(baseURL).origin) outside.push(r.url()); });
    await page.goto(baseURL);
    await page.getByLabel('Review archive', { exact: true }).setInputFiles(archive);
    const row = page.locator('.field-row').filter({ has: page.getByRole('button', { name: 'Inspect line_items[0].quantity', exact: true }) });
    await row.locator('.review-badge').getByText('edited', { exact: true }).waitFor();
    assert.equal(await row.locator('.status-chip').getAttribute('data-status'), 'needs_review');
    const documents = (await (await context.request.get(new URL('/api/documents', baseURL).href)).json()).documents;
    assert.equal(documents.length, 1);
    const id = documents[0].id;
    const report = await (await context.request.get(new URL(`/api/documents/${id}/report`, baseURL).href)).json();
    assert.deepEqual(report.report.counts, { verified: 6, needs_review: 1, unsupported: 0 });
    const original = report.report.fields.find(f => f.path === 'line_items[0].quantity');
    assert.equal(original.value, 1); assert.equal(original.matched_text, 'Quantity 1⁄2 m');
    assert.equal(original.status, 'needs_review');
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
    const path = join(output, `${name}-${width}.json`);
    await (await pending).saveAs(path);
    const downloaded = JSON.parse(await readFile(path, 'utf8'));
    assert.equal(downloaded.length, 1);
    assert.equal(downloaded[0].value, .5); assert.equal(downloaded[0].original_value, 1);
    assert.equal(downloaded[0].verification_status, 'needs_review');
    assert.equal(downloaded[0].review_status, 'edited');
    assert.equal(downloaded[0].value_source, 'correction');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    if ((name === 'chromium' && width === 1440) || (name === 'firefox' && width === 375)) {
      await page.screenshot({ path: join(output, `${name}-${width}.png`), fullPage: true });
    }
    assert.deepEqual(errors, []); assert.deepEqual(outside, []);
    records.push({ browser: name, version: browser.version(), width, input_archive: 'before-review.zip',
      source_automated_status: 'verified', restored_automated_status: original.status,
      original_value: 1, retained_correction: .5, review_status: 'edited',
      downloaded_json: downloaded, errors, off_origin_requests: outside });
    assert.equal((await context.request.delete(new URL(`/api/documents/${id}`, baseURL).href)).status(), 204);
    await context.close();
  }
  await browser.close();
}
await writeFile(join(output, 'upgrade.json'), JSON.stringify({ archive_sha256: createHash('sha256').update(bytes).digest('hex'),
  workflows: records }, null, 2) + '\n');
console.log(JSON.stringify({ workflows: records.length, actual_json_downloads: records.length }));
