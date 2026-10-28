/* Persistent read-only DEV browser gate; never sends messages or mutations. */
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {performance}=require('node:perf_hooks');
const root=path.resolve(__dirname);
const home=process.env.HOME||'/home/ragdehl';
const puppeteerPath=process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(home,'.npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer');
const executablePath=process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(home,'.cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome');
(async()=>{
 let browser, proxy;
 const report={kind:'readonly_dev_browser',no_new_writes:true,
   cloudflare_access_checked:false,live_p4_browser_write_checked:false,
   scenarios:{}, errors:[]};
 try{
  ({startReadonlyDevProxy:proxy} = await import(pathToFileURL(path.join(root,'odyssey_dev_readonly_proxy.mjs')).href));
  const server=await proxy();
  proxy=server;
  const puppeteer=require(puppeteerPath);
  browser=await puppeteer.launch({
   executablePath,headless:true,
   args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-background-networking']
  });
  let originalCommit=null;
  for(const [profile,width,height] of [['mobile',390,844],['desktop',1280,960]]){
   const page=await browser.newPage();
   await page.setViewport({width,height,deviceScaleFactor:1});
   const errors=[];
   page.on('pageerror',e=>errors.push(String(e.message).slice(0,250)));
   const res=await page.goto(proxy.url,{waitUntil:'domcontentloaded',timeout:25000});
   await page.waitForFunction(()=>document.querySelector('#interaction')?.childElementCount>0,{timeout:25000});
   const before=await page.evaluate(()=>({
    commit:globalThis.ODYSSEY_DEPLOYMENT?.commit,
    turns:document.querySelector('#interaction')?.childElementCount||0,
    details:document.querySelectorAll('.detail-button').length
   }));
   if(!originalCommit)originalCommit=before.commit;
   const graphical=await page.evaluate(()=>{
     const buttons=[...document.querySelectorAll('.detail-button')];
     let drawings=0, coreReceipts=0, flows=0, dupes=0, stale=0;
     for(const btn of buttons) {
       btn.click();
       const sheet=document.querySelector('#request-detail-sheet');
       const body=document.querySelector('#request-detail-content')?.innerText||'';
       const writes=body.match(/Resultado de escritura Core registrado:[^\n]*/g)||[];
       if(sheet?.open===true&&sheet.querySelectorAll('svg').length>0)drawings++;
       coreReceipts+=writes.length;
       if(/Estado de ruta:/.test(body))flows++;
       if(new Set(writes).size !== writes.length)dupes++;
       if(body.includes('es anterior al registro'))stale++;
       if(sheet?.open)sheet.close();
     }
     return {checked:buttons.length,renderedWithSvg:drawings,coreReceipts,routeFlows:flows,
       duplicateReceiptViews:dupes,falseLegacyWarnings:stale};
   });
   // Exercise visible Notes and every Calendar layout. A pressed tab alone
   // is not evidence of loaded calendar data: wait for the requested grid.
   const navigation={notesRendered:false,calendarModes:[],chatPreserved:false};
   await page.click('#notes-tab');
   await page.waitForFunction(()=>!document.querySelector('#notes-surface')?.hidden,{timeout:15000});
   await page.waitForFunction(()=>document.querySelector('#notes-list')?.childElementCount>0,{timeout:20000});
   navigation.notesRendered=true;
   // Open the deployed schema editor by a user-visible click, without suggesting,
   // proposing or confirming anything. The only new allowed operation is status.
   await page.click('.notes-create-type-button');
   await page.waitForFunction(()=>{
     const sheet=document.querySelector('.schema-model-sheet');
     const form=sheet?.querySelector('.schema-model-form');
     const status=sheet?.querySelector('.schema-model-message')?.textContent||'';
     return sheet&&!sheet.hidden&&(/Describe el cambio|preparar y revisar/.test(status)||
       /no está disponible|no está listo/.test(status));
   },{timeout:15000});
   navigation.schemaEditor=await page.evaluate(()=>{
     const sheet=document.querySelector('.schema-model-sheet');
     const message=sheet?.querySelector('.schema-model-message')?.textContent||'';
     const form=sheet?.querySelector('.schema-model-form');
     return {opened:!!sheet&&!sheet.hidden,formVisible:!!form&&!form.hidden,
       unavailable:/no está disponible|no está listo/.test(message)};
   });
   await page.click('.schema-model-close');
   await page.click('#notes-calendar-tab');
   await page.waitForFunction(()=>!document.querySelector('#calendar-surface')?.hidden,{timeout:15000});
   for(const mode of ['month','7','3','1']){
    await page.click('#calendar-view-'+mode);
    await page.waitForFunction(mode=>{
     const status=document.querySelector('#calendar-status')?.textContent||'';
     const grid=document.querySelector(mode==='month'?'#calendar-grid':'#calendar-schedule-grid');
     const ready=grid?.childElementCount>0&&!status&&
       (mode==='month'||grid.classList.contains('calendar-schedule-'+mode));
     return ready||/No se ha podido|no está disponible/.test(status);
    },{timeout:20000},mode);
    const displayed=await page.evaluate(mode=>{
     const status=document.querySelector('#calendar-status')?.textContent||'';
     const grid=document.querySelector(mode==='month'?'#calendar-grid':'#calendar-schedule-grid');
     return !status&&grid?.childElementCount>0&&
       (mode==='month'||grid.classList.contains('calendar-schedule-'+mode));
    },mode);
    navigation.calendarModes.push({mode,rendered:!!displayed});
   }
   await page.click('#calendar-chat-tab');
   navigation.chatPreserved=(await page.$eval('#interaction',el=>el.childElementCount))===before.turns;
   navigation.pass=navigation.notesRendered&&navigation.schemaEditor?.opened&&
     navigation.schemaEditor?.formVisible&&!navigation.schemaEditor?.unavailable&&navigation.chatPreserved&&
     navigation.calendarModes.length===4&&navigation.calendarModes.every(v=>v.rendered);
   await page.reload({waitUntil:'domcontentloaded',timeout:25000});
   await page.waitForFunction(()=>document.querySelector('#interaction')?.childElementCount>0,{timeout:25000});
   const after=await page.evaluate(()=>({
     turns:document.querySelector('#interaction')?.childElementCount||0,
     details:document.querySelectorAll('.detail-button').length
   }));
   report.scenarios[profile]={
    http:res.status(),before,after,graphical,navigation,exceptions:errors,
    pass:res.status()===200 && before.turns>0 && before.details>0 &&
      before.turns===after.turns && before.details===after.details &&
      navigation.pass &&
      graphical.renderedWithSvg===graphical.checked &&
      graphical.duplicateReceiptViews===0&&graphical.falseLegacyWarnings===0 &&
      errors.length===0
   };
   await page.close();
  }
  report.deployedCommit=originalCommit;
  const probe=async(url,op)=>{
    const raw=await fetch(new URL(url,proxy.url),{method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({operation:op,note_id:'fake-readonly-test'})});
    return raw.status;
  };
  report.denialProof={
    createRequest:await probe('/api/request','execute'),
    deleteNote:await probe('/api/notes','delete_note'),
    changeTask:await probe('/api/notes','task_status'),
    appendTurn:await probe('/api/conversation','turn')
  };
  report.proxyRequests={...proxy.stats};
  report.pass=Object.values(report.scenarios).every(x=>x.pass) &&
    Object.values(report.denialProof).every(code=>code===403) &&
    proxy.stats.denied>=4;
  console.log(JSON.stringify(report,null,2));
  if(!report.pass)process.exitCode=2;
 } catch(err){console.log(JSON.stringify({error:String(err.message).slice(0,400)}));process.exitCode=1;}
 finally {
   if(browser)await browser.close();
   if(proxy?.server)await new Promise(resolve=>proxy.server.close(resolve));
 }
})();
