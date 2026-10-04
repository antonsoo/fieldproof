import { expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export const row = (page, path) => page.locator('.field-row').filter({ has: page.getByRole('button', { name: `Inspect ${path}`, exact: true }) });

export async function downloadText(page, format) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: `Export ${format}` }).click();
  const download = await pending;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return { filename: download.suggestedFilename(), text: Buffer.concat(chunks).toString() };
}

export async function scan(page) {
  const report = await new AxeBuilder({ page }).analyze();
  expect(report.violations.map(({ id, nodes }) => ({ id, targets: nodes.map(node => node.target) }))).toEqual([]);
}

export function installAudit(test) {
  test.beforeEach(async ({ page, baseURL }) => {
    await page.addInitScript(() => {
      window.fieldproofAudit = { errors: [], csp: [] };
      addEventListener('error', event => { if (event.message) window.fieldproofAudit.errors.push(event.message); });
      addEventListener('unhandledrejection', event => window.fieldproofAudit.errors.push(String(event.reason)));
      addEventListener('securitypolicyviolation', event => window.fieldproofAudit.csp.push(event.violatedDirective));
    });
    const origin = new URL(baseURL).origin;
    page.on('request', request => expect(new URL(request.url()).origin).toBe(origin));
  });
  test.afterEach(async ({ page }) => {
    expect(await page.evaluate(() => window.fieldproofAudit)).toEqual({ errors: [], csp: [] });
  });
}
