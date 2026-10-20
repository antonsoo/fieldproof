// Actual local/hosted browser downloads. Run after a build, with API for live mode.
import { chromium, firefox, expect } from '../../web/node_modules/@playwright/test/index.mjs';
import { unzipSync, strFromU8 } from '../../web/node_modules/fflate/esm/index.mjs';
import { parseArgs } from 'node:util';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { row, scan } from '../../web/tests/browser/helpers.mjs';

const { values } = parseArgs({ options: { url: {type:'string'}, out: {type:'string'}, demo:{type:'boolean',default:false} } });
if (!values.url || !values.out) throw new Error('--url and --out are required');
const root = resolve(import.meta.dirname, '../..');
const out = resolve(values.out); mkdirSync(out,{recursive:true});
const hash = b => createHash('sha256').update(b).digest('hex');
const reference = JSON.parse(readFileSync(join(root,'studies/server-ocr/results/capture.json')));
const results = [];
const cases = values.demo ? [{name:'cord',mode:'ocr-all',schema:'receipt',total:60000}] : [
  {name:'mixed',mode:'native',schema:'invoice',total:100},
  {name:'mixed',mode:'ocr-missing',schema:'invoice',total:100},
  {name:'mixed',mode:'ocr-all',schema:'invoice',total:100},
  {name:'saved-form',mode:'ocr-all',schema:'invoice',total:100},
  {name:'cord',mode:'ocr-missing',schema:'receipt',total:60000,retry:true},
];
for (const [browserName,engine] of [['chromium',chromium],['firefox',firefox]]) {
 const browser=await engine.launch();
 try { for (const width of [1440,375]) {
  const context=await browser.newContext({viewport:{width,height:960},acceptDownloads:true});
  const page=await context.newPage(); page.setDefaultTimeout(30000);
  const audit={errors:[],external:[],csp:[]};
  page.on('pageerror',e=>audit.errors.push(String(e)));
  page.on('request',r=>{if(new URL(r.url()).origin!==new URL(values.url).origin && !r.url().startsWith('blob:'))audit.external.push(r.url());});
  await page.addInitScript(()=>{window.sourceCsp=[];addEventListener('securitypolicyviolation',e=>window.sourceCsp.push(e.violatedDirective));});
  for(const c of cases) {
   const key=`${browserName}-${width}-${c.name}-${c.mode}`;
   const directory=join(out,key); mkdirSync(directory,{recursive:true});
   if(!values.demo) {
    const list=await (await context.request.get(new URL('/api/documents',values.url).href)).json();
    for(const d of list.documents) expect((await context.request.delete(new URL(`/api/documents/${d.id}`,values.url).href)).status()).toBe(204);
   }
   await page.goto(values.demo?`${values.url}#cord-ocr`:values.url);
   if(!values.demo) {
    const pdf=c.name==='cord'?'examples/recorded/cord/cord-test-0000.pdf':c.name==='mixed'?'studies/server-ocr/fixtures/mixed-source.pdf':'studies/form-appearances/fixtures/covered-native-total.pdf';
    const fixture=c.name==='cord'?'examples/recorded/cord/fixture.json':`studies/server-ocr/fixtures/${c.name==='mixed'?'mixed-fixture':'form-hidden-claim'}.json`;
    await page.getByLabel('Text source',{exact:true}).selectOption(c.retry?'native':c.mode);
    await page.getByLabel('PDF document',{exact:true}).setInputFiles(join(root,pdf));
    if(c.retry) {
     await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();
     await expect(page.locator('#text-source-help')).toHaveText('Native text only; up to 64 pages.');
     await page.getByLabel('Text source',{exact:true}).selectOption(c.mode);
     await page.getByRole('button',{name:'Retry',exact:true}).click();
    }
    await expect(page.getByRole('button',{name:'Run extraction',exact:true})).toBeVisible();
    if(c.mode!=='native') await expect(page.getByRole('complementary',{name:'Document text source'})).toBeVisible();
    await page.getByLabel('Schema').selectOption(c.schema);
    await page.getByLabel('Fixture JSON',{exact:true}).setInputFiles(join(root,fixture));
    await page.getByRole('button',{name:'Run extraction',exact:true}).click();
   }
   const total=row(page,'total'); await expect(total).toBeVisible();
   const expected=reference.cases.find(r=>r.name===c.name && r.mode===c.mode);
   const original=expected.fields.find(f=>f.path==='total');
   await expect(total.locator('.status-chip')).toHaveAttribute('data-status',original.status);
   if(c.name==='saved-form') {
    await total.getByRole('button',{name:'Edit',exact:true}).click();
    await total.getByRole('textbox').fill('100');
    await total.getByRole('button',{name:'Save',exact:true}).click();
    await expect(total.locator('.field-value')).toHaveText('100.00');
   } else await total.getByRole('button',{name:'Approve',exact:true}).click();
   await expect(total.getByRole('button',{name:'Edit',exact:true})).toBeEnabled();
   await total.getByRole('button',{name:'Inspect total',exact:true}).click();
   if(width===375) await page.getByRole('button',{name:'Document',exact:true}).click();
   await expect(page.locator('#page-frame img')).toBeVisible();
   await page.locator('#page-frame img').evaluate(img=>img.decode());
   const source=page.getByRole('complementary',{name:'Document text source'});
   if(c.mode!=='native') {
    await expect(source).toContainText('Tesseract'.toLowerCase());
    if(c.name==='mixed' && c.mode==='ocr-missing') {
     await expect(source).toContainText('Mixed native/OCR text');
     await expect(source).toContainText('Page 2: OCR words');
     await page.getByRole('button',{name:'Previous page',exact:true}).click();
     await expect(source).toContainText('Page 1: native PDF words');
     await page.getByRole('button',{name:'Next page',exact:true}).click();
    }
   }
   if(c.name==='cord' && values.demo) await expect(source).toContainText('NAVER CLOVA');
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await scan(page);
   if(c.name==='cord' || c.name==='saved-form') {
    await page.evaluate(()=>document.fonts.ready);
    await page.locator('#page-frame img').evaluate(img=>img.decode());
    await page.screenshot({path:join(directory,'review.png'),fullPage:true});
   }
   if(width===375) await page.getByRole('button',{name:'Fields',exact:true}).click();
   const sourceText=c.mode==='native'?null:await source.innerText();
   const requests=[];const observe=r=>requests.push(r.url());
   page.on('request',observe); await context.setOffline(true);
   const downloads={}; let reviewed;
   for(const scope of ['reviewed','all']) {
    await page.getByLabel('Export',{exact:true}).selectOption(scope);
    let rows;
    for(const format of ['JSON','CSV','XLSX']) {
     const pending=page.waitForEvent('download');
     await page.getByRole('button',{name:`Export ${format}`,exact:true}).click();
     const download=await pending; const chunks=[];
     for await(const chunk of await download.createReadStream())chunks.push(chunk);
     const bytes=Buffer.concat(chunks);writeFileSync(join(directory,`${scope}.${format.toLowerCase()}`),bytes);
     downloads[`${scope}.${format}`]={bytes:bytes.length,sha256:hash(bytes)};
     if(format==='JSON') {
      rows=JSON.parse(bytes); if(scope==='reviewed'){reviewed=rows;expect(rows).toHaveLength(1);}
      for(const r of rows) {
       if(c.mode==='native'){expect(r.text_mode).toBeUndefined();expect(r.text_source).toBeUndefined();}
       else {expect(r.text_mode).toBe(c.mode);expect(typeof r.text_source).toBe('string');}
      }
     } else if(format==='CSV') {
      const header=bytes.toString().split('\r\n')[0].split(',');
      expect(header).toEqual(Object.keys(rows[0]));
      if(c.mode!=='native')expect(bytes.toString()).toContain('OCR: tesseract');
     } else {
      const parts=unzipSync(bytes);const xml=strFromU8(parts['xl/worksheets/sheet1.xml']);
      expect(xml).not.toMatch(/<f[ >]|hyperlink|externalLink/);
      const cells=await page.evaluate(xml=>{
       const d=new DOMParser().parseFromString(xml,'application/xml');
       if(d.querySelector('parsererror'))throw Error('Invalid workbook');
       return [...d.querySelectorAll('sheetData row')].map(r=>[...r.children].map(c=>{
        if(c.getAttribute('t')==='inlineStr')return c.querySelector('t')?.textContent??'';
        const v=c.querySelector('v')?.textContent;return v==null?null:c.getAttribute('t')==='b'?v==='1':Number(v);
       }));
      },xml);
      expect(cells).toEqual([Object.keys(rows[0]),...rows.map(r=>Object.values(r))]);
     }
    }
   }
   await context.setOffline(false);page.off('request',observe);expect(requests).toEqual([]);
   expect(reviewed[0]).toMatchObject({field:'total',value:c.total,original_value:original.value,verification_status:original.status});
   let archive;
   if(!values.demo) {
    const pending=page.waitForEvent('download'); await page.getByRole('button',{name:'Save archive',exact:true}).click();
    const saved=await pending;const path=join(directory,'review.zip');await saved.saveAs(path);
    const bytes=readFileSync(path), parts=unzipSync(bytes), manifest=JSON.parse(strFromU8(parts['manifest.json']));
    expect(manifest.version).toBe(c.mode==='native'?1:2);
    if(c.mode!=='native')expect(manifest.processing).toEqual({text_mode:c.mode});
    const list=await (await context.request.get(new URL('/api/documents',values.url).href)).json();
    for(const d of list.documents)await context.request.delete(new URL(`/api/documents/${d.id}`,values.url).href);
    await page.reload();await page.getByLabel('Review archive',{exact:true}).setInputFiles(path);
    await expect(row(page,'total').locator('.field-value')).toHaveText(c.total.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
    const sessions=await (await context.request.get(new URL('/api/documents',values.url).href)).json();
    const restored=await (await context.request.get(new URL(`/api/documents/${sessions.documents[0].id}/export.json?scope=reviewed`,values.url).href)).json();
    expect(restored).toEqual(reviewed);
    archive={version:manifest.version,sha256:hash(bytes),restoredIntoEmptyStore:true};
   }
   audit.csp.push(...await page.evaluate(()=>window.sourceCsp));
   expect(audit).toEqual({errors:[],external:[],csp:[]});
   results.push({profile:`${browserName}-${width}`,case:c.name,mode:c.mode,sourceText,downloads,reviewed,archive,audit:{...audit}});
   writeFileSync(join(out,'browser.json'),JSON.stringify({url:values.url,demo:values.demo,results},null,2)+'\n');
   process.stdout.write(`${key}: exports, original verdict, source${values.demo?'':', archive restore'} passed\n`);
  }
  await context.close();
 }} finally {await browser.close();}
}
