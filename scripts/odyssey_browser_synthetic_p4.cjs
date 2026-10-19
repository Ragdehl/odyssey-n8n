"use strict";
const path=require("node:path");
const puppeteer=require(process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(process.env.HOME||"/home/ragdehl",
    ".npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer"));
const CHROME=process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(process.env.HOME||"/home/ragdehl",
   ".cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome");
(async ()=>{
 let browser;
 let checkpoint="starting";
 let page;
 try {
  if(!process.env.ODYSSEY_SYNTHETIC_BROWSER_URL ||
     !/^http:\/\/127\.0\.0\.1:\d+\/$/.test(process.env.ODYSSEY_SYNTHETIC_BROWSER_URL))
   throw Error("Only ephemeral localhost synthetic browser is allowed");
  browser=await puppeteer.launch({
    executablePath:CHROME,headless:true,
    args:["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
          "--disable-background-networking"]
  });
  page=await browser.newPage();
  const desktop=process.env.ODYSSEY_SYNTHETIC_VIEWPORT==="desktop";
  await page.setViewport({width:desktop?1280:390,height:desktop?960:844,deviceScaleFactor:1});
  const jsErrors=[];
  page.on("pageerror",error=>jsErrors.push(String(error.message).slice(0,120)));
  const bad=await page.goto(process.env.ODYSSEY_SYNTHETIC_BROWSER_URL,
    {waitUntil:"domcontentloaded",timeout:15000});
  if(bad.status()!==200)throw Error("Synthetic frontend HTTP failed");
  await page.waitForFunction(()=>!!document.querySelector("#request-input")
    && !!document.querySelector("#odyssey-form")
    && document.querySelector("#interaction")?.childElementCount===0,{timeout:10000});
  await page.type("#request-input",process.env.ODYSSEY_SYNTHETIC_SOURCE,{delay:2});
  await page.click("#send-button");
  checkpoint="await_initial_response";
  await page.waitForFunction(()=>document.querySelector(".message-acknowledgement")
    && document.querySelectorAll(".detail-button").length===1
    && document.querySelectorAll(".note-set-button").length===1,
    {timeout:22000});
  const before=await page.evaluate(()=>({
    userMessages:document.querySelectorAll(".message-user").length,
    acknowledgements:document.querySelectorAll(".message-acknowledgement").length,
    details:document.querySelectorAll(".detail-button").length,
    noteButtons:document.querySelectorAll(".note-set-button").length,
    confirmationVisible:document.querySelector(".message-odyssey .message-text")?.textContent==="Guardado"
  }));
  await page.click(".detail-button");
  await page.waitForFunction(()=>document.querySelector("#request-detail-sheet")?.open,{timeout:3000});
  const detail=await page.evaluate(()=>{
    const root=document.querySelector("#request-detail-sheet");
    const content=document.querySelector("#request-detail-content")?.innerText||"";
    const sample={
      svgCount:root?.querySelectorAll("svg").length||0,
      sourceFlow:/Estado de ruta:/.test(content),
      writeReceipts:(content.match(/Resultado de escritura Core registrado:/g)||[]).length,
      diagnosticRejected:content.includes("El navegador rechazó sus datos técnicos"),
    };
    root?.close();
    return sample;
  });
  checkpoint="reload_before_details";
  await page.reload({waitUntil:"domcontentloaded",timeout:12000});
  await page.waitForFunction(()=>document.querySelectorAll(".detail-button").length===1
    && document.querySelectorAll(".note-set-button").length===1,
    {timeout:13000});
  const after=await page.evaluate(()=>({
    userMessages:document.querySelectorAll(".message-user").length,
    acknowledgements:document.querySelectorAll(".message-acknowledgement").length,
    details:document.querySelectorAll(".detail-button").length,
    noteButtons:document.querySelectorAll(".note-set-button").length,
    confirmationVisible:document.querySelector(".message-odyssey .message-text")?.textContent==="Guardado"
  }));
  checkpoint="verify_graph_after_reload";
  await page.click(".detail-button");
  await page.waitForFunction(()=>document.querySelector("#request-detail-sheet")?.open,
    {timeout:3000});
  const reloadedDetail=await page.evaluate(()=>{
    const root=document.querySelector("#request-detail-sheet");
    const body=document.querySelector("#request-detail-content")?.innerText||"";
    const output={
      svgCount:root?.querySelectorAll("svg").length||0,
      writeReceipts:(body.match(/Resultado de escritura Core registrado:/g)||[]).length,
      diagnosticRejected:body.includes("El navegador rechazó sus datos técnicos")
    };
    root?.close();
    return output;
  });
  checkpoint="open_note_snapshot";
  await page.click(".note-set-button");
  await page.waitForFunction(()=>!document.querySelector("#notes-surface")?.hidden,
    {timeout:10000});
  await page.waitForFunction(()=>document.querySelector("#notes-list")?.children.length>0,
    {timeout:11000});
  const notes=await page.evaluate(()=>({
    surfaceVisible:document.querySelector("#notes-surface")?.hidden===false,
    resultNodes:document.querySelector("#notes-list")?.children.length||0
  }));
  const output={
    pass:before.userMessages===1 && before.acknowledgements===1 &&
      before.details===1 && before.noteButtons===1 &&
      before.userMessages===after.userMessages &&
      before.details===after.details && before.noteButtons===after.noteButtons &&
      before.confirmationVisible===true && after.confirmationVisible===true &&
      detail.svgCount>0 && detail.sourceFlow && detail.writeReceipts===2 &&
      !detail.diagnosticRejected && reloadedDetail.svgCount>0 &&
      reloadedDetail.writeReceipts===detail.writeReceipts &&
      !reloadedDetail.diagnosticRejected &&
      notes.surfaceVisible && notes.resultNodes>=2 &&
      jsErrors.length===0,
    before,after,detail,reloadedDetail,notes,jsErrorsCount:jsErrors.length,
    actor:"synthetic_only",messages_sent:1
  };
  console.log(JSON.stringify(output));
  if(!output.pass)process.exitCode=2;
 } catch(error){
  let info=null;
  try{if(page) info=await page.evaluate(()=>({turns:document.querySelector("#interaction")?.childElementCount||0,detailButtons:document.querySelectorAll(".detail-button").length,noteButtons:document.querySelectorAll(".note-set-button").length,appErrors:document.querySelectorAll(".message-error").length}));}catch{}
  console.log(JSON.stringify({pass:false,checkpoint,info,category:String(error.message).slice(0,240)}));
  process.exitCode=1;
 } finally {if(browser) await browser.close();}
})();
