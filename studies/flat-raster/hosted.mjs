// Exercise the deployed static sample; the native PDF audit runs build/server side.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';

const baseURL = process.env.FIELDPROOF_HOSTED_URL ?? 'https://antonsoo.github.io/fieldproof/';
const observations = [];
for (const [engine, launcher] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await launcher.launch();
  try {
    for (const width of [375, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      try {
        const page = await context.newPage();
        const errors = [], violations = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.exposeFunction('recordPolicyViolation', directive => violations.push(directive));
        await page.addInitScript(() => addEventListener('securitypolicyviolation', event => window.recordPolicyViolation(event.violatedDirective)));
        await page.goto(`${baseURL}#hidden-text`, { waitUntil: 'networkidle' });
        const total = page.locator('.field-row').filter({ has: page.getByRole('button', { name: 'Inspect total', exact: true }) });
        await total.waitFor();
        assert.equal(await total.locator('.field-value').textContent(), '900.00');
        assert.equal(await total.locator('.status-chip').getAttribute('data-status'), 'needs_review');
        assert.match(await total.locator('.field-reasons').textContent(), /native-text paint contribution/);
        await total.getByRole('button', { name: 'Inspect total', exact: true }).click();
        await page.waitForFunction(() => { const image = document.querySelector('#page-frame img'); return image?.complete && image.naturalWidth > 0; });
        if (width === 375) await page.getByRole('button', { name: 'Fields', exact: true }).click();
        await page.evaluate(() => document.fonts.ready);
        const requests = [];
        await context.setOffline(true);
        page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
        await total.getByRole('button', { name: 'Edit', exact: true }).click();
        await total.getByRole('textbox').fill('90');
        await total.getByRole('button', { name: 'Save', exact: true }).click();
        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
        const raw = await readFile(await (await pending).path());
        const exported = JSON.parse(raw);
        assert.equal(exported.length, 1);
        assert.equal(exported[0].field, 'total');
        assert.equal(exported[0].value, 90);
        assert.equal(exported[0].original_value, 900);
        assert.equal(exported[0].value_source, 'correction');
        assert.equal(exported[0].verification_status, 'needs_review');
        assert.deepEqual(requests, []);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await context.setOffline(false);
        await page.reload({ waitUntil: 'networkidle' });
        assert.equal(await total.locator('.field-value').textContent(), '90.00');
        assert.equal(await total.locator('.status-chip').getAttribute('data-status'), 'needs_review');
        assert.deepEqual(errors, []);
        assert.deepEqual(violations, []);
        observations.push({ engine, version: browser.version(), width, originalValue: 900, correctedValue: 90,
          exported, downloadSha256: createHash('sha256').update(raw).digest('hex'), offlineRequests: 0,
          noOverflow: true, correctionSurvivesReload: true, automatedVerdict: 'needs_review', pageErrors: errors, cspViolations: violations });
        console.log(`${engine} ${width}: actual hosted correction, offline download and reload verified`);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(process.argv[2] ?? new URL('results/hosted-browser.json', import.meta.url), JSON.stringify({ baseURL,
  scope: 'Actual deployed static demo, not an in-browser native PDF audit.', observations }, null, 2) + '\n');
