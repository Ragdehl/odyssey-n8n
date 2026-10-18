import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import {approvedRead, approvedStaticPath, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES} from "./odyssey_dev_readonly_contract.mjs";

const ROOT = "/data/odyssey-dev/runtime/web";
const TARGET = Object.freeze({hostname: "172.18.0.1", port: 28780});
const MIME = Object.freeze({
 ".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8",
 ".css":"text/css; charset=utf-8", ".svg":"image/svg+xml",
 ".json":"application/json", ".png":"image/png", ".webp":"image/webp",
 ".ico":"image/x-icon", ".woff2":"font/woff2"
});

function answer(res, code, message = "") {
 res.writeHead(code, {"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
 res.end(message);
}

async function serveStatic(req, res) {
 if(req.method!=="GET" && req.method!=="HEAD") return answer(res,405);
 const url=new URL(req.url,"http://127.0.0.1");
 const relative=approvedStaticPath(url.pathname);
 if(!relative) return answer(res,403);
 try {
  const real=await fs.realpath(path.join(ROOT,relative));
  if(!real.startsWith(ROOT+"/")) return answer(res,403);
  const file=await fs.readFile(real);
  if(file.length>MAX_RESPONSE_BYTES) return answer(res,413);
  res.writeHead(200,{"content-type":MIME[path.extname(real)]||"application/octet-stream","cache-control":"no-store","content-security-policy":"default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"});
  res.end(req.method==="HEAD"?"":file);
 } catch {answer(res,404);}
}

async function getBoundedBody(req) {
 let size=0;
 const parts=[];
 for await (const data of req) {
   size+=data.length;
   if(size>MAX_REQUEST_BYTES) throw new Error("API request exceeds read-only limit");
   parts.push(data);
 }
 return Buffer.concat(parts);
}

async function serveApi(req,res,stats) {
 const uri=new URL(req.url,"http://127.0.0.1");
 if(req.method!=="POST") {stats.denied++;return answer(res,403);}
 let body,parsed;
 try {
  body=await getBoundedBody(req);
  parsed=JSON.parse(body.toString("utf8"));
 } catch {
  stats.denied++;return answer(res,400);
 }
 // Presence is a write-to-session/last-seen signal. Never forward it to DEV.
 if(uri.pathname==="/api/conversation" && parsed?.operation==="presence") {
  stats.syntheticPresence++;
  res.writeHead(200,{"content-type":"application/json","cache-control":"no-store"});
  return res.end('{"status":"ignored_readonly"}');
 }
 if(!approvedRead(uri.pathname,req.method,parsed)){
  stats.denied++;return answer(res,403,"Browser inspection forbids mutating DEV");
 }
 stats.approved++;
 const upstream=http.request({
   ...TARGET, method:"POST",path:uri.pathname,
   headers:{"content-type":"application/json","accept":"application/json",
            "content-length":body.length},timeout:15000,
 }, remote=>{
   let total=0, chunks=[];
   remote.on("data",b=>{
     total+=b.length;
     if(total>MAX_RESPONSE_BYTES) {remote.destroy(new Error("Oversize response"));return;}
     chunks.push(b);
   });
   remote.on("end",()=>{
     if(res.writableEnded)return;
     res.writeHead(remote.statusCode||502,{
       "content-type":"application/json","cache-control":"no-store"
     });
     res.end(Buffer.concat(chunks));
   });
   remote.on("error",()=>{
     if(!res.headersSent) answer(res,502);
     else res.destroy();
   });
 });
 upstream.on("timeout",()=>upstream.destroy(new Error("DEV read timeout")));
 upstream.on("error",()=>{
   if(!res.headersSent) answer(res,502);
   else res.destroy();
 });
 upstream.end(body);
}

export async function startReadonlyDevProxy() {
 const stats={denied:0, approved:0,syntheticPresence:0};
 const server=http.createServer((req,res)=>{
  if((req.url||"").startsWith("/api/")) void serveApi(req,res,stats);
  else void serveStatic(req,res);
 });
 await new Promise((resolve,reject)=>{
   server.once("error",reject);
   server.listen(0,"127.0.0.1",resolve);
 });
 return {server, stats, url:"http://127.0.0.1:"+server.address().port+"/"};
}
