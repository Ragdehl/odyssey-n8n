/* E5 synthetic Event UI check against DEV only; no writes allowed. */
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const here=path.resolve(__dirname);
const home=process.env.HOME||'/home/ragdehl';
const puppeteerPath=process.env.ODYSSEY_PUPPETEER_MODULE ||
 path.join(home,'.npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer');
const executablePath=process.env.ODYSSEY_CHROMIUM_BINARY ||
 path.join(home,'.cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome');
const expected=process.env.ODYSSEY_E5_EVENT_LABEL||'';
const day=process.env.ODYSSEY_E5_DAY||'';
const shouldExist=process.env.ODYSSEY_E5_VISIBLE==='1';
if(!expected||!/^2026-10-(29|30)$/.test(day)) throw Error('Bounded E5 synthetic browser settings required');
(async()=>{
 let browser,proxy;
 try {
  const {startReadonlyDevProxy}=await import(pathToFileURL(path.join(here,'odyssey_dev_readonly_proxy.mjs')).href);
  proxy=await startReadonlyDevProxy();
  const puppeteer=require(puppeteerPath);
  browser=await puppeteer.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const rows=[];
  for(const [profile,width,height] of [['mobile',390,844],['desktop',1280,960]]) {
   const page=await browser.newPage();
   await page.setViewport({width,height,deviceScaleFactor:1});
   const errors=[];
   page.on('pageerror',e=>errors.push(String(e.message).slice(0,180)));
   const response=await page.goto(proxy.url,{waitUntil:'domcontentloaded',timeout:30000});
   await page.waitForFunction(()=>document.querySelector('#interaction')?.childElementCount>0,{timeout:30000});
   await page.evaluate(()=>document.querySelector('#calendar-tab')?.click());
   await page.waitForFunction(()=>document.querySelectorAll('.calendar-day-cell').length>0,{timeout:30000});
   await page.waitForFunction(()=>document.querySelector('#calendar-status')?.textContent!=='Cargando…',{timeout:30000});
   const before=await page.evaluate(({day,label})=>{
    const grid=document.querySelector('#calendar-grid');
    const cell=[...grid.querySelectorAll('.calendar-day-cell')].find(x=>x.getAttribute('data-date')===day);
    // Source notes are intentionally still shown as capture on their
    // creation date after cancellation. Only test the occurrence DATE cell.
    const snapshot=cell?.textContent||'';
    return {gridExists:!!grid,cells:grid?.querySelectorAll('.calendar-day-cell').length||0,
            monthTitle:document.querySelector('#calendar-month-title')?.textContent,
            visible:snapshot.includes(label),cellFound:!!cell};
   },{day,label:expected});
   const backend=await page.evaluate(async({day,label})=>{
    const response=await fetch('/api/calendar',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({operation:'day',date:day})});
    const data=await response.json();
    return {http:response.status,kind:data.kind,
      matching:(data.events||[]).filter(x=>x.source?.name===label).length};
   },{day,label:expected});
   await page.reload({waitUntil:'domcontentloaded',timeout:30000});
   await page.waitForFunction(()=>document.querySelector('#interaction')?.childElementCount>0,{timeout:30000});
   await page.evaluate(()=>document.querySelector('#calendar-tab')?.click());
   await page.waitForFunction(()=>document.querySelectorAll('.calendar-day-cell').length>0,{timeout:30000});
   const after=await page.evaluate(({day,label})=>{
     const cell=[...document.querySelectorAll('#calendar-grid .calendar-day-cell')]
       .find(x=>x.getAttribute('data-date')===day);
     return cell?.textContent?.includes(label)||false;
   },{day,label:expected});
   const pass=response.status()===200 && backend.http===200 &&
    backend.kind==='calendar_day' && backend.matching===(shouldExist?1:0) &&
    before.cellFound && before.visible===shouldExist && after===shouldExist && errors.length===0;
   rows.push({profile,pass,calendarDayMatches:backend.matching,
     uiVisible:before.visible,reloadVisible:after,cells:before.cells,exceptions:errors.length});
   await page.close();
  }
  const pass=rows.every(x=>x.pass);
  console.log('E5_DEV_CHROMIUM='+JSON.stringify({pass,shouldExist,rows}));
  if(!pass)process.exitCode=2;
 } catch(e){console.log('E5_DEV_CHROMIUM='+JSON.stringify({pass:false,error:String(e.message).slice(0,240)}));process.exitCode=1;}
 finally{
  if(browser)await browser.close();
  if(proxy?.server)await new Promise(resolve=>proxy.server.close(resolve));
 }
})();
