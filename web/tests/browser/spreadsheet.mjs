import { expect } from '@playwright/test';
import { strFromU8, unzipSync } from 'fflate';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { row, downloadText, scan } from './helpers.mjs';

export async function spreadsheetScenario(page, context, info) {
  await expect(page.getByRole('button', { name: 'Export XLSX' })).toBeDisabled();
  for (const [path, value] of [['invoice_number', '00034'], ['vendor_name', '=1+1'], ['po_number', '1E10'], ['line_items[0].description', '12345678901234567890'], ['total', '123.45']]) {
    const field = row(page, path);
    await field.getByRole('button', { name: 'Edit', exact: true }).click();
    await field.getByRole('textbox').fill(value);
    await field.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(field.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();
  }
  await row(page, 'invoice_number').getByRole('button', { name: 'Approve', exact: true }).click();
  await row(page, 'tax').getByRole('button', { name: 'Reject', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Export XLSX' })).toBeEnabled();
  await expect(page.locator('#page-frame img')).toBeVisible();
  const destination = process.env.SPREADSHEET_EVIDENCE;
  if (destination) mkdirSync(destination, { recursive: true });
  await context.setOffline(true);
  try {
    for (const scope of ['reviewed', 'all']) {
      await page.getByLabel('Export', { exact: true }).selectOption(scope);
      const json = await downloadText(page, 'JSON');
      const csv = await downloadText(page, 'CSV');
      const expected = JSON.parse(json.text);
      expect(expected.some(r => r.field === 'tax')).toBe(false);
      expect(expected.find(r => r.field === 'invoice_number')).toMatchObject({ value: '00034', value_source: 'correction', review_status: 'approved' });
      expect(expected).toHaveLength(scope === 'reviewed' ? 5 : 24);
      const promise = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Export XLSX' }).click();
      const download = await promise;
      expect(download.suggestedFilename()).toBe('invoice.fieldproof.xlsx');
      const chunks = [];
      for await (const chunk of await download.createReadStream()) chunks.push(chunk);
      const bytes = Buffer.concat(chunks);
      const parts = unzipSync(bytes);
      const xml = strFromU8(parts['xl/worksheets/sheet1.xml']);
      expect(xml).not.toMatch(/<f[ >]|hyperlink|externalLink/);
      const visible = await page.evaluate(xml => {
        const doc = new DOMParser().parseFromString(xml, 'application/xml');
        if (doc.querySelector('parsererror')) throw new Error('Invalid workbook XML');
        return [...doc.querySelectorAll('sheetData row')].slice(1).map(row => [...row.children].map(cell => {
          if (cell.getAttribute('t') === 'inlineStr') return cell.querySelector('t')?.textContent ?? '';
          const text = cell.querySelector('v')?.textContent;
          return text === undefined ? null : cell.getAttribute('t') === 'b' ? text === '1' : Number(text);
        }));
      }, xml);
      expect(visible).toEqual(expected.map(r => Object.values(r)));
      if (destination) {
        const base = join(destination, `${info.project.name}-${scope}`);
        writeFileSync(`${base}.json`, json.text);
        writeFileSync(`${base}.csv`, csv.text);
        writeFileSync(`${base}.xlsx`, bytes);
      }
    }
    await page.getByPlaceholder("Search fields").fill("invoice_number");
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await scan(page);
      if (destination) await page.screenshot({ path: join(destination, `${info.project.name}-${width}.png`) });
    }
  } finally { await context.setOffline(false); }
}
