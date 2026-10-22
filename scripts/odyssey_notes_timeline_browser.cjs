"use strict";
const fs=require("node:fs"),path=require("node:path"),{pathToFileURL}=require("node:url");
const puppeteer=require(process.env.ODYSSEY_PUPPETEER_MODULE || path.join(process.env.HOME,".npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer"));
const Chrome=process.env.ODYSSEY_CHROMIUM_BINARY || path.join(process.env.HOME,".cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome");
const root=path.resolve(__dirname,"..");
const out=process.env.ODYSSEY_SCREENSHOT_DIR || "/tmp/odyssey-notes-timeline-browser";
const report={profiles:{},pass:false};let browser,proxy;
(async()=>{
 try{
  fs.mkdirSync(out,{recursive:true,mode:0o700});
  proxy=await(await import(pathToFileURL(path.join(root,"scripts/odyssey_dev_readonly_proxy.mjs")).href)).startReadonlyDevProxy();
  browser=await puppeteer.launch({executablePath:Chrome,headless:true,args:["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-background-networking"]});
  for(const [name,width,height] of [["mobile",390,844],["desktop",1280,960]]){
   const page=await browser.newPage();await page.setViewport({width,height,deviceScaleFactor:1});
   const errors=[];
   page.on("pageerror",e=>errors.push(e.message));
   if(process.env.ODYSSEY_USE_LOCAL_ASSETS==="1") {
   await page.setRequestInterception(true);
   page.on("request",req=>{
     const url=new URL(req.url());const file=path.basename(url.pathname);
     if(["notes.js","styles.css"].includes(file)){
       req.respond({status:200,contentType:file.endsWith(".css")?"text/css":"application/javascript",body:fs.readFileSync(path.join(root,"odyssey_web",file))});
     }else req.continue();
   });
   }
   const loaded=await page.goto(proxy.url,{waitUntil:"domcontentloaded",timeout:30000});
   await page.waitForSelector("#notes-tab",{timeout:20000});
   await page.click("#notes-tab");
   await page.waitForFunction(()=>document.querySelector("#notes-list")?.children.length>0,{timeout:30000});
   let rows=await page.evaluate(()=>[...document.querySelectorAll("#notes-list .note-row")].map(x=>x.textContent).slice(0,8));
   let found=await page.evaluate(()=>[...document.querySelectorAll("#notes-list .note-row")].some(x=>x.textContent.includes("Odyssey DEV Synthetic User")));
   if(!found){
     await page.evaluate(()=>{let el=document.querySelector("#notes-search");el.value="Odyssey DEV Synthetic User";el.dispatchEvent(new Event("input",{bubbles:true}));});
     await page.evaluate(()=>document.querySelector("#notes-search-form")?.requestSubmit());
     await page.waitForFunction(()=>[...document.querySelectorAll("#notes-list .note-row")].some(x=>x.textContent.includes("Odyssey DEV Synthetic User")),{timeout:35000});
   }
   await page.evaluate(()=>[...document.querySelectorAll("#notes-list .note-row")].find(x=>x.textContent.includes("Odyssey DEV Synthetic User")).click());
   await page.waitForFunction(()=>document.querySelector("#note-detail")?.hidden===false,{timeout:20000});
   await page.waitForFunction(()=>document.querySelectorAll("#note-detail .note-fact-incoming").length>0,{timeout:30000});
   const ui=await page.evaluate(()=>{
     const dates=[...document.querySelectorAll("#note-detail .note-fact-group")].map(g=>g.dataset.date);
     const incoming=[...document.querySelectorAll("#note-detail .note-fact-incoming")];
     const origins=[...document.querySelectorAll("#note-detail .note-fact-origin")];
     return {dates,dayGroups:dates.length,incoming:incoming.length,
       labels:origins.map(x=>x.textContent).slice(0,4),
       oldBacklinks:document.querySelectorAll("#note-detail .note-backlinks").length,
       oldAdded:document.querySelector("#note-detail")?.textContent.includes("Añadido"),
       metaClosed:!document.querySelector("#note-detail .note-metadata")?.open,
       noteName:document.querySelector("#note-detail .note-view-header h2")?.textContent,
       scrollWidth:document.querySelector("#note-detail").scrollWidth,
       clientWidth:document.querySelector("#note-detail").clientWidth,
     };
   });
   await page.screenshot({path:out+"/"+name+"-note.png",fullPage:false});
   const good=loaded.status()===200&&ui.dayGroups>0&&ui.incoming>0&&ui.oldBacklinks===0&&!ui.oldAdded&&ui.metaClosed&&
     new Set(ui.dates).size===ui.dates.length&&ui.scrollWidth<=ui.clientWidth+2&&errors.length===0;
   report.profiles[name]={...ui,previewRows:rows,errors,pass:good}; await page.close();
  }
  report.pass=Object.values(report.profiles).every(v=>v.pass);
  console.log("ODYSSEY_TIMELINE_PROTOTYPE="+JSON.stringify(report));
  if(!report.pass)process.exitCode=2;
 }catch(e){report.error=String(e.stack||e).slice(0,850);console.log("ODYSSEY_TIMELINE_PROTOTYPE="+JSON.stringify(report));process.exitCode=2}
 finally{if(browser)await browser.close();if(proxy?.server)await new Promise(r=>proxy.server.close(r));}
})();
