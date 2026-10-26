"use strict";
/** Real Chromium click/type/select interactions against current UI module; ALL API/model replies synthetic.
 * On Pi arm64, use the existing locally staged Chromium libs with a process-scoped
 * LD_LIBRARY_PATH if ldd reports missing libraries. NOT authenticated DEV E2E.
 */
const http = require('node:http');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const base = path.resolve(__dirname, '..');
const puppeteer = require(process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(process.env.HOME, '.npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer'));
const chrome = process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(process.env.HOME, '.cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome');
const html = `<!doctype html><html lang="es"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/odyssey_web/styles.css"></head>
  <body><main id="app"><h1>Odyssey · notas (banco sintético)</h1><button id="start">Modelo de notas</button><section id="schema-root"></section></main>
  <script type="module">
    import {createSchemaModel} from '/odyssey_web/schema-model.js';
    const calls = [];
    window.__calls = calls;
    const makePreview = (change, proposal_hash) => ({
      kind: 'schema_preview', revision: 0, next_revision: 1, proposal_hash,
      affected_type_id: change.operation === 'add_type' ? change.type.id : change.type_id,
      operation: change.operation,
      type_preview: change.operation === 'add_type' ? {...change.type, properties: change.type.properties.map(p=>({...p,required:false,filterable:true}))} :
        {id:change.type_id,name:'Persona',description:'Una persona',properties:[{...change.property,required:false,filterable:true}]}
    });
    const candidate = {operation:'add_type',type:{id:'juego',name:'Juego de mesa',description:'Juegos que tengo',examples:[],properties:[
      {id:'jugadores',description:'Número de jugadores',value_type:'string'},
      {id:'editorial',description:'Editorial',value_type:'string'}
    ]}};
    const proposed = makePreview(candidate, 'a'.repeat(64));
    const client = async (req) => {
      calls.push(structuredClone(req));
      if(req.operation==='schema_status') return {status:'ready',revision:0,can_confirm:true};
      if(req.operation==='schema_suggest') return {kind:'schema_suggestion',decision:'PROPOSE',message:'Propuesta inicial',change:candidate,preview:proposed};
      if(req.operation==='schema_preview') return makePreview(req.payload.change,'b'.repeat(64));
      if(req.operation==='schema_review') return {kind:'schema_review',proposal_hash:req.payload.proposal_hash,
        verdict:'CHECK',message:'Revisión final: comprueba la intención.',issues:['El número de jugadores debe ser entero.']};
      if(req.operation==='schema_confirm') return {status:'active',request_id:req.payload.request_id};
      if(req.operation==='schema_scan') return req.payload.action==='status'
        ? {kind:'schema_scan',status:'not_started'}
        : {kind:'schema_scan',status:'complete',scanned_paths:3,
           eligible_notes:2,skipped_existing_values:0,legacy_sources:1};
      throw new Error('Unexpected operation '+req.operation);
    };
    const panel = createSchemaModel({root:document.querySelector('#schema-root'),client,onActive:()=>{window.__active = true;}});
    document.querySelector('#start').addEventListener('click',()=>panel.open({kind:'new'}));
    window.__ready = true;
  </script></body></html>`;
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url,'http://localhost').pathname;
  if (pathname === '/') {res.writeHead(200, {'content-type':'text/html; charset=utf-8'});res.end(html);return;}
  const files = new Set(['/odyssey_web/schema-model.js','/odyssey_web/schema-scan.js','/odyssey_web/notes-client.js','/odyssey_web/client.js','/odyssey_web/styles.css']);
  if (!files.has(pathname)) {res.writeHead(404);res.end();return;}
  const file = path.join(base, pathname.slice(1));
  res.writeHead(200,{'content-type':file.endsWith('.css')?'text/css':'text/javascript'});
  res.end(fs.readFileSync(file));
});
const profiles = [['desktop',1280,920],['mobile',390,844]];
(async () => {
  let browser;
  const result={kind:'schema_editor_real_chromium_mock_service',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:base,encoding:'utf8'}).trim(),modelProvider:'MOCK',authenticatedDevApp:false,profiles:{},pass:false};
  try {
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const url=`http://127.0.0.1:${server.address().port}/`;
    browser=await puppeteer.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-background-networking']});
    for (const [label,width,height] of profiles) {
      const page=await browser.newPage();await page.setViewport({width,height});
      const errors=[];page.on('pageerror',e=>errors.push(String(e)));
      await page.goto(url,{waitUntil:'networkidle0'});
      await page.waitForFunction(()=>window.__ready===true);
      await page.click('#start');
      await page.waitForSelector('.schema-model-form:not([hidden])');
      await page.type('.schema-model-assistant textarea','Quiero fichas para mis juegos de mesa y su número de jugadores');
      await page.click('.schema-model-ask');
      await page.waitForFunction(()=>document.querySelector('.schema-model-preview')?.hidden===false);
      const initiallyBlocked=await page.$eval('.schema-model-confirm',el=>el.disabled);
      await page.click('.schema-model-review');
      await page.waitForSelector('.schema-model-property-row');
      const rowsBefore=await page.$$('.schema-model-property-row');
      await (await rowsBefore[0].$('.schema-model-property-type')).select('integer');
      const removeButtons = await page.$$('.schema-model-property-remove');
      await removeButtons[1].click();
      await page.click('.schema-model-property-add');
      const rows=await page.$$('.schema-model-property-row');
      const last=rows[rows.length-1];
      const inputs=await last.$$('.schema-model-input');
      await inputs[0].click();
      await inputs[0].type('edad recomendada');
      await inputs[1].click();
      await inputs[1].type('Edad mínima en años');
      await (await last.$('select')).select('integer');
      await page.click('.schema-model-propose');
      await page.waitForFunction(()=>document.querySelector('.schema-model-preview')?.hidden===false);
      const beforeReview=await page.$eval('.schema-model-confirm',el=>el.disabled);
      await page.click('.schema-model-ai-review');
      await page.waitForFunction(()=>document.querySelector('.schema-model-final-review')?.textContent.includes('El número de jugadores debe ser entero.'));
      const afterReview=await page.$eval('.schema-model-confirm',el=>el.disabled);
      await page.click('.schema-model-confirm');
      await page.waitForFunction(()=>window.__active===true);
      await page.waitForFunction(()=>document.querySelector('.schema-model-scan-status')?.textContent.includes('No se ha iniciado'));
      const autoScanCount=await page.evaluate(()=>window.__calls.filter(c=>c.operation==='schema_scan' && c.payload.action==='advance').length);
      await page.click('.schema-model-scan-advance');
      await page.waitForFunction(()=>document.querySelector('.schema-model-scan-status')?.textContent.includes('Lectura finalizada'));

      const evidence=await page.evaluate(()=>({
        calls:window.__calls.map(c=>c.operation),
        changed:window.__calls.find(c=>c.operation==='schema_preview')?.payload.change,
        reviewedHash:window.__calls.find(c=>c.operation==='schema_review')?.payload.proposal_hash,
        confirmedHash:window.__calls.find(c=>c.operation==='schema_confirm')?.payload.proposal_hash,
        confirmedActorIntent:window.__calls.filter(c=>c.operation==='schema_confirm').length,
        finalMessage:document.querySelector('.schema-model-message')?.textContent,
        scanCalls:window.__calls.filter(c=>c.operation==='schema_scan'),
        scanText:document.querySelector('.schema-model-scan-status')?.textContent,
        overflow:document.documentElement.scrollWidth>innerWidth+3
      }));
      const properties=evidence.changed?.type?.properties||[];
      const pass=initiallyBlocked && beforeReview && !afterReview &&
        evidence.calls.filter(c=>c!=='schema_scan').join(',')==='schema_status,schema_suggest,schema_preview,schema_review,schema_confirm' &&
        autoScanCount===0 && evidence.scanCalls.length===2 &&
        evidence.scanCalls[0].payload.action==='status' &&
        evidence.scanCalls[1].payload.action==='advance' &&
        evidence.scanCalls[1].payload.scan_kind==='discover_type' &&
        evidence.scanCalls[1].payload.target_type_id==='juego_de_mesa' &&
        evidence.scanText.includes('3 notas examinadas') && evidence.scanText.includes('1 con texto antiguo') &&
        properties.length===2 && properties.every(p=>p.value_type==='integer') &&
        evidence.reviewedHash===evidence.confirmedHash && evidence.confirmedActorIntent===1 &&
        !evidence.overflow && errors.length===0;
      result.profiles[label]={...evidence,initiallyBlocked,beforeReview,afterReview,autoScanCount,errors,pass};
      await page.close();
    }
    result.pass=Object.values(result.profiles).every(v=>v.pass);
    console.log('SCHEMA_EDITOR_CHROMIUM='+JSON.stringify(result));
    if (!result.pass) process.exitCode=2;
  } catch(e) {result.error=String(e.stack||e).slice(0,850);console.log('SCHEMA_EDITOR_CHROMIUM='+JSON.stringify(result));process.exitCode=1;}
  finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})();
