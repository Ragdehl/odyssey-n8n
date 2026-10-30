"use strict";
const path = require("node:path");
const puppeteer = require(process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(process.env.HOME || "/home/ragdehl", ".npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer"));
const executablePath = process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(process.env.HOME || "/home/ragdehl",
    ".cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome");

(async () => {
  let browser, page, checkpoint = "boot";
  try {
    const url = process.env.ODYSSEY_SYNTHETIC_BROWSER_URL;
    if (!/^http:\/\/127\.0\.0\.1:\d+\/$/.test(url)) throw Error("Synthetic localhost required");
    browser = await puppeteer.launch({executablePath, headless:true,
      args:["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-background-networking"]});
    page = await browser.newPage();
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    const jsErrors=[];
    page.on("pageerror",error=>jsErrors.push(String(error.message).slice(0,180)));
    checkpoint="auth_negative";
    const denied=await page.goto(url,{waitUntil:"domcontentloaded",timeout:16000});
    if (denied.status()!==403) throw Error("Unauthenticated access was accepted");
    await page.setCookie({name:"odyssey_test_auth",value:process.env.ODYSSEY_SYNTHETIC_AUTH,
      url,httpOnly:true,sameSite:"Strict"});
    checkpoint="restored_choice";
    const ok=await page.goto(url,{waitUntil:"domcontentloaded",timeout:15000});
    if (ok.status()!==200) throw Error("Synthetic app unreachable");
    await page.waitForFunction(() =>
      document.querySelector(".message-clarification-restored")
      && document.querySelectorAll(".message-clarification-restored .clarification-choose").length===2,
      {timeout:18000});
    const rows=await page.$$(".message-clarification-restored .clarification-option");
    const labels=await Promise.all(rows.map(row=>row.$eval("h3", el=>el.textContent)));
    const chosen=await rows[labels.findIndex(x=>x.includes("Luis"))]?.$(".clarification-choose");
    if (!chosen || !labels.some(x=>x.includes("Eric")))
      throw Error("Invalid restored choices: "+JSON.stringify(labels));
    checkpoint="click_choice";
    await chosen.click();
    await page.waitForFunction(() => {
      const body=document.querySelector("#interaction")?.textContent||"";
      return (document.querySelectorAll(".message-acknowledgement").length>0 ||
              document.querySelectorAll(".message-error").length>0 ||
              body.includes("He guardado la información pendiente."));
    },{timeout:180000});
    const response=await page.evaluate(()=>({
      text:document.querySelector("#interaction")?.textContent?.slice(-800)||"",
      errorCount:document.querySelectorAll(".message-error").length,
      acknowledgementCount:document.querySelectorAll(".message-acknowledgement").length,
      userCount:document.querySelectorAll(".message-user").length,
    }));
    if(response.errorCount || !/guardad/i.test(response.text))
      throw Error("Browser did not acknowledge saved E5 continuation: "+JSON.stringify(response));
    checkpoint="reload";
    await page.reload({waitUntil:"domcontentloaded",timeout:17000});
    await page.waitForFunction(()=>!!document.querySelector("#interaction"),{timeout:14000});
    await page.waitForFunction(()=>document.querySelector("#interaction")?.textContent?.includes("He guardado"),
      {timeout:18000});
    const after=await page.evaluate(()=>({
      persisted:document.querySelector("#interaction")?.textContent?.includes("He guardado"),
      pendingChoices:document.querySelectorAll(".message-clarification-restored .clarification-choose").length,
      errorCount:document.querySelectorAll(".message-error").length,
    }));
    if(!after.persisted || after.pendingChoices || after.errorCount) throw Error("Reload did not retain success");
    checkpoint="notes_ui";
    await page.click("#notes-tab");
    await page.waitForFunction(()=>document.querySelector("#notes-list-view"),{timeout:14000});
    await page.waitForFunction(()=>document.querySelector("#notes-list")?.textContent?.length>0,
      {timeout:20000});
    const notes=await page.evaluate(()=>({
      visible:!!document.querySelector("#notes-list-view"),
      count:document.querySelector("#notes-list")?.children.length||0,
      text:document.querySelector("#notes-list")?.textContent?.slice(0,220)||"",
    }));
    if (!notes.visible || !notes.count || jsErrors.length) throw Error("Notes UI error");
    console.log(JSON.stringify({pass:true,source_case:"e5_selected",authenticated_local:true,
      restored_card:true,choice_labels:labels,
      saved_visible:response.acknowledgementCount>0||/guardad/i.test(response.text),
      persisted_on_reload:after.persisted,notes_visible:notes.visible,notes_count:notes.count,
      page_errors:jsErrors}),);
  } catch(error) {
    console.log(JSON.stringify({pass:false,checkpoint,error:String(error.message||error).slice(0,420)}));
    process.exitCode=2;
  } finally {
    await page?.close().catch(()=>{});
    await browser?.close().catch(()=>{});
  }
})();
