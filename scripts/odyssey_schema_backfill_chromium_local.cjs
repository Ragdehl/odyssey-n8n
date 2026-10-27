"use strict";
/** Actual Chromium clicks, local synthetic actor proxy, REAL Core HTTP+Markdown.
 * NOT deployed DEV / n8n / Access / model provider.
 */
const assert=require("node:assert/strict");
const http=require("node:http"),fs=require("node:fs"),path=require("node:path");
const root=path.resolve(__dirname,"..");
const puppeteer=require(process.env.ODYSSEY_PUPPETEER_MODULE||
  path.join(process.env.HOME,".npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer"));
const chrome=process.env.ODYSSEY_CHROMIUM_BINARY||
  path.join(process.env.HOME,".cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome");
const upstream=new URL(process.env.ODYSSEY_SYNTH_LOCAL_HTTP||"");
assert.equal(upstream.hostname,"127.0.0.1");
assert.equal(upstream.pathname,"/");
const actor="00000000-0000-4000-8000-000000000001";
const n8nSocket=process.env.ODYSSEY_SYNTH_N8N_SOCKET||"";
if(n8nSocket) {
  assert.match(n8nSocket,/^\/tmp\/odyssey-schema-socket-[^/]+\/ingress\.sock$/);
  assert.ok(fs.statSync(n8nSocket).isSocket(),"Must connect to a temporary Unix socket");
}
const viewport=process.argv[2]==="mobile"?[390,844]:[1280,920];
const calls=[];
const campaign=process.env.ODYSSEY_SYNTH_CAMPAIGN==="1";
const html='<!doctype html><html lang="es"><head><meta charset="utf-8">'+
  '<meta name="viewport" content="width=device-width,initial-scale=1">'+
  '<link rel="stylesheet" href="/odyssey_web/styles.css"></head><body>'+
  '<main><h1>Odyssey · Personas</h1><button id="show">Revisar notas</button>'+
  '<section id="model"></section></main><script type="module">'+
  'import {createSchemaScanPanel} from "/odyssey_web/schema-scan.js";'+
  'const panel=createSchemaScanPanel({root:document.querySelector("#model")});'+
  'document.querySelector("#show").addEventListener("click",()=>panel.show({'+
  'scanKind:"backfill_property",typeId:"person",propertyId:"profesion",revision:1,autoStart:true}));'+
  'window.__appReady=true;</script></body></html>';
const files=new Set(["/odyssey_web/styles.css","/odyssey_web/schema-scan.js",
                     "/odyssey_web/notes-client.js","/odyssey_web/client.js"]);
const server=http.createServer(async(req,res)=>{
  const pathname=new URL(req.url,"http://localhost").pathname;
  if(req.method==="GET"&&pathname==="/"){
    res.writeHead(200,{"content-type":"text/html; charset=utf-8"});res.end(html);return;
  }
  if(req.method==="GET"&&files.has(pathname)){
    const file=path.join(root,pathname.slice(1));
    res.writeHead(200,{"content-type":file.endsWith(".css")?"text/css":"text/javascript"});
    res.end(fs.readFileSync(file));return;
  }
  if(req.method==="POST"&&pathname==="/api/notes"){
    let data="";
    for await(const part of req){
      data+=part;if(data.length>3000){res.writeHead(413);res.end();return;}
    }
    let body;
    try{body=JSON.parse(data);}catch{res.writeHead(400);res.end();return;}
    if(!["schema_scan","schema_backfill"].includes(body?.operation)||
       !["status","advance","stage"].includes(body?.action)||
       body.target_type_id!=="person"||body.property_id!=="profesion"||
       body.expected_revision!==1||
       Object.keys(body).some(k=>!["operation","action","target_type_id",
                    "property_id","expected_revision","scan_kind"].includes(k))||
       (body.operation==="schema_scan"&&(body.scan_kind!=="backfill_property"||
                    body.action==="stage"))||
       (body.operation==="schema_backfill"&&body.scan_kind!==undefined)){
      res.writeHead(400,{"content-type":"application/json"});
      res.end(JSON.stringify({error:"invalid notes request"}));return;
    }
    calls.push(body.operation+":"+body.action);
    const next=http.request(n8nSocket ? {
      socketPath:n8nSocket,method:"POST",path:"/execute",
      headers:{"content-type":"application/json"},timeout:20000
    }:{
      hostname:"127.0.0.1",port:Number(upstream.port),
      method:"POST",path:"/notes",headers:{"content-type":"application/json"},timeout:15000
    }, response=>{
      res.writeHead(response.statusCode,{"content-type":"application/json"});
      response.pipe(res);
    });
    next.on("error",()=>{if(!res.headersSent)res.writeHead(502);res.end();});
    next.end(JSON.stringify(n8nSocket ? body :
      Object.assign({},body,{authenticated_actor:{stable_user_id:actor}})));
    return;
  }
  res.writeHead(404);res.end();
});
(async()=>{
  let browser;
  const output={kind:n8nSocket ? "real_chromium_offline_n8n_core" :
      "real_chromium_local_core_no_n8n",
    viewport:process.argv[2]||"desktop",
    n8n:n8nSocket ? "REAL_OFFLINE" : "NOT_TESTED",deployedDev:false,pass:false};
  try{
    await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
    browser=await puppeteer.launch({executablePath:chrome,headless:true,
      args:["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-background-networking"]});
    const page=await browser.newPage();await page.setViewport({width:viewport[0],height:viewport[1]});
    const errors=[];page.on("pageerror",e=>errors.push(String(e).slice(0,180)));
    const url="http://127.0.0.1:"+server.address().port+"/";
    await page.goto(url,{waitUntil:"networkidle0"});
    await page.waitForFunction(()=>window.__appReady===true);
    await page.click("#show");
    await page.waitForFunction((expected)=>{
      const text=document.querySelector(".schema-model-enrichment-status")?.textContent||"";
      return text.includes(expected) && (!expected.startsWith("4 ") ||
        text.includes("El resto requiere interpretación mediante IA."));
    },{timeout:45000},campaign?"4 propiedades completadas":"1 pendientes de IA");
    const first=await page.$eval(".schema-model-enrichment-status",el=>el.textContent);
    assert.match(first,campaign?/4 propiedades completadas/:/1 propiedades completadas/);
    assert.match(first,/1 pendientes de IA/);
    assert.match(first,/requiere interpretación mediante IA/);
    assert.equal(errors.length,0,JSON.stringify(errors));
    await page.reload({waitUntil:"networkidle0"});
    await page.waitForFunction(()=>window.__appReady===true);
    await page.click("#show");
    await page.waitForFunction((expected)=>{
      const text=document.querySelector(".schema-model-enrichment-status")?.textContent||"";
      return text.includes(expected) && (!expected.startsWith("4 ") ||
        text.includes("El resto requiere interpretación mediante IA."));
    },{timeout:45000},campaign?"4 propiedades completadas":"1 pendientes de IA");
    const second=await page.$eval(".schema-model-enrichment-status",el=>el.textContent);
    assert.match(second,campaign?/4 propiedades completadas/:/1 propiedades completadas/);
    assert.match(second,/1 pendientes de IA/);
    assert.equal(calls.filter(x=>x==="schema_backfill:advance").length,campaign?6:2);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+4);
    assert.equal(overflow,false,"Mobile horizontal overflow");
    assert.equal(errors.length,0,JSON.stringify(errors));
    output.pass=true;output.requests=calls;output.reloadPersisted=true;
    output.screenStatus=second;output.browserErrors=errors;
    await page.close();
  }catch(e){output.error=String(e.stack||e).slice(0,900);process.exitCode=1;}
  finally{if(browser)await browser.close();server.close();
          console.log("ODYSSEY_BACKFILL_BROWSER="+JSON.stringify(output));}
})();
