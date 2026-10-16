// Capture the reproduced baseline through a separately running source server.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { fileURLToPath } from 'node:url';
import { mkdirSync, writeFileSync } from 'node:fs';

const study = new URL('./', import.meta.url);
const observations = [];
for (const [browserName, engine, width] of [['chromium', chromium, 1440], ['firefox', firefox, 375]]) {
  const browser = await engine.launch();
  const page = await browser.newPage({
    baseURL: process.env.FIELDPROOF_BASELINE_URL || 'http://127.0.0.1:4432/',
    viewport: { width, height: 960 },
  });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(process.env.FIELDPROOF_BASELINE_URL || 'http://127.0.0.1:4432/');
  await page.getByLabel('PDF document').setInputFiles(fileURLToPath(new URL('fixtures/end-n.pdf', study)));
  await page.getByRole('button', { name: 'Run extraction' }).waitFor();
  await page.getByLabel('Fixture JSON').setInputFiles(fileURLToPath(new URL('fixture.json', study)));
  await page.getByRole('button', { name: 'Run extraction' }).click();
  const inspect = page.getByRole('button', { name: 'Inspect total', exact: true });
  await inspect.waitFor();
  await inspect.click();
  await page.locator('#page-frame img').waitFor();
  await page.waitForFunction(() => {
    const image = document.querySelector('#page-frame img');
    return image?.complete && image.naturalWidth > 0;
  });
  if (width === 375) await page.getByRole('button', { name: 'Fields', exact: true }).click();
  const listing = await (await page.request.get('/api/documents')).json();
  const id = listing.documents[0].id;
  const result = await (await page.request.get(`/api/documents/${id}/report`)).json();
  const total = result.report.fields.find(field => field.path === 'total');
  if (total.status !== 'verified' || total.value !== 900) throw new Error('Baseline did not reproduce');
  const destination = fileURLToPath(new URL('../../docs/assets/clipped-text/', study));
  mkdirSync(destination, { recursive: true });
  await page.screenshot({ path: `${destination}/before-${browserName}-${width}.png`, fullPage: true });
  observations.push({ browser: browserName, width, report: result.report, errors });
  await page.request.delete(`/api/documents/${id}`);
  await browser.close();
  if (errors.length) throw new Error(JSON.stringify(errors));
}
writeFileSync(new URL('results/before-browser.json', study), JSON.stringify(observations, null, 2) + '\n');
console.log('Captured the false verification in Chromium desktop and Firefox mobile');
