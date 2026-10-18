import {test} from "node:test";
import assert from "node:assert/strict";
import {approvedRead, approvedStaticPath} from "../scripts/odyssey_dev_readonly_contract.mjs";
import {startReadonlyDevProxy} from "../scripts/odyssey_dev_readonly_proxy.mjs";

test("DEV browser inspection accepts only explicitly read-only API operations",()=>{
 const allowed={
  "/api/conversation":["main","progress"],
  "/api/notes":["query","capabilities","detail","backlinks"],
  "/api/calendar":["month","day","schedule"]
 };
 for(const [endpoint,operations] of Object.entries(allowed)){
  for(const operation of operations)
   assert.equal(approvedRead(endpoint,"POST",{operation}),true,`${endpoint}/${operation}`);
 }
 for(const [endpoint,ops] of Object.entries({
  "/api/request":["execute","request"],
  "/api/conversation":["turn","presence","delete"],
  "/api/notes":["delete_note","delete_fact","task_status","work_session_start",
    "work_session_delete","task_subtask_create","work_session_activity_edit"],
  "/api/calendar":["task_status","write"]
 })) {
  for(const operation of ops)
    assert.equal(approvedRead(endpoint,"POST",{operation}),false,`${endpoint}/${operation}`);
 }
 assert.equal(approvedRead("/api/notes","GET",{operation:"detail"}),false);
 assert.equal(approvedRead("/api/notes","POST",{operation:"detail",write:true}),false);
 assert.equal(approvedRead("/api/notes","POST",{operation:"detail",events:[]}),false);
 assert.equal(approvedRead("/api/notes","POST",{operation:"detail",mutations:[]}),false);
 assert.equal(approvedRead("/api/notes","POST",{operation:"detail",action:"delete"}),false);
 assert.equal(approvedRead("/api/notes","POST",[]),false);
 assert.equal(approvedRead("/api/notes","POST",null),false);
 assert.equal(approvedRead("/api/notes?operation=detail","POST",{operation:"detail"}),false);
});

test("read-only DEV proxy prevents path traversal",()=>{
 for(const candidate of ["/%2e%2e/%2e%2e/private.env","/../../passwd","/a//b.js",
   "/foo%5cbar.js","/data/secrets.env","//server/app.js","/./etc/passwd",
   "/%00hidden.js","/test.txt"]) {
  assert.equal(approvedStaticPath(candidate),null,candidate);
 }
 assert.equal(approvedStaticPath("/"),"index.html");
 assert.equal(approvedStaticPath("/notes.js"),"notes.js");
 assert.equal(approvedStaticPath("/sub/module.js"),"sub/module.js");
});

test("actual loopback proxy returns HTTP 403 on all mutation attempts without forwarding to DEV",async()=>{
 const proxy=await startReadonlyDevProxy();
 try {
  const cases=[
   ["/api/request","execute"],["/api/conversation","turn"],
   ["/api/notes","delete_fact"],["/api/notes","task_status"],
   ["/api/notes","work_session_edit"],["/api/calendar","write"],
   ["/api/something","query"]
  ];
  for(const [endpoint,operation] of cases){
   const reply=await fetch(new URL(endpoint,proxy.url),{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({operation,note_id:"synthetic-noop"})
   });
   assert.equal(reply.status,403,`${endpoint}/${operation}`);
  }
  const fakePresence=await fetch(new URL("/api/conversation",proxy.url),{
   method:"POST",headers:{"content-type":"application/json"},
   body:JSON.stringify({operation:"presence",state:"active",session_id:"synthetic"})
  });
  assert.equal(fakePresence.status,200);
  assert.deepEqual(await fakePresence.json(),{status:"ignored_readonly"});
  assert.equal(proxy.stats.approved,0);
  assert.equal(proxy.stats.denied,cases.length);
  assert.equal(proxy.stats.syntheticPresence,1);
 } finally {
  await new Promise(resolve=>proxy.server.close(resolve));
 }
});

test("real DEV proxy refuses oversized JSON and GET mutations",async()=>{
 const proxy=await startReadonlyDevProxy();
 try {
  const tooBig=await fetch(new URL("/api/notes",proxy.url),{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({operation:"detail",padding:"x".repeat(35000)})
  });
  assert.equal(tooBig.status,400);
  const wrongMethod=await fetch(new URL("/api/notes",proxy.url));
  assert.equal(wrongMethod.status,403);
  assert.equal(proxy.stats.approved,0);
 }finally{await new Promise(resolve=>proxy.server.close(resolve));}
});
