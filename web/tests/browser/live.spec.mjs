import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { row, downloadText, scan, installAudit } from './helpers.mjs';

const pdf = fileURLToPath(new URL('../../../examples/invoice.pdf', import.meta.url));
const fixture = fileURLToPath(new URL('../../../examples/fixtures/invoice.json', import.meta.url));
installAudit(test);

test.afterEach(async ({ request }) => {
  const listing = await (await request.get('/api/documents')).json();
  for (const entry of listing.documents) {
    await expect.poll(async () => (await request.delete(`/api/documents/${entry.id}`)).status(), { timeout: 5000 }).toBe(204);
  }
});

async function configure(page) {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(pdf);
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fixture);
}

async function extract(page) {
  await configure(page);
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await expect(row(page, 'total')).toBeVisible();
}

test('real PDF and fixture extraction support nested corrections and identical API exports', async ({ page, request }) => {
  await extract(page);
  const field = row(page, 'line_items[0].amount');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('123.5');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('123.50');
  await field.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(field.locator('.review-badge')).toHaveText('approved');
  const downloaded = await downloadText(page, 'JSON');
  const rows = JSON.parse(downloaded.text);
  expect(rows).toHaveLength(1);
  expect(rows[0].value).toBe(123.5);
  const id = await page.locator('#page-frame img').getAttribute('src');
  const documentUrl = id.replace(/\/pages\/\d+\.png$/, '');
  const api = await request.get(`${documentUrl}/export.json?scope=reviewed`);
  expect(await api.json()).toEqual(rows);
  const csv = await downloadText(page, 'CSV');
  const apiCsv = await (await request.get(`${documentUrl}/export.csv?scope=reviewed`)).text();
  // JSON numbers lose Python's .0 in JavaScript. Compare numeric cells as
  // numbers; this fixture row has no quoted string cells or embedded commas.
  const csvRow = text => text.split('\r\n')[1].split(',').map((cell, index) => [1, 2, 6].includes(index) ? Number(cell) : cell);
  expect(csvRow(csv.text)).toEqual(csvRow(apiCsv));
  expect(rows[0].value_source).toBe('correction');
  expect(rows[0].original_value).toBe(1740);
  await scan(page);
});

test('failed review saves keep the editor and prior value for retry', async ({ page }) => {
  await extract(page);
  let fail = true;
  await page.route('**/api/documents/*/review', route => fail ? route.fulfill({ status: 503, json: { detail: 'Review temporarily unavailable' } }) : route.continue());
  const field = row(page, 'total');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('123.5');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.getByRole('alert')).toHaveText('Review temporarily unavailable');
  await expect(field.getByRole('textbox')).toHaveValue('123.5');
  await expect(field.locator('.field-value')).toHaveText('2,600.00');
  fail = false;
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('123.50');
});

test('late review reply stays with its document and pending saves disable export', async ({ page }) => {
  await extract(page);
  await row(page, 'vendor_name').getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Export JSON' })).toBeEnabled();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let returned;
  const done = new Promise(resolve => { returned = resolve; });
  await page.route('**/api/documents/*/review', async route => {
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response }).catch(() => {});
    returned();
  });
  await row(page, 'total').getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Export JSON' })).toBeDisabled();
  await page.getByRole('button', { name: 'New document' }).click();
  await page.getByLabel('PDF document').setInputFiles(pdf);
  await page.getByLabel('Fixture JSON').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await expect(row(page, 'total')).toBeVisible();
  release();
  await done;
  await expect(row(page, 'total').locator('.review-badge')).toHaveCount(0);
  await expect(page.locator('#review-progress')).toContainText('0 of 25 reviewed');
});

test('cancelled extraction cannot resurrect a reset document', async ({ page }) => {
  await configure(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let returned;
  const done = new Promise(resolve => { returned = resolve; });
  await page.route('**/api/documents/*/extract', async route => {
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response }).catch(() => {});
    returned();
  });
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await page.getByRole('button', { name: 'New document' }).click();
  await expect(page.getByRole('button', { name: /choose a file/ })).toBeVisible();
  release();
  await done;
  await expect(page.locator('.field-row')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /choose a file/ })).toBeVisible();
});

test('fixture failure is recoverable without losing the uploaded document', async ({ page }) => {
  await configure(page);
  await page.getByLabel('Fixture JSON').setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{ invalid') });
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await expect(page.getByRole('alert')).toContainText('not valid JSON');
  await page.getByLabel('Fixture JSON').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(row(page, 'total')).toBeVisible();
});

test('upload and configure controls are accessible in both themes at phone widths', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await scan(page);
  await configure(page);
  await page.setViewportSize({ width: 320, height: 900 });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(theme => document.documentElement.setAttribute('data-theme', theme), theme);
    await scan(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('a cancelled slow upload cannot replace a newer uploaded PDF', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let returned;
  const done = new Promise(resolve => { returned = resolve; });
  let first = true;
  await page.route('**/api/documents', async route => {
    if (!first) return route.continue();
    first = false;
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response }).catch(() => {});
    returned();
  });
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(pdf);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByLabel('PDF document').setInputFiles({ name: 'second.pdf', mimeType: 'application/pdf', buffer: await (await import('node:fs/promises')).readFile(pdf) });
  await expect(page.getByRole('heading', { name: 'second.pdf' })).toBeVisible();
  release();
  await done;
  await expect(page.getByRole('heading', { name: 'second.pdf' })).toBeVisible();
});

test('sessions reopen saved corrections after reload and removal needs explicit confirmation', async ({ page, request }) => {
  await extract(page);
  const field = row(page, 'total');
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('123.5');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.field-value')).toHaveText('123.50');
  const source = await page.locator('#page-frame img').getAttribute('src');
  const documentUrl = source.replace(/\/pages\/\d+\.png$/, '');
  await page.reload();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Document sessions' });
  await expect(dialog).toContainText('1 of 25 reviewed');
  await dialog.getByRole('button', { name: 'Open', exact: true }).click();
  await expect(row(page, 'total').locator('.field-value')).toHaveText('123.50');
  expect(JSON.parse((await downloadText(page, 'JSON')).text)[0].value).toBe(123.5);
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Keep session' })).toBeFocused();
  await dialog.getByRole('button', { name: 'Keep session' }).click();
  expect((await request.get(documentUrl)).status()).toBe(200);
  await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
  await dialog.getByRole('button', { name: 'Remove permanently' }).click();
  await expect(dialog).toContainText('No documents stored yet');
  expect((await request.get(documentUrl)).status()).toBe(404);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByRole('button', { name: /choose a file/ })).toBeVisible();
});

test('session dialog is keyboard accessible in both themes at narrow phone width', async ({ page }) => {
  await configure(page);
  await page.setViewportSize({ width: 320, height: 568 });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(theme => document.documentElement.setAttribute('data-theme', theme), theme);
    await page.getByRole('button', { name: 'Sessions', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Document sessions' });
    await expect(dialog).toContainText('Ready to extract');
    await expect(dialog.getByRole('button', { name: 'Close', exact: true })).toBeFocused();
    await scan(page);
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Sessions', exact: true })).toBeFocused();
  }
});

test('session listing and deletion failures can be retried without losing decisions', async ({ page }) => {
  await extract(page);
  await row(page, 'total').getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(row(page, 'total').locator('.review-badge')).toHaveText('approved');
  let listingFails = true;
  let deleteFails = true;
  await page.route('**/api/documents', route => listingFails ? route.fulfill({ status: 503, json: { detail: 'Sessions unavailable' } }) : route.continue());
  await page.route('**/api/documents/*', route => route.request().method() === 'DELETE' && deleteFails ? route.fulfill({ status: 503, json: { detail: 'Removal unavailable' } }) : route.continue());
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Document sessions' });
  await expect(dialog.getByRole('alert')).toHaveText('Sessions unavailable');
  listingFails = false;
  await dialog.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(dialog).toContainText('1 of 25 reviewed');
  await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
  await dialog.getByRole('button', { name: 'Remove permanently' }).click();
  await expect(dialog.getByRole('alert')).toHaveText('Removal unavailable');
  await dialog.getByRole('button', { name: 'Keep session' }).click();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(row(page, 'total').locator('.review-badge')).toHaveText('approved');
  deleteFails = false;
});

test('session controls cannot discard an unsaved correction', async ({ page }) => {
  await extract(page);
  await row(page, 'total').getByRole('button', { name: 'Edit', exact: true }).click();
  await row(page, 'total').getByRole('textbox').fill('123.5');
  await expect(page.getByRole('button', { name: 'New document', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Document sessions' });
  await expect(dialog).toContainText('Finish or cancel');
  await expect(dialog.getByRole('button', { name: 'Open', exact: true })).toBeDisabled();
  await expect(dialog.getByRole('button', { name: 'Remove', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(row(page, 'total').getByRole('textbox')).toHaveValue('123.5');
  await row(page, 'total').getByRole('textbox').press('Escape');
  await expect(page.getByRole('button', { name: 'New document', exact: true })).toBeEnabled();
});

test('full capacity refuses uploads, keeps reviewed values, and removal permits recovery', async ({ page, request }) => {
  await extract(page);
  await row(page, 'total').getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(row(page, 'total').locator('.review-badge')).toHaveText('approved');
  const buffer = await (await import('node:fs/promises')).readFile(pdf);
  for (let index = 0; index < 7; index++) {
    const response = await request.post('/api/documents', { multipart: { file: { name: `capacity-${index}.pdf`, mimeType: 'application/pdf', buffer } } });
    expect(response.status()).toBe(200);
  }
  await page.getByRole('button', { name: 'New document', exact: true }).click();
  await page.getByLabel('PDF document').setInputFiles(pdf);
  await expect(page.getByRole('alert')).toContainText('All 8 document slots');
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Document sessions' });
  await expect(dialog).toContainText('8 of 8 document slots');
  const retained = dialog.locator('li').filter({ hasText: 'invoice.pdf' });
  await expect(retained).toContainText('1 of 25 reviewed');
  const discarded = dialog.locator('li').filter({ hasText: 'capacity-6.pdf' });
  await discarded.getByRole('button', { name: 'Remove', exact: true }).click();
  await discarded.getByRole('button', { name: 'Remove permanently' }).click();
  await expect(dialog).toContainText('7 of 8 document slots');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
});

test('oversized fixture is refused before sending it and uploaded PDF remains usable', async ({ page }) => {
  await configure(page);
  let extractions = 0;
  page.on('request', request => { if (request.url().endsWith('/extract')) extractions++; });
  await page.getByLabel('Fixture JSON').setInputFiles({ name: 'large.json', mimeType: 'application/json', buffer: Buffer.alloc(2 * 1024 * 1024 + 1, 32) });
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await expect(page.getByRole('alert')).toContainText('2 MiB limit');
  expect(extractions).toBe(0);
  await page.getByLabel('Fixture JSON').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(row(page, 'total')).toBeVisible();
});
