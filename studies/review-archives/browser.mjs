import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { parseArgs } from 'node:util';

const { values: args } = parseArgs({ options: Object.fromEntries(
  ['url', 'phase', 'source', 'tools', 'static', 'output'].map(name => [name, { type: 'string' }]),
) });
args.url = new URL(args.url).href;
const require = createRequire(join(args.tools, 'package.json'));
const { chromium, firefox, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const row = (page, path) => page.locator('.field-row').filter({ has: page.getByRole('button', { name: `Inspect ${path}`, exact: true }) });
const observations = [];
const saved = args.phase === 'restore' ? JSON.parse(await readFile(join(args.output, 'save.json'))) : null;

async function downloaded(page, name) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name, exact: true }).click();
  const download = await pending;
  const chunks = [];
  for await (const chunk of await download.createReadStream()) chunks.push(chunk);
  return Buffer.concat(chunks);
}

for (const [engine, driver] of Object.entries({ chromium, firefox })) {
  const browser = await driver.launch();
  try {
    for (const width of [1440, 375]) {
      const id = `${engine}-${width}`;
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: width === 1440 ? 'dark' : 'light' });
      const page = await context.newPage();
      const errors = [], external = [], assets = new Map(), reads = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        window.cspErrors = [];
        addEventListener('securitypolicyviolation', event => window.cspErrors.push(event.violatedDirective));
      });
      await context.route('**/*', route => {
        if (new URL(route.request().url()).origin !== new URL(args.url).origin) {
          external.push(route.request().url());
          return route.abort();
        }
        return route.continue();
      });
      page.on('response', response => {
        const path = new URL(response.url()).pathname;
        if (response.status() === 200 && (path === '/' || path.startsWith('/assets/'))) {
          reads.push(response.body().then(async bytes => {
            const relative = path === '/' ? 'index.html' : path.slice(1);
            const expected = await readFile(join(args.static, relative));
            assert.equal(sha(bytes), sha(expected), `Served asset differs: ${relative}`);
            assets.set(relative, { bytes: bytes.length, sha256: sha(bytes) });
          }));
        }
      });
      await page.goto(args.url);
      let originalId;
      if (args.phase === 'save') {
        await page.getByLabel('PDF document', { exact: true }).setInputFiles(join(args.source, 'examples/invoice.pdf'));
        await expect(page.getByRole('button', { name: 'Run extraction', exact: true })).toBeVisible();
        await page.getByLabel('Fixture JSON', { exact: true }).setInputFiles(join(args.source, 'examples/fixtures/invoice.json'));
        await page.getByRole('button', { name: 'Run extraction', exact: true }).click();
        await expect(row(page, 'total')).toBeVisible();
        for (const [path, value] of [['invoice_number', '00042'], ['total', '123.5']]) {
          const field = row(page, path);
          await field.getByRole('button', { name: 'Edit', exact: true }).click();
          await field.getByRole('textbox').fill(value);
          await field.getByRole('button', { name: 'Save', exact: true }).click();
          await expect(field.locator('.review-badge')).toHaveText('edited');
        }
        await row(page, 'vendor_name').getByRole('button', { name: 'Approve', exact: true }).click();
        await row(page, 'po_number').getByRole('button', { name: 'Reject', exact: true }).click();
        await expect(row(page, 'po_number').locator('.review-badge')).toHaveText('rejected');
      } else {
        const prior = saved.cases.find(item => item.id === id);
        originalId = prior.document_id;
        assert.equal((await context.request.get(`${args.url}api/documents/${originalId}/report`)).status(), 404);
        await page.getByLabel('Review archive', { exact: true }).setInputFiles(join(args.output, `${id}.zip`));
        await expect(row(page, 'total').locator('.field-value')).toHaveText('123.50');
        await expect(page.getByText('Opened from a review archive.', { exact: false })).toBeVisible();
        await expect(row(page, 'invoice_number').locator('.field-value')).toHaveText('00042');
      }
      const documents = (await (await context.request.get(`${args.url}api/documents`)).json()).documents;
      const document = documents.at(-1);
      assert.ok(document && document.id !== originalId);
      const root = `${args.url}api/documents/${document.id}`;
      const report = await (await context.request.get(`${root}/report`)).json();
      const reportBytes = Buffer.from(JSON.stringify(report));
      const exported = {};
      for (const ext of ['json', 'csv', 'xlsx']) {
        const bytes = await downloaded(page, `Export ${ext.toUpperCase()}`);
        if (ext === 'json') assert.deepEqual(JSON.parse(bytes), await (await context.request.get(`${root}/export.json?scope=reviewed`)).json());
        exported[ext] = { bytes: bytes.length, sha256: sha(bytes) };
        await writeFile(join(args.output, `${args.phase}-${id}.${ext}`), bytes);
      }
      const archive = await downloaded(page, 'Save archive');
      if (args.phase === 'save') await writeFile(join(args.output, `${id}.zip`), archive);
      else assert.deepEqual(archive, await readFile(join(args.output, `${id}.zip`)));
      await row(page, 'total').getByRole('button', { name: 'Inspect total', exact: true }).click();
      await expect(page.locator('.highlight-rect[data-path="total"]').first()).toBeVisible();
      const image = page.locator('#page-frame img');
      await expect(image).toBeVisible();
      await image.evaluate(element => element.decode());
      const pageBytes = await (await context.request.get(`${root}/pages/1.png`)).body();
      if (width === 375) await page.getByRole('button', { name: 'Fields', exact: true }).click();
      await row(page, 'total').scrollIntoViewIfNeeded();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('.toast')).toHaveCSS('opacity', '0');
      await scan(page);
      if (args.phase === 'restore') await page.screenshot({ path: join(args.output, `${id}.png`), fullPage: true });
      await Promise.all(reads);
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      assert.deepEqual(await page.evaluate(() => window.cspErrors), []);
      const record = { id, browser: browser.version(), document_id: document.id,
        report_sha256: sha(reportBytes), page_sha256: sha(pageBytes), archive_sha256: sha(archive),
        archive_bytes: archive.length, exports: exported, assets: Object.fromEntries(assets),
        page_errors: errors, external_requests: external, csp_errors: [], axe_violations: [], overflow: false };
      if (args.phase === 'restore') {
        const prior = saved.cases.find(item => item.id === id);
        for (const key of ['report_sha256', 'page_sha256', 'archive_sha256', 'archive_bytes', 'exports']) {
          assert.deepEqual(record[key], prior[key], `${id} ${key} changed across restart`);
        }
        record.restored_after_server_restart = true;
      }
      observations.push(record);
      await context.close();
    }
  } finally { await browser.close(); }
}
await writeFile(join(args.output, `${args.phase}.json`), JSON.stringify({ cases: observations }, null, 2) + '\n');
console.log(`${args.phase}: ${observations.length} actual browser workflows passed`);

async function scan(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const report = await new AxeBuilder({ page }).analyze();
  if (report.violations.length) await page.screenshot({ path: join(args.output, 'accessibility-failure.png'), fullPage: true });
  assert.deepEqual(report.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), []);
}
