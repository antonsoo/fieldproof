// Real production app edits and offline downloads in both demo and native server modes.
import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { createWriteStream } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, resolve, sep } from 'node:path';

const [beforeArg, afterArg, beforePython, afterPython, outputArg] = process.argv.slice(2);
assert(beforeArg && afterArg && beforePython && afterPython && outputArg,
  'Expected BEFORE_ROOT AFTER_ROOT BEFORE_PYTHON AFTER_PYTHON OUTPUT');
const require = createRequire(new URL('../../web/package.json', import.meta.url));
const { chromium, firefox, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { strFromU8, unzipSync } = require('fflate');
const output = resolve(outputArg); await mkdir(output, { recursive: true });
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const cases = JSON.parse(await readFile(new URL('./cases.json', import.meta.url), 'utf8'));
const selected = ['money', 'seventeen-digit-fraction', 'subnormal', 'javascript-safe-integer-limit']
  .map(id => cases.find(item => item.id === id));
const views = [], records = [];
const pause = ms => new Promise(done => setTimeout(done, ms));

async function serve(root, mode, python, phase) {
  const dist = resolve(root, 'web', mode === 'demo' ? 'dist-demo' : 'dist');
  const server = createServer(async (request, response) => {
    const name = new URL(request.url, 'http://localhost').pathname.replace(/^\/fieldproof\//, '') || 'index.html';
    const path = resolve(dist, name);
    if (!path.startsWith(dist + sep)) { response.writeHead(403); response.end(); return; }
    try {
      const bytes = await readFile(path);
      response.writeHead(200, { 'Content-Type': ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.woff2': 'font/woff2' })[extname(path)] ?? 'application/octet-stream' });
      response.end(bytes);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(done => server.listen(0, '127.0.0.1', done));
  const port = server.address().port;
  if (mode === 'demo') return { dist, origin: `http://127.0.0.1:${port}`, stop: async () => {
    server.closeAllConnections(); await new Promise(done => server.close(done));
  } };
  await new Promise(done => server.close(done));
  const log = createWriteStream(resolve(output, `${phase}-server.log`));
  const env = { ...process.env, PYTHONPATH: resolve(root, 'src'), FIELDPROOF_STATIC_DIR: dist };
  if (phase === 'after' && process.env.NUMERIC_XLSX_INSTALLED_AFTER === '1') {
    delete env.PYTHONPATH; delete env.FIELDPROOF_STATIC_DIR;
  }
  const child = spawn(resolve(python), ['-m', 'uvicorn', 'fieldproof.server.app:app', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: root, env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.pipe(log); child.stderr.pipe(log, { end: false });
  const exited = new Promise(done => child.once('exit', code => done(code)));
  const origin = `http://127.0.0.1:${port}`;
  let ready = false;
  for (let attempt = 0; attempt < 150; attempt++) {
    assert(child.exitCode === null, 'Native review server exited during startup');
    try { if ((await fetch(origin + '/api/documents')).ok) { ready = true; break; } } catch {}
    await pause(100);
  }
  assert(ready, 'Native review server did not become ready');
  return { dist, origin, stop: async () => { child.kill('SIGTERM'); await exited; log.end(); } };
}

for (const [phase, rootArg, python] of [['before', beforeArg, beforePython], ['after', afterArg, afterPython]]) {
  if (phase === 'before' && process.env.NUMERIC_XLSX_INSTALLED_AFTER === '1') continue;
  const root = resolve(rootArg);
  for (const mode of process.env.NUMERIC_XLSX_INSTALLED_AFTER === '1' ? ['live'] : ['demo', 'live']) {
    const host = await serve(root, mode, python, phase);
    try {
      for (const [engine, type] of Object.entries({ chromium, firefox })) {
        const browser = await type.launch();
        try {
          for (const width of [1440, 375]) {
            const context = await browser.newContext({ viewport: { width, height: 1000 } });
            const errors = [], external = [], late = [], pending = [], loaded = {};
            let offline = false;
            try {
              const page = await context.newPage();
              await page.addInitScript(() => {
                window.policyViolations = [];
                document.addEventListener('securitypolicyviolation', event => window.policyViolations.push(event.violatedDirective));
              });
              page.on('pageerror', error => errors.push(error.message));
              page.on('console', message => {
                if (message.type() === 'error') console.error(phase, mode, engine, width, message.text());
              });
              page.on('request', request => {
                if (!/^https?:/.test(request.url())) return;
                if (new URL(request.url()).origin !== host.origin) external.push(request.url());
                if (offline) late.push(new URL(request.url()).pathname);
              });
              page.on('response', response => {
                if (!response.url().startsWith(host.origin)) return;
                const path = new URL(response.url()).pathname;
                if (mode === 'live' && path.startsWith('/api/')) return;
                const name = path.replace(/^\/fieldproof\//, '').replace(/^\//, '') || 'index.html';
                pending.push((async () => {
                  const bytes = await response.body(), local = await readFile(resolve(host.dist, name));
                  assert.equal(sha(bytes), sha(local), name); loaded[name] = { bytes: bytes.length, sha256: sha(bytes) };
                })());
              });
              await page.goto(host.origin + (mode === 'demo' ? '/fieldproof/' : '/'));
              if (mode === 'live') {
                await page.getByLabel('PDF document').setInputFiles(resolve(root, 'examples/invoice.pdf'));
                await expect(page.getByRole('button', { name: 'Run extraction' })).toBeVisible();
                await page.getByLabel('Fixture JSON').setInputFiles(resolve(root, 'examples/fixtures/invoice.json'));
                await page.getByRole('button', { name: 'Run extraction' }).click();
              }
              const field = page.locator('.field-row').filter({ has: page.getByRole('button', { name: 'Inspect total', exact: true }) });
              await expect(field).toBeVisible();
              await expect(page.locator('#page-frame img')).toBeAttached();
              await page.waitForFunction(() => document.querySelector('#page-frame img')?.complete);
              await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.fonts].map(font => font.load())); });
              await Promise.all(pending);
              for (const item of selected) {
                await context.setOffline(false); offline = false;
                await field.getByRole('button', { name: 'Edit', exact: true }).click();
                await field.getByRole('textbox').fill(String(item.value));
                await field.getByRole('button', { name: 'Save', exact: true }).click();
                await expect(field.locator('.review-badge')).toHaveText('edited');
                await expect(field.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();
                await context.setOffline(true); offline = true;
                for (const scope of ['reviewed', 'all']) {
                  await page.getByLabel('Export', { exact: true }).selectOption(scope);
                  const take = async format => {
                    // Exercise separate user-paced downloads rather than a burst of export clicks.
                    await pause(200);
                    const event = page.waitForEvent('download');
                    await page.getByRole('button', { name: `Export ${format}` }).click();
                    const download = await event.catch(async error => {
                      console.error(JSON.stringify({ phase, mode, engine, width, case: item.id, scope, format,
                        note: await page.locator('[role="status"]').allTextContents() }));
                      throw error;
                    }), chunks = [];
                    for await (const chunk of await download.createReadStream()) chunks.push(chunk);
                    return Buffer.concat(chunks);
                  };
                  const json = await take('JSON'), bytes = await take('XLSX');
                  const rows = JSON.parse(json), index = rows.findIndex(row => row.field === 'total');
                  assert(index >= 0); assert.equal(rows[index].value, item.value);
                  assert.equal(rows[index].value_source, 'correction'); assert.equal(rows[index].review_status, 'edited');
                  const xml = strFromU8(unzipSync(bytes)['xl/worksheets/sheet1.xml']);
                  const cells = await page.evaluate(({ xml, index }) => {
                    const doc = new DOMParser().parseFromString(xml, 'application/xml');
                    if (doc.querySelector('parsererror')) throw new Error('Invalid workbook XML');
                    if (doc.querySelector('f,hyperlink')) throw new Error('Unexpected active cell');
                    return [...doc.querySelectorAll('sheetData row')[index + 1].children].map(cell => ({
                      type: cell.getAttribute('t') ?? 'blank', text: cell.querySelector('t')?.textContent ?? null,
                      number: cell.querySelector('v')?.textContent ?? null,
                    }));
                  }, { xml, index });
                  const agrees = cells[1].type === item.cell && (item.cell !== 'inlineStr' || cells[1].text === String(item.value));
                  if (phase === 'after') assert(agrees, `${mode}/${engine}/${item.id}`);
                  assert.equal(cells[2].type, 'n'); assert.equal(Number(cells[2].number), rows[index].original_value);
                  const name = `${phase}-${mode}-${engine}-${width}-${item.id}-${scope}`;
                  await writeFile(resolve(output, name + '.xlsx'), bytes);
                  records.push({ phase, mode, engine, width, case: item.id, scope, agrees, row: rows[index], cells,
                    file: name + '.xlsx', bytes: bytes.length, sha256: sha(bytes) });
                }
              }
              const violations = (await new AxeBuilder({ page }).analyze()).violations.map(row => row.id);
              const policy = await page.evaluate(() => window.policyViolations);
              const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
              assert.deepEqual(violations, []); assert.deepEqual(errors, []); assert.deepEqual(external, []);
              assert.deepEqual(late, []); assert.deepEqual(policy, []); assert(!overflow);
              if (phase === 'after' && mode === 'live' && engine === 'chromium' && process.env.NUMERIC_XLSX_INSTALLED_AFTER !== '1') {
                await page.getByPlaceholder('Search fields').fill('total');
                await page.evaluate(() => window.scrollTo(0, 0));
                await page.screenshot({ path: resolve(output, `after-live-chromium-${width}.png`), fullPage: true });
              }
              await Promise.all(pending);
              views.push({ phase, mode, engine, browser: browser.version(), width, loaded, offlineExports: true,
                pageErrors: errors, externalRequests: external, lateRequests: late, policyViolations: policy,
                axeViolations: violations, overflow });
            } finally { await context.close(); }
          }
        } finally { await browser.close(); }
      }
    } finally { await host.stop(); }
  }
}
const result = { node: process.version, workflows: records.length,
  beforeDisagreements: records.filter(row => row.phase === 'before' && !row.agrees).length,
  afterDisagreements: records.filter(row => row.phase === 'after' && !row.agrees).length, records, views };
await writeFile(resolve(output, 'observations.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ workflows: result.workflows, beforeDisagreements: result.beforeDisagreements,
  afterDisagreements: result.afterDisagreements, views: views.length }));
