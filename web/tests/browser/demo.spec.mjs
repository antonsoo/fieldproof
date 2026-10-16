import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

import { row, downloadText, scan, installAudit } from './helpers.mjs';
installAudit(test);

test('the hidden-text sample keeps an invisible amount in review and exports offline', async ({ page, context, browserName }) => {
  await page.goto('./#hidden-text', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Hidden text');
  const total = row(page, 'total');
  await expect(total.locator('.field-value')).toHaveText('900.00');
  await expect(total.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(total.locator('.field-reasons')).toContainText('native-text paint contribution');
  await total.getByRole('button', { name: 'Inspect total', exact: true }).click();
  await expect.poll(() => page.locator('#page-frame img').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
  await context.setOffline(true);
  const requests = [];
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
  for (const width of [1440, 375, 320]) {
    await page.setViewportSize({ width, height: 960 });
    if (width <= 375) await page.getByRole('button', { name: 'Fields', exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_RASTER_SCREENSHOTS) {
      await page.screenshot({ path: fileURLToPath(new URL(`../../../docs/assets/flat-raster/demo-${browserName}-${width}.png`, import.meta.url)), fullPage: true });
    }
  }
  await total.getByRole('button', { name: 'Edit', exact: true }).click();
  await total.getByRole('textbox').fill('90');
  await total.getByRole('button', { name: 'Save', exact: true }).click();
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported).toEqual([expect.objectContaining({ field: 'total', value: 90, original_value: 900, value_source: 'correction', verification_status: 'needs_review' })]);
  expect(requests).toEqual([]);
  await context.setOffline(false);
  await page.reload();
  await expect(row(page, 'total').locator('.field-value')).toHaveText('90.00');
  await expect(row(page, 'total').locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
});

test('the line arithmetic sample exposes the original calculation and exports a correction', async ({ page }) => {
  await page.goto('./#line-arithmetic', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Arithmetic');
  const quantity = row(page, 'line_items[0].quantity');
  await expect(quantity.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(quantity.locator('.field-reasons')).toContainText('59.85');
  await expect(quantity.locator('.field-evidence')).toContainText('Precision bolts 3 19.95 39.90');
  for (const width of [1440, 375, 320]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_ARITHMETIC_SCREENSHOTS) {
      await page.screenshot({ path: fileURLToPath(new URL(`../../../docs/assets/arithmetic/demo-${test.info().project.name}-${width}.png`, import.meta.url)), fullPage: true });
    }
  }
  await quantity.getByRole('button', { name: 'Edit', exact: true }).click();
  await quantity.getByRole('textbox').fill('2');
  await quantity.getByRole('button', { name: 'Save', exact: true }).click();
  await page.reload();
  await expect(row(page, 'line_items[0].quantity').locator('.field-value')).toHaveText('2');
  const downloaded = await downloadText(page, 'JSON');
  expect(downloaded.filename).toBe('line-arithmetic.fieldproof.json');
  expect(JSON.parse(downloaded.text)).toEqual([
    expect.objectContaining({ field: 'line_items[0].quantity', value: 2, original_value: 3, value_source: 'correction' }),
  ]);
});

test('nested numeric correction saves the typed value and approval retains it', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  const field = row(page, 'line_items[0].amount');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.locator('input').fill('321.5');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('321.50');
  await field.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('321.50');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const rows = JSON.parse(Buffer.concat(chunks).toString());
  expect(rows.find(r => r.field === 'line_items[0].amount').value).toBe(321.5);
});

test('a slow earlier sample cannot replace a newer selection', async ({ page }) => {
  let release;
  const delayed = new Promise(resolve => { release = resolve; });
  await page.route('**/receipt/data.json', async route => { await delayed; await route.continue(); });
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(row(page, 'po_number')).toBeVisible();
  await page.getByRole('button', { name: 'Receipt', exact: true }).click();
  await page.getByRole('button', { name: 'Contract', exact: true }).click();
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Contract');
  release();
  await page.waitForTimeout(300);
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Contract');
});

test('page-session review survives sample switches when storage is blocked', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => { throw new DOMException('Blocked', 'SecurityError'); };
    Storage.prototype.getItem = () => { throw new DOMException('Blocked', 'SecurityError'); };
  });
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await row(page, 'po_number').getByRole('button', { name: 'Reject', exact: true }).click();
  await expect(row(page, 'po_number').locator('.review-badge')).toHaveText('rejected');
  await page.getByRole('button', { name: 'Receipt', exact: true }).click();
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Receipt');
  await page.getByRole('button', { name: 'Invoice', exact: true }).click();
  await expect(row(page, 'po_number').locator('.review-badge')).toHaveText('rejected');
});

test('invalid numeric edits remain editable and reset restores the original extraction', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  const field = row(page, 'total');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  const input = field.getByRole('textbox', { name: 'Correction for total' });
  await expect(input).toBeFocused();
  for (const value of ['', 'NaN', '1e309', '$100']) {
    await input.fill(value);
    await input.press('Enter');
    await expect(field.getByRole('alert')).toContainText('finite number');
    await expect(input).toHaveValue(value);
    await expect(input).toBeFocused();
    await expect(field.locator('.field-value')).toHaveText('2,600.00');
  }
  await input.fill('0');
  await input.press('Enter');
  await expect(field.locator('.field-value')).toHaveText('0.00');
  await expect(field.locator('.original-value')).toContainText('2,600.00');
  await expect(field.locator('.field-evidence')).toContainText('2,666.93');
  await field.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('2,600.00');
  await expect(field.locator('.original-value')).toHaveCount(0);
});

test('reviewed export excludes pending and rejected values, all scope remains explicit', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('button', { name: 'Export JSON' })).toBeDisabled();
  await row(page, 'invoice_number').getByRole('button', { name: 'Approve', exact: true }).click();
  await row(page, 'po_number').getByRole('button', { name: 'Reject', exact: true }).click();
  await expect(page.locator('#review-progress')).toContainText('2 of 25 reviewed');
  let download = await downloadText(page, 'JSON');
  expect(download.filename).toBe('invoice.fieldproof.json');
  expect(JSON.parse(download.text).map(row => row.field)).toEqual(['invoice_number']);
  await page.getByLabel('Export', { exact: true }).selectOption('all');
  download = await downloadText(page, 'JSON');
  expect(JSON.parse(download.text)).toHaveLength(24);
  expect(JSON.parse(download.text).some(row => row.field === 'po_number')).toBe(false);
  await page.getByLabel('Show', { exact: true }).selectOption('pending');
  await expect(page.locator('.field-row')).toHaveCount(23);
});

test('stored invalid overlays are ignored and valid corrections survive a reload', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('fieldproof-demo-review:invoice', JSON.stringify({
    total: { status: 'edited', edited_value: '' },
    tax: { status: ['approved'], edited_value: null },
    vendor_name: { status: 'approved', edited_value: 'Corrected vendor' },
    unknown: { status: 'edited', edited_value: 'injected' },
  })));
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(row(page, 'total').locator('.field-value')).toHaveText('2,600.00');
  await expect(row(page, 'tax').locator('.review-badge')).toHaveCount(0);
  const download = await downloadText(page, 'JSON');
  expect(JSON.parse(download.text).map(row => row.field)).toEqual(['vendor_name']);
  await expect(row(page, 'vendor_name').locator('.field-value')).toHaveText('Corrected vendor');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(row(page, 'vendor_name').locator('.field-value')).toHaveText('Corrected vendor');
});

test('sample and index failures have retry, and failed replacement preserves the previous review', async ({ page }) => {
  let failIndex = true;
  let failSample = true;
  await page.route('**/demo-data/index.json', route => failIndex ? route.fulfill({ status: 503, json: { detail: 'Unavailable index' } }) : route.continue());
  await page.route('**/receipt/data.json', route => failSample ? route.fulfill({ status: 503, json: { detail: 'Unavailable sample' } }) : route.continue());
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('Unavailable index');
  failIndex = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await row(page, 'po_number').getByRole('button', { name: 'Reject', exact: true }).click();
  await page.getByRole('button', { name: 'Receipt', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Unavailable sample');
  await expect(row(page, 'po_number').locator('.review-badge')).toHaveText('rejected');
  failSample = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Receipt');
});

test('keyboard navigation retains focus through selection, decisions, filters and editing', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  const inspect = page.getByRole('button', { name: 'Inspect po_number', exact: true });
  await inspect.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('button', { name: 'Inspect subtotal', exact: true })).toBeFocused();
  const approve = row(page, 'subtotal').getByRole('button', { name: 'Approve', exact: true });
  await approve.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Inspect subtotal', exact: true })).toBeFocused();
  await page.keyboard.press('a');
  await expect(row(page, 'subtotal').locator('.review-badge')).toHaveText('approved');
  await expect(page.getByRole('button', { name: 'Inspect subtotal', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  const focused = await page.locator('[data-select]:focus').getAttribute('data-select');
  expect(focused).not.toBe('subtotal');
  const filter = page.getByRole('button', { name: 'Needs review 3', exact: true });
  await filter.click();
  await expect(filter).toBeFocused();
  await expect(filter).toHaveAttribute('aria-pressed', 'true');
  const field = row(page, 'total');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').press('Escape');
  await expect(page.getByRole('button', { name: 'Inspect total', exact: true })).toBeFocused();
});

test('desktop and phone review, fit, edit and themes have accessible bounded layouts', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(row(page, 'po_number')).toBeVisible();
  for (const [width, height] of [[1440, 900], [375, 812], [320, 568]]) {
    await page.setViewportSize({ width, height });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => document.documentElement.setAttribute('data-theme', theme), theme);
      await scan(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await page.locator('#field-list').evaluate(list => list.clientHeight > 70 && list.getBoundingClientRect().bottom <= innerHeight + 1)).toBe(true);
      if (width < 860) {
        await expect(page.getByRole('button', { name: 'Fields', exact: true })).toHaveAttribute('aria-pressed', 'true');
        expect(await page.locator('#field-list').evaluate(list => list.clientHeight > 180)).toBe(true);
        await page.getByRole('button', { name: 'Document', exact: true }).click();
        await scan(page);
        await expect(page.locator('.field-pane')).toBeHidden();
      }
      expect(await page.locator('#page-frame').evaluate(frame => frame.offsetWidth <= frame.parentElement.clientWidth - 40)).toBe(true);
      if (width < 860) await page.getByRole('button', { name: 'Fields', exact: true }).click();
    }
  }
  await row(page, 'total').getByRole('button', { name: 'Edit', exact: true }).click();
  await scan(page);
  await page.getByRole('button', { name: 'Document', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Fit', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Fit', exact: true })).toBeFocused();
});

test('phone inspection opens the matching page and returns to the field and its draft', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('./#contract', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Inspect key_obligations[0]', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Document', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.viewer-toolbar')).toContainText('Page 2 / 2');
  await expect(page.locator('.mobile-views')).toContainText('Evidence: key_obligations[0]');
  await page.getByRole('button', { name: 'Fields', exact: true }).click();
  const field = row(page, 'key_obligations[0]');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('draft correction');
  await page.getByRole('button', { name: 'Document', exact: true }).click();
  await page.getByRole('button', { name: 'Fields', exact: true }).click();
  await expect(field.getByRole('textbox')).toHaveValue('draft correction');
});

test('page image failure exposes retry without losing field evidence', async ({ page }) => {
  let fail = true;
  await page.route('**/invoice/page-1.png', route => fail ? route.fulfill({ status: 503, body: '' }) : route.continue());
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('Page image could not load');
  await expect(row(page, 'total').locator('.field-evidence')).toContainText('2,666.93');
  fail = false;
  await page.getByRole('button', { name: 'Retry page image' }).click();
  await expect(page.locator('.page-image-error')).toHaveCount(0);
  await expect.poll(() => page.locator('#page-frame img').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
});

test('damaged replacement reports preserve the original document and decision', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await row(page, 'po_number').getByRole('button', { name: 'Reject', exact: true }).click();
  await page.route('**/receipt/data.json', route => route.fulfill({ json: { document: { id: 'receipt' }, extraction: null } }));
  await page.getByRole('button', { name: 'Receipt', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid document summary');
  await expect(row(page, 'po_number').locator('.review-badge')).toHaveText('rejected');
  await expect(page.locator('.sample-switch .is-active')).toHaveText('Invoice');
});

test('boolean corrections remain false and markup-like corrections are inert in the UI and files', async ({ page }) => {
  await page.route('**/invoice/data.json', async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.extraction.report.fields.push({ path: 'approved', value: true, status: 'verified', reasons: [], matched_text: 'approved', match_score: 100, page: null, rects: [] });
    data.extraction.report.fields.push({ path: 'amount', value: '00034', status: 'verified', reasons: [], matched_text: '00034', match_score: 100, page: null, rects: [] });
    await route.fulfill({ json: data });
  });
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(row(page, 'amount').locator('.field-value')).toHaveText('00034');
  const field = row(page, 'approved');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('combobox').selectOption('false');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('false');
  await field.getByRole('button', { name: 'Approve', exact: true }).click();
  const vendor = row(page, 'vendor_name');
  await vendor.getByRole('button', { name: 'Edit', exact: true }).click();
  const value = '<img src=x onerror="window.injected=true">, "literal"';
  await vendor.getByRole('textbox').fill(value);
  await vendor.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(vendor.locator('.field-value')).toHaveText(value);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  const json = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(json.find(row => row.field === 'approved').value).toBe(false);
  expect(json.find(row => row.field === 'vendor_name').value).toBe(value);
  const csv = (await downloadText(page, 'CSV')).text;
  expect(csv).toContain('value_source');
  expect(csv).toContain('"<img src=x onerror=""window.injected=true"">, ""literal"""');
});

test('malformed deep links and malformed sample indexes recover without page errors', async ({ page }) => {
  let fail = true;
  await page.route('**/demo-data/index.json', route => fail ? route.fulfill({ json: { samples: 'wrong shape' } }) : route.continue());
  await page.goto('./#%ZZ', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('Invalid sample document index');
  fail = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(row(page, 'po_number')).toBeVisible();
});

import { spreadsheetScenario } from './spreadsheet.mjs';
test('spreadsheet download preserves literal text and review scope offline', async ({ page, context }, info) => {
  await page.goto('./', { waitUntil: 'networkidle' });
  await spreadsheetScenario(page, context, info);
});

test('oversized spreadsheet text leaves JSON export available', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  const field = row(page, 'invoice_number');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('a'.repeat(32768));
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  const downloads = [];
  page.on('download', d => downloads.push(d));
  await page.getByRole('button', { name: 'Export XLSX' }).click();
  await expect(page.locator('.toast')).toContainText('Export JSON to keep the complete data');
  expect(downloads).toHaveLength(0);
  expect(JSON.parse((await downloadText(page, 'JSON')).text)[0].value).toHaveLength(32768);
});
