import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { mkdirSync, writeFileSync } from 'node:fs';
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

test('a negated extracted date remains reviewable with its original evidence and exports', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../studies/date-claims/date-claims.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../studies/date-claims/negated-claim.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const date = row(page, 'issue_date');
  await expect(date.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(date.locator('.field-reasons')).toContainText('one calendar-valid date in YYYY-MM-DD format');
  await expect(date).toContainText('not 2026-03-04');
  await date.getByRole('button', { name: 'Inspect issue_date', exact: true }).click();
  const highlight = page.locator('.highlight-rect[data-path="issue_date"]');
  await expect(highlight).toHaveCount(1);
  await expect(highlight).toHaveAttribute('data-status', 'needs_review');
  await expect(page.locator('#page-frame img')).toBeVisible();
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const before = await (await request.get(`${url}/report`)).json();
  const evidence = before.report.fields.find(field => field.path === 'issue_date');
  expect(evidence).toMatchObject({ value: 'not 2026-03-04', page: 1, matched_text: 'Issue date: 2026-03-04' });
  expect(before.report.cross_field_checks.find(check => check.rule === 'invoice.due_date_order').status).toBe('not_checked');
  const directory = fileURLToPath(new URL('../../../docs/assets/date-claims', import.meta.url));
  if (process.env.UPDATE_DATE_CLAIM_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_DATE_CLAIM_SCREENSHOTS) await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await date.getByRole('button', { name: 'Edit', exact: true }).click();
  await date.getByRole('textbox').fill('2026-03-04');
  await date.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(date.locator('.review-badge')).toHaveText('edited');
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported).toHaveLength(1);
  expect(exported[0]).toMatchObject({ field: 'issue_date', value: '2026-03-04', original_value: 'not 2026-03-04', value_source: 'correction', verification_status: 'needs_review' });
  expect((await (await request.get(`${url}/report`)).json()).report).toEqual(before.report);
  const csv = (await downloadText(page, 'CSV')).text;
  expect(csv).toContain('not 2026-03-04');
  expect(csv).toContain('needs_review');
  if (process.env.UPDATE_DATE_CLAIM_SCREENSHOTS) writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ evidence, exported }, null, 2) + '\n');
});

test('a written date keeps every printed year digit through review and export', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../studies/written-dates/extra-year-digit.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByRole('combobox', { name: 'Schema', exact: true }).selectOption('contract');
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../studies/written-dates/extra-year-digit.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const date = row(page, 'effective_date');
  await expect(date.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(date.locator('.field-reasons')).toContainText('could not parse a date');
  await expect(date.locator('.field-evidence')).toContainText('May 1, 20260');
  await date.getByRole('button', { name: 'Inspect effective_date', exact: true }).click();
  await expect(page.locator('#page-frame img')).toBeVisible();
  const highlight = page.locator('.highlight-rect[data-path="effective_date"]');
  await expect(highlight).toHaveCount(1);
  await expect(highlight).toHaveAttribute('data-status', 'needs_review');
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const before = await (await request.get(`${url}/report`)).json();
  expect(before.report.counts).toEqual({ verified: 2, needs_review: 1, unsupported: 0 });
  const evidence = before.report.fields.find(field => field.path === 'effective_date');
  expect(evidence).toMatchObject({ page: 1, value: '2026-05-01', matched_text: 'Effective date: May 1, 20260' });
  const directory = fileURLToPath(new URL('../../../docs/assets/written-dates', import.meta.url));
  if (process.env.UPDATE_WRITTEN_DATE_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_WRITTEN_DATE_SCREENSHOTS) await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  // A human can confirm the intended date. That decision must not rewrite
  // the automated verdict or the literal evidence retained in the report.
  await date.getByRole('button', { name: 'Approve', exact: true }).click();
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported).toHaveLength(1);
  expect(exported[0]).toMatchObject({ field: 'effective_date', value: '2026-05-01', verification_status: 'needs_review' });
  expect(await (await request.get(`${url}/export.json?scope=reviewed`)).json()).toEqual(exported);
  expect((await (await request.get(`${url}/report`)).json()).report).toEqual(before.report);
  await page.reload();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  await page.getByRole('dialog', { name: 'Document sessions' }).locator('li').filter({ hasText: 'extra-year-digit.pdf' }).getByRole('button', { name: 'Open', exact: true }).click();
  expect(JSON.parse((await downloadText(page, 'JSON')).text)).toEqual(exported);
  if (process.env.UPDATE_WRITTEN_DATE_SCREENSHOTS) writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ evidence, exported }, null, 2) + '\n');
});

test('an invalid date reference cannot settle an ambiguous issue date through review and export', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../examples/date-convention.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../examples/fixtures/date-convention.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const date = row(page, 'issue_date');
  await expect(date.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(date.locator('.field-reasons')).toContainText('no other date on the document settles which');
  await date.getByRole('button', { name: 'Inspect issue_date', exact: true }).click();
  await expect(page.locator('#page-frame img')).toBeVisible();
  const highlight = page.locator('.highlight-rect[data-path="issue_date"]');
  await expect(highlight).toHaveCount(1);
  await expect(highlight).toHaveAttribute('data-status', 'needs_review');
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const before = await (await request.get(`${url}/report`)).json();
  expect(before.report.counts).toEqual({ verified: 3, needs_review: 1, unsupported: 0 });
  const evidence = before.report.fields.find(field => field.path === 'issue_date');
  expect(evidence).toMatchObject({ page: 1, value: '2026-04-03', matched_text: 'Issue Date: 03/04/2026' });
  const directory = fileURLToPath(new URL('../../../docs/assets/date-conventions', import.meta.url));
  if (process.env.UPDATE_DATE_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_DATE_SCREENSHOTS) await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await date.getByRole('button', { name: 'Edit', exact: true }).click();
  await date.getByRole('textbox').fill('2026-03-04');
  await date.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(date.locator('.review-badge')).toHaveText('edited');
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported).toHaveLength(1);
  expect(exported[0]).toMatchObject({ field: 'issue_date', value: '2026-03-04', original_value: '2026-04-03', value_source: 'correction', verification_status: 'needs_review' });
  expect(await (await request.get(`${url}/export.json?scope=reviewed`)).json()).toEqual(exported);
  expect((await (await request.get(`${url}/report`)).json()).report).toEqual(before.report);
  await page.reload();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  await page.getByRole('dialog', { name: 'Document sessions' }).locator('li').filter({ hasText: 'date-convention.pdf' }).getByRole('button', { name: 'Open', exact: true }).click();
  await expect(row(page, 'issue_date').locator('.review-badge')).toHaveText('edited');
  expect(JSON.parse((await downloadText(page, 'JSON')).text)).toEqual(exported);
  if (process.env.UPDATE_DATE_SCREENSHOTS) writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ evidence, exported }, null, 2) + '\n');
});

test('an omitted minus stays visible and readable in the real PDF review', async ({ page }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../examples/signed-amount.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../examples/fixtures/signed-amount.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const field = row(page, 'total');
  await expect(field.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(field.locator('.field-evidence')).toContainText('- $100.00');
  await expect(field.locator('.field-reasons')).toContainText('does not match -100');
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => document.documentElement.setAttribute('data-theme', theme), theme);
      await scan(page);
    }
  }
});

test('a unique quote keeps its location while the wrong item association requires review', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../examples/row-association.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../examples/fixtures/row-association.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const field = row(page, 'line_items[0].quantity');
  await expect(field.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(field.locator('.field-evidence')).toContainText('2');
  await expect(field.locator('.field-reasons')).toContainText('different visual line than line_items[0].description');
  await field.getByRole('button', { name: 'Inspect line_items[0].quantity', exact: true }).click();
  const highlight = page.locator('.highlight-rect[data-path="line_items[0].quantity"]');
  await expect(highlight).toHaveCount(1);
  await expect(highlight).toHaveAttribute('data-status', 'needs_review');
  await expect(page.locator('#page-frame img')).toBeVisible();
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const before = await (await request.get(`${url}/report`)).json();
  expect(before.report.counts).toEqual({ verified: 14, needs_review: 1, unsupported: 0 });
  const relation = before.report.row_checks.find(check => check.field === 'line_items[0].quantity');
  expect(relation).toMatchObject({ status: 'separate', field_source_status: 'verified', anchor_source_status: 'verified' });
  expect(relation.field_location.text).toBe('2');
  expect(relation.anchor_location.text).toBe('Delivery');
  expect(relation.field_location.rects[0].top).toBeGreaterThan(relation.anchor_location.rects[0].bottom);
  const directory = fileURLToPath(new URL('../../../docs/assets/row-association', import.meta.url));
  if (process.env.UPDATE_ASSOCIATION_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_ASSOCIATION_SCREENSHOTS) await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await field.getByRole('button', { name: 'Edit', exact: true }).click();
  await field.getByRole('textbox').fill('3');
  await field.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(field.locator('.review-badge')).toHaveText('edited');
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported[0]).toMatchObject({ field: 'line_items[0].quantity', value: 3, original_value: 2, value_source: 'correction' });
  expect((await (await request.get(`${url}/report`)).json()).report.row_checks).toEqual(before.report.row_checks);
  await page.reload();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  await page.getByRole('dialog', { name: 'Document sessions' }).locator('li').filter({ hasText: 'row-association.pdf' }).getByRole('button', { name: 'Open', exact: true }).click();
  await expect(row(page, 'line_items[0].quantity').locator('.review-badge')).toHaveText('edited');
  expect(JSON.parse((await downloadText(page, 'JSON')).text)).toEqual(exported);
  if (process.env.UPDATE_ASSOCIATION_SCREENSHOTS) writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ relation, exported }, null, 2) + '\n');
});

test('a repeated quantity from another row stays unresolved through review and export', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../examples/row-locality.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../examples/fixtures/row-locality.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const quantity = row(page, 'line_items[0].quantity');
  await expect(quantity.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
  await expect(quantity.locator('.field-reasons')).toContainText('no unique occurrence shares the visual line');
  await quantity.getByRole('button', { name: 'Inspect line_items[0].quantity', exact: true }).click();
  await expect(page.locator('#page-frame img')).toBeVisible();
  await expect(page.locator('.highlight-rect[data-path="line_items[0].quantity"]')).toHaveCount(0);
  for (const index of [1, 2]) {
    await expect(row(page, `line_items[${index}].quantity`).locator('.status-chip')).toHaveAttribute('data-status', 'verified');
    await expect(page.locator(`.highlight-rect[data-path="line_items[${index}].quantity"]`)).toHaveCount(1);
  }
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const original = await (await request.get(`${url}/report`)).json();
  expect(original.report.counts).toEqual({ verified: 14, needs_review: 1, unsupported: 0 });
  const evidence = original.report.fields.find(field => field.path === 'line_items[0].quantity');
  expect(evidence).toMatchObject({ value: 1, page: null, rects: [], matched_text: null });
  expect(original.report.fields.find(field => field.path === 'line_items[1].quantity').notes[0]).toContain('line_items[1].description');
  const directory = fileURLToPath(new URL('../../../docs/assets/row-locality', import.meta.url));
  if (process.env.UPDATE_LOCALITY_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_LOCALITY_SCREENSHOTS) await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await quantity.getByRole('button', { name: 'Edit', exact: true }).click();
  await quantity.getByRole('textbox').fill('3');
  await quantity.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(quantity.locator('.review-badge')).toHaveText('edited');
  const exported = JSON.parse((await downloadText(page, 'JSON')).text);
  expect(exported).toHaveLength(1);
  expect(exported[0]).toMatchObject({ field: 'line_items[0].quantity', value: 3, original_value: 1, value_source: 'correction' });
  expect(await (await request.get(`${url}/export.json?scope=reviewed`)).json()).toEqual(exported);
  expect((await (await request.get(`${url}/report`)).json()).report).toEqual(original.report);
  await page.reload();
  await page.getByRole('button', { name: 'Sessions', exact: true }).click();
  const session = page.getByRole('dialog', { name: 'Document sessions' }).locator('li').filter({ hasText: 'row-locality.pdf' });
  await session.getByRole('button', { name: 'Open', exact: true }).click();
  await expect(row(page, 'line_items[0].quantity').locator('.review-badge')).toHaveText('edited');
  expect(JSON.parse((await downloadText(page, 'JSON')).text)).toEqual(exported);
  if (process.env.UPDATE_LOCALITY_SCREENSHOTS) writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ evidence, exported }, null, 2) + '\n');
});

test('quoted but inconsistent line arithmetic is reviewable and corrections keep their provenance', async ({ page, request, browserName }) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('../../../examples/line-arithmetic.pdf', import.meta.url)));
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('../../../examples/fixtures/line-arithmetic.json', import.meta.url)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const quantity = row(page, 'line_items[0].quantity');
  for (const path of ['quantity', 'unit_price', 'amount']) {
    const field = row(page, `line_items[0].${path}`);
    await expect(field.locator('.status-chip')).toHaveAttribute('data-status', 'needs_review');
    await expect(field.locator('.field-reasons')).toContainText('59.85');
    await expect(field.locator('.field-reasons')).toContainText('before discounts or adjustments');
  }
  await expect(quantity.locator('.field-evidence')).toContainText('Precision bolts 3 19.95 39.90');
  await quantity.getByRole('button', { name: 'Inspect line_items[0].quantity', exact: true }).click();
  await expect(page.locator('#page-frame img')).toBeVisible();
  const url = (await page.locator('#page-frame img').getAttribute('src')).replace(/\/pages\/\d+\.png$/, '');
  const original = await (await request.get(`${url}/report`)).json();
  const calculation = original.report.cross_field_checks[0];
  expect(calculation.status).toBe('failed');
  expect([calculation.computed, calculation.observed, calculation.difference]).toEqual(['59.85', '39.9', '-19.95']);

  const directory = fileURLToPath(new URL('../../../docs/assets/arithmetic', import.meta.url));
  if (process.env.UPDATE_ARITHMETIC_SCREENSHOTS) mkdirSync(directory, { recursive: true });
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await scan(page);
    if (process.env.UPDATE_ARITHMETIC_SCREENSHOTS) {
      await page.screenshot({ path: `${directory}/${browserName}-${width}.png`, fullPage: true });
    }
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await quantity.getByRole('button', { name: 'Edit', exact: true }).click();
  await quantity.getByRole('textbox').fill('2');
  await quantity.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(quantity.locator('.review-badge')).toHaveText('edited');
  const downloaded = await downloadText(page, 'JSON');
  const rows = JSON.parse(downloaded.text);
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({ field: 'line_items[0].quantity', value: 2, original_value: 3, value_source: 'correction' });
  expect(await (await request.get(`${url}/export.json?scope=reviewed`)).json()).toEqual(rows);
  const reviewed = await (await request.get(`${url}/report`)).json();
  // The audit describes the original extraction; human edits are separate evidence.
  expect(reviewed.report.cross_field_checks).toEqual(original.report.cross_field_checks);
  if (process.env.UPDATE_ARITHMETIC_SCREENSHOTS) {
    writeFileSync(`${directory}/${browserName}-observations.json`, JSON.stringify({ calculation, downloadedRows: rows }, null, 2) + '\n');
  }
});

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

test('cropped PDF uses the visible canvas and highlights the actual evidence position', async ({ page }) => {
  const cropped = fileURLToPath(new URL('../../../tests/fixtures/cropped-marker.pdf', import.meta.url));
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('PDF document').setInputFiles(cropped);
  await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
  await page.getByLabel('Fixture JSON').setInputFiles({
    name: 'marker.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({
      vendor_name: { value: 'Marker', evidence: ['Marker'], page: 1 },
      invoice_number: { value: 'M1', evidence: [] },
      issue_date: { value: '2026-10-04', evidence: [] },
      total: { value: 1, evidence: [] },
    })),
  });
  await page.getByRole('button', { name: 'Run extraction' }).click();
  await expect(row(page, 'vendor_name').locator('.field-value')).toHaveText('Marker');
  await page.getByRole('button', { name: 'Inspect vendor_name', exact: true }).click();
  const image = page.locator('#page-frame img');
  await expect.poll(() => image.evaluate(el => [el.naturalWidth, el.naturalHeight])).toEqual([800, 1000]);
  const highlight = page.locator('.highlight-rect[data-path="vendor_name"]');
  await expect(highlight).toHaveAttribute('data-status', 'verified');
  const frame = await page.locator('#page-frame').boundingBox();
  const box = await highlight.boundingBox();
  expect(Math.abs((box.x - frame.x) / frame.width - 50 / 400)).toBeLessThan(0.005);
  expect(Math.abs((box.y - frame.y) / frame.height - 90.484 / 500)).toBeLessThan(0.005);
});
