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
  const unauth=await page.goto(process.env.ODYSSEY_SYNTHETIC_BROWSER_URL,
    {waitUntil:"domcontentloaded",timeout:15000});
  if(unauth.status()!==403)throw Error("Unauthenticated browser request was accepted");
  await page.setCookie({name:"odyssey_test_auth",value:process.env.ODYSSEY_SYNTHETIC_AUTH,
    url:process.env.ODYSSEY_SYNTHETIC_BROWSER_URL,httpOnly:true,sameSite:"Strict"});
  const bad=await page.goto(process.env.ODYSSEY_SYNTHETIC_BROWSER_URL,
    {waitUntil:"domcontentloaded",timeout:15000});
  if(bad.status()!==200)throw Error("Synthetic frontend HTTP failed");
  await page.waitForFunction(()=>!!document.querySelector("#request-input")
    && !!document.querySelector("#odyssey-form")
    && document.querySelector("#interaction")?.childElementCount===0,{timeout:10000});
  await page.type("#request-input",process.env.ODYSSEY_SYNTHETIC_SOURCE,{delay:2});
  const userRequestStart=performance.now();
  await page.click("#send-button");
  checkpoint="progress_donut";
  await page.waitForFunction(()=>{
    const bar=document.querySelector('.processing-donut[role="progressbar"]');
    return bar && bar.getAttribute("aria-valuemin")==="0" &&
      bar.getAttribute("aria-valuemax")==="100" &&
      bar.querySelector(".processing-donut-value") &&
      bar.querySelector(".processing-percent");
  }, {timeout:10000});
  const progressDonut=await page.evaluate(()=>{
    const bar=document.querySelector('.processing-donut[role="progressbar"]');
    const percent=Number(bar?.getAttribute("aria-valuenow"));
    return {present:!!bar,valid:Number.isFinite(percent)&&percent>=0&&percent<=100,
      percent,displayed:bar?.querySelector('.processing-percent')?.textContent};
  });
  // Collect REAL DOM updates over the asynchronous request, not merely the
  // initial 0% rendered before the server has emitted a progress milestone.
  await page.evaluate(()=>{
    const values=[0];
    const sample=()=>{
      const bar=document.querySelector('.processing-donut[role="progressbar"]');
      if(!bar)return;
      const n=Number(bar.getAttribute("aria-valuenow"));
      const shown=bar.querySelector(".processing-percent")?.textContent;
      if(Number.isInteger(n)&&n>=0&&n<=100&&String(n)===shown&&values.at(-1)!==n)
        values.push(n);
    };
    window.__e4ProgressValues=values;
    window.__e4ProgressWatcher=new MutationObserver(sample);
    window.__e4ProgressWatcher.observe(document.querySelector("#interaction"),
      {attributes:true,subtree:true,childList:true,characterData:true});
    sample();
  });
  checkpoint="await_initial_response";
  await page.waitForFunction(()=>(document.querySelector(".message-acknowledgement")
    && document.querySelectorAll(".detail-button").length===1
    && document.querySelectorAll(".note-set-button").length===1)
    || document.querySelector(".message-error"), {timeout:180000});
  if(await page.$(".message-error"))throw Error("Browser received an application error");
  // User-perceived request latency excludes harness setup, UI inspection and replay.
  const userRequestSeconds=Math.round((performance.now()-userRequestStart)/10)/100;
  const progressTrace=await page.evaluate(()=>{
    window.__e4ProgressWatcher?.disconnect();
    const observed=window.__e4ProgressValues||[];
    return {observed:observed.slice(0,32),advanced:observed.some(n=>n>0),
      monotonic:observed.every((n,i)=>i===0||n>=observed[i-1])};
  });
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
  const expectedNames=JSON.parse(process.env.ODYSSEY_E4_EXPECTED_PERSONS||"[]");
  if(!Array.isArray(expectedNames)||!expectedNames.length||
     expectedNames.some(name=>typeof name!=="string"||!name.trim()))
    throw Error("Invalid expected synthetic Person names");
  checkpoint="verify_result_note_types";
  await page.waitForFunction((names)=>{
    const task=document.querySelectorAll('#notes-list .notes-type-group[data-type="task"] .note-row');
    const persons=Array.from(document.querySelectorAll('#notes-list .notes-type-group[data-type="person"] .note-row'));
    return task.length===1 && names.every(name=>persons.some(row=>row.textContent.includes(name)));
  },{timeout:12000},expectedNames);
  const taskName=await page.evaluate(()=>{
    const title=document.querySelector('#notes-list .notes-type-group[data-type="task"] .note-row strong');
    return Array.from(title?.childNodes||[]).filter(node=>node.nodeType===Node.TEXT_NODE)
      .map(node=>node.textContent||"").join("").trim();
  });
  if(!taskName||taskName.length>200)throw Error("Task absent from notes snapshot");
  // A matching row from the PREVIOUS snapshot does not prove a real search.
  // Correlate the actual /api/notes local-query HTTP response to the typed
  // query, then demand a newer DOM render (not merely matching stale text).
  const queryObservations=[];
  async function verifyFreshNotesSearch(query, type) {
    const beforeRender=await page.evaluate(()=>{
      const root=document.querySelector("#notes-list");
      if(!root)throw Error("Missing Notes list");
      if(!window.__e4ListMutationObserver){
        window.__e4ListMutationCount=0;
        window.__e4ListMutationObserver=new MutationObserver(
          ()=>{window.__e4ListMutationCount++;}
        );
        window.__e4ListMutationObserver.observe(root,
          {childList:true,subtree:true,characterData:true});
      }
      return window.__e4ListMutationCount;
    });
    const exactResponse=page.waitForResponse(response=>{
      if(!response.ok() || !response.url().includes("/api/notes"))return false;
      let body;
      try{body=JSON.parse(response.request().postData()||"{}");}catch{return false;}
      return body.operation==="query" && body.mode==="local" && body.query===query;
    },{timeout:20000});
    await page.evaluate(name=>{
      const field=document.querySelector("#notes-search");
      field.value=name;
      field.dispatchEvent(new Event("input",{bubbles:true}));
    },query);
    const response=await exactResponse;
    if(!response.ok())throw Error("E4 Notes search API error");
    await page.waitForFunction(({name,kind,counter})=>{
      const notes=document.querySelectorAll(
        '#notes-list .notes-type-group[data-type="'+kind+'"] .note-row');
      const status=document.querySelector("#notes-status")?.textContent||"";
      return (window.__e4ListMutationCount||0)>counter &&
        !/Cargando|Buscando|error|no se ha podido/i.test(status) &&
        Array.from(notes).some(row=>row.textContent.includes(name));
    },{timeout:20000},{name:query,kind:type,counter:beforeRender});
    const observed=await page.evaluate(({name,kind})=>({
      allRows:document.querySelectorAll("#notes-list .note-row").length,
      kindRows:document.querySelectorAll(
        '#notes-list .notes-type-group[data-type="'+kind+'"] .note-row').length,
      matchRows:Array.from(document.querySelectorAll(
        '#notes-list .notes-type-group[data-type="'+kind+'"] .note-row'
      )).filter(row=>row.textContent.includes(name)).length,
      status:document.querySelector("#notes-status")?.textContent||"",
      renderCount:window.__e4ListMutationCount||0,
    }),{name:query,kind:type});
    if(observed.matchRows!==1 || observed.allRows<1)
      throw Error("E4 physical Notes search did not return one canonical match");
    queryObservations.push({query,kind:type,apiResponse:true,...observed});
    return observed;
  }
  checkpoint="verify_task_local_search";
  await page.click("#notes-home-tab");
  const taskQuery=await verifyFreshNotesSearch(taskName,"task");
  const taskSearchVisible=taskQuery.matchRows===1;
  checkpoint="verify_person_backlinks_ui";
  const linkedPersons=[];
  for(const name of expectedNames){
    await page.click("#notes-home-tab");
    await verifyFreshNotesSearch(name,"person");
    await page.evaluate(person=>{
      const row=Array.from(document.querySelectorAll(
        '#notes-list .notes-type-group[data-type="person"] .note-row'
      )).find(item=>item.textContent.includes(person));
      if(!row)throw Error("Synthetic Person not in fresh query");
      row.click();
    },name);
    await page.waitForFunction((person,task)=>{
      const title=document.querySelector("#note-detail header h2")?.textContent||"";
      const inbound=Array.from(document.querySelectorAll(
        "#note-detail .note-backlinks .backlink-source .backlink"));
      return !document.querySelector("#note-detail")?.hidden && title.includes(person) &&
        inbound.some(item=>item.textContent.includes(task));
    },{timeout:15000},name,taskName);
    linkedPersons.push(name);
  }
  const notes={surfaceVisible:true,
    resultNodes:await page.evaluate(()=>document.querySelectorAll("#notes-list .note-row").length),
    searchObservations:queryObservations,
    taskSearchVisible,verifiedPersonBacklinks:linkedPersons.length,taskName};
  const expectedWrites=Number(process.env.ODYSSEY_E4_EXPECTED_WRITES);
  if(!Number.isInteger(expectedWrites) || expectedWrites<2 || expectedWrites>10)
    throw Error("Invalid E4 expected receipt count");
  // Recorded responses can finish before a progress milestone is painted;
  // live GPT requests MUST still show an advanced progress trace.
  const recordedFixture=process.env.ODYSSEY_E4_RECORDED==="1";
  const output={
    pass:progressDonut.present && progressDonut.valid &&
      String(progressDonut.percent)===progressDonut.displayed &&
      (recordedFixture || progressTrace.advanced) && progressTrace.monotonic &&
      before.userMessages===1 && before.acknowledgements===1 &&
      before.details===1 && before.noteButtons===1 &&
      before.userMessages===after.userMessages &&
      before.details===after.details && before.noteButtons===after.noteButtons &&
      before.confirmationVisible===true && after.confirmationVisible===true &&
      detail.svgCount>0 && detail.sourceFlow && detail.writeReceipts===expectedWrites &&
      !detail.diagnosticRejected && reloadedDetail.svgCount>0 &&
      reloadedDetail.writeReceipts===detail.writeReceipts &&
      !reloadedDetail.diagnosticRejected &&
      notes.surfaceVisible && notes.resultNodes>=1 &&
      notes.searchObservations.length===expectedNames.length+1 &&
      notes.searchObservations.every(item=>item.apiResponse && item.matchRows===1) &&
      jsErrors.length===0,
    before,after,detail,reloadedDetail,notes,progressDonut,progressTrace,recordedFixture,
    userRequestSeconds,
    jsErrorsCount:jsErrors.length,
    actor:"synthetic_only",messages_sent:1
  };
  console.log(JSON.stringify(output));
  if(!output.pass)process.exitCode=2;
 } catch(error){
  let info=null;
  try{if(page) info=await page.evaluate(()=>({turns:document.querySelector("#interaction")?.childElementCount||0,detailButtons:document.querySelectorAll(".detail-button").length,noteButtons:document.querySelectorAll(".note-set-button").length,appErrors:document.querySelectorAll(".message-error").length,notesSearch:document.querySelector("#notes-search")?.value?.slice(0,120),notesStatus:document.querySelector("#notes-status")?.textContent?.slice(0,120),notesResults:Array.from(document.querySelectorAll("#notes-list .note-row")).map(row=>row.textContent.slice(0,100)).slice(0,8),notesDetail:document.querySelector("#note-detail")?.textContent?.slice(0,140)}));}catch{}
  console.log(JSON.stringify({pass:false,checkpoint,info,category:String(error.message).slice(0,240)}));
  process.exitCode=1;
 } finally {if(browser) await browser.close();}
})();
