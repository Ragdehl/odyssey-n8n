import test from "node:test";
import assert from "node:assert/strict";
import {createSchemaScanPanel} from "../odyssey_web/schema-scan.js";
import {validateSchemaOperationResponse, NotesRequestError} from "../odyssey_web/notes-client.js";

class Node {
  constructor(tagName) {
    this.tagName = tagName;
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.children = [];
    this.handlers = {};
  }
  append(...children) {this.children.push(...children);}
  setAttribute(key, value) {this[key] = value;}
  addEventListener(name, fn) {this.handlers[name] = fn;}
  click() {this.handlers.click?.();}
}
globalThis.document = {createElement: (tag) => new Node(tag)};

const ready = {kind: "schema_scan", status: "scanning", scanned_paths: 20,
  eligible_notes: 17, skipped_existing_values: 0, legacy_sources: 2};
const complete = {...ready, status: "complete", scanned_paths: 40, eligible_notes: 25,
  legacy_sources: 5};
const target = {scanKind: "discover_type", typeId: "libro", revision: 1};

async function drain() {for (let i=0;i<8;i++) await Promise.resolve();}

test("read-only scan completes several bounded pages from a single click", async () => {
  const calls = [];
  const client = async (x) => {
    calls.push(x);
    return x.payload.action === "status" ? {kind:"schema_scan", status:"not_started"} :
      calls.filter(c => c.payload.action === "advance").length === 1 ? ready : complete;
  };
  const panel = createSchemaScanPanel({root: new Node("section"), client});
  panel.show(target);
  await drain();
  assert.equal(panel.panel.hidden, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].payload.action, "status");
  assert.equal(calls.some(x=>x.operation === "schema_confirm"), false);
  panel.panel.children[3].click();
  await drain();
  assert.equal(calls.length, 3);
  assert.deepEqual(calls[1].payload, {
    scan_kind: "discover_type", target_type_id: "libro", property_id: null,
    expected_revision: 1, action: "advance",
  });
  assert.equal(calls[2].payload.action, "advance");
  assert.match(panel.panel.children[2].textContent, /40 notas examinadas/);
  assert.match(panel.panel.children[2].textContent, /5 con texto antiguo/);
  assert.match(panel.panel.children[2].textContent, /Lectura finalizada/);
  assert.equal(panel.panel.children[3].hidden, true);
  panel.hide();
  assert.equal(panel.panel.hidden, true);
});

test("backfill property source preview never writes and has no stale cross-user UI authority", async () => {
  let resolveCall;
  const calls = [];
  const client = (input) => {calls.push(input); return new Promise(resolve => {resolveCall = resolve;});};
  const panel = createSchemaScanPanel({root: new Node("section"), client});
  panel.show({scanKind:"backfill_property", typeId:"person", propertyId:"profesion", revision:2});
  assert.equal(calls[0].payload.property_id, "profesion");
  panel.hide();
  resolveCall(ready);
  await drain();
  assert.equal(panel.panel.hidden, true);
  assert.equal(calls.length, 1);
  for (const bad of [
    {scanKind:"discover_type", typeId:"../a", revision:1},
    {scanKind:"backfill_property", typeId:"person", revision:1},
    {scanKind:"discover_type", typeId:"book", propertyId:"fake", revision:1},
    {scanKind:"discover_type", typeId:"book", revision:101},
  ]) assert.throws(()=>panel.show(bad));
});

test("stale scan receipt is shown as non-writing blocker", async () => {
  let count = 0;
  const client = async () => {
    count += 1;
    if (count === 1) return {kind:"schema_scan",status:"not_started"};
    throw Object.assign(new Error("stale"), {code:"SCHEMA_SCAN_STALE_OR_INVALID"});
  };
  const panel = createSchemaScanPanel({root: new Node("section"), client});
  panel.show(target);
  await drain();
  panel.panel.children[3].click();
  await drain();
  assert.match(panel.panel.children[2].textContent,/no se ha continuado el análisis/i);
  assert.equal(panel.panel.children[3].hidden,true);
});

test("schema scan response union rejects fake progress, source bodies and write receipts", () => {
  assert.deepEqual(validateSchemaOperationResponse("schema_scan", {
    kind:"schema_scan",status:"not_started",
  }), {kind:"schema_scan", status:"not_started"});
  assert.equal(validateSchemaOperationResponse("schema_scan", ready).legacy_sources,2);
  for (const payload of [
    {...ready, physical_write:true},
    {...ready, scanned_paths:-1},
    {...ready, eligible_notes:21},
    {...ready, legacy_sources:30},
    {...ready, seen_note_ids:["private"]},
    {...ready, body:"secret"},
    {...ready, status:"published"},
    {kind:"schema_scan", status:"not_started", actor_id:"other"},
  ]) assert.throws(()=>validateSchemaOperationResponse("schema_scan",payload),NotesRequestError);
});

test("one action scans up to 1,000 notes, pauses fairly and resumes without redoing work", async () => {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.payload.action === "status") return {kind:"schema_scan",status:"not_started"};
    const page = calls.filter(x=>x.payload.action==="advance").length;
    return page <= 50 ? {...ready,scanned_paths:20*page,eligible_notes:15*page,
      legacy_sources:0} : {...complete,scanned_paths:1010,eligible_notes:750,legacy_sources:0};
  };
  const panel = createSchemaScanPanel({root:new Node("section"),client});
  panel.show(target);
  await drain();
  await panel.advance();
  assert.equal(calls.filter(x=>x.payload.action==="advance").length,50);
  assert.match(panel.panel.children[2].textContent,/Pausa de rendimiento tras 1.000 archivos/);
  assert.equal(panel.panel.children[3].hidden,false);
  await panel.advance();
  assert.equal(calls.filter(x=>x.payload.action==="advance").length,51);
  assert.match(panel.panel.children[2].textContent,/Lectura finalizada/);
  assert.equal(panel.panel.children[3].hidden,true);
});

test("pausing during one in-flight request prevents the next automatic request", async () => {
  let finish;
  const calls = [];
  const client = (call) => {
    calls.push(call);
    if (call.payload.action === "status") return Promise.resolve({kind:"schema_scan",status:"not_started"});
    return new Promise(resolve=>{finish=resolve;});
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show(target);
  await drain();
  panel.panel.children[3].click();
  await drain();
  assert.equal(calls.length,2);
  panel.panel.children[5].click();
  finish(ready);
  await drain();
  assert.equal(calls.length,2);
  assert.match(panel.panel.children[2].textContent,/Análisis pausado/);
  assert.equal(panel.panel.children[3].hidden,false);
});

const backfill = (status, updates = 0, pending = 0, deferred = 0) => ({
  kind:"schema_backfill",status,total:updates+pending+deferred,
  pending,interpreting:0,writing:0,updated:updates,no_evidence:0,
  ambiguous:0,stale:0,already_present:0,deferred,
});

test("one confirmed property starts scan and deterministic enrichment automatically", async () => {
  const calls=[];
  const client=async (r)=>{
    calls.push(r);
    if (r.operation==="schema_scan") return r.payload.action==="status"
      ? {kind:"schema_scan",status:"not_started"} : complete;
    const steps=calls.filter(x=>x.operation==="schema_backfill");
    if (r.payload.action==="status") return {kind:"schema_backfill",status:"not_started"};
    if (r.payload.action==="stage") return backfill("in_progress",0,3);
    if (steps.filter(x=>x.payload.action==="advance").length===1) return backfill("in_progress",1,2);
    if (steps.filter(x=>x.payload.action==="advance").length===2) return backfill("in_progress",2,1);
    return backfill("awaiting_ai",2,0,1);
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",
    propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<60;i++) await Promise.resolve();
  assert.deepEqual(calls.map(x=>[x.operation,x.payload.action]),[
    ["schema_scan","status"],["schema_scan","advance"],["schema_backfill","status"],
    ["schema_backfill","stage"],["schema_backfill","advance"],
    ["schema_backfill","advance"],["schema_backfill","advance"],
  ]);
  for(const r of calls.filter(x=>x.operation==="schema_backfill")) {
    assert.deepEqual(Object.keys(r.payload).sort(),
      ["action","expected_revision","property_id","target_type_id"].sort());
    assert.equal(r.payload.expected_revision,1);
  }
  assert.match(panel.panel.children[6].textContent,/2 propiedades completadas/);
  assert.match(panel.panel.children[6].textContent,/1 pendientes de IA/);
  assert.equal(panel.panel.children[7].hidden,true);
  assert.equal(panel.panel.children[3].hidden,true);
});

test("reopening a completed scan resumes local write journal without rescanning", async () => {
  const calls=[];
  const client=async r=>{
    calls.push(r);
    if(r.operation==="schema_scan") return complete;
    if(r.payload.action==="status") return backfill("in_progress",1,1);
    return backfill("complete",2);
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",
    propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<40;i++) await Promise.resolve();
  assert.deepEqual(calls.map(x=>[x.operation,x.payload.action]),[
    ["schema_scan","status"],["schema_backfill","status"],["schema_backfill","advance"],
  ]);
  assert.match(panel.panel.children[6].textContent,/Autocompletado finalizado/);
});

test("disabled backfill never presents a source read as a physical write", async () => {
  const calls=[];
  const client=async r=>{
    calls.push(r);
    if(r.operation==="schema_scan") return complete;
    throw Object.assign(Error("disabled"),{code:"invalid notes request"});
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",
    propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<30;i++) await Promise.resolve();
  assert.equal(calls.filter(x=>x.operation==="schema_backfill").length,1);
  assert.match(panel.panel.children[6].textContent,/todavía no está habilitado/i);
  assert.doesNotMatch(panel.panel.children[6].textContent,/propiedades completadas/);
});

test("strict deterministic enrichment receipts reject forged IDs, counts and writes", () => {
  const accepted=backfill("awaiting_ai",2,0,1);
  assert.equal(validateSchemaOperationResponse("schema_backfill",accepted).deferred,1);
  assert.deepEqual(validateSchemaOperationResponse("schema_backfill",{
    kind:"schema_backfill",status:"not_started",
  }),{kind:"schema_backfill",status:"not_started"});
  for(const bad of [
    {...accepted, actor_id:"other"}, {...accepted,undo:"git-sha"},
    {...accepted, total:9999}, {...accepted, updated:-1},
    {...accepted, deferred:0}, {...accepted,status:"all_done"},
    {...accepted,status:"attention"}, {...accepted,status:"complete"},
  ]) assert.throws(()=>validateSchemaOperationResponse("schema_backfill",bad),NotesRequestError);
});

test("unknown postwrite outcome offers journal verification instead of manual per-note approval", async()=>{
  const calls=[];
  let fail=true;
  const client=async r=>{
    calls.push(r);
    if(r.operation==="schema_scan")return complete;
    if(r.payload.action==="status")return fail
      ? backfill("in_progress",0,1)
      : {...backfill("in_progress",0,0),total:1,writing:1,updated:0};
    if(fail){
      fail=false;
      throw Object.assign(Error("postwrite scheduling fault"),
        {code:"SCHEMA_BACKFILL_OUTCOME_UNVERIFIED"});
    }
    return backfill("complete",1);
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",
    propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<55;i++)await Promise.resolve();
  const message=panel.panel.children[6];
  const resume=panel.panel.children[7];
  assert.match(message.textContent,/verificar el resultado|confirmar el resultado/i);
  assert.equal(resume.hidden,false);
  assert.match(resume.textContent,/Verificar y continuar/);
  assert.equal(calls.filter(c=>c.operation==="schema_backfill"&&
    c.payload.action==="advance").length,1);
  resume.click();
  for(let i=0;i<55;i++)await Promise.resolve();
  assert.match(message.textContent,/Autocompletado finalizado/);
  assert.equal(resume.hidden,true);
  assert.equal(calls.filter(c=>c.operation==="schema_backfill"&&
    c.payload.action==="advance").length,2);
});

test("campaign validates 50k bounded totals and rejects false terminal or injected receipts", () => {
  const running = {...backfill("in_progress", 2, 0, 1), segment: 0, finished: false};
  assert.deepEqual(validateSchemaOperationResponse("schema_backfill", running), running);
  const completed = {...backfill("complete", 12000), segment: 12, finished: true};
  assert.deepEqual(validateSchemaOperationResponse("schema_backfill", completed), completed);
  for (const bad of [
    {...running, finished: true},
    {...running, status: "awaiting_ai"},
    {...completed, finished: false},
    {...completed, segment: -1},
    {...completed, segment: 60000},
    {...completed, total: 50001},
    {...completed, actor_id: "attacker"},
    {...completed, eligibility_bitmap: "secret"},
  ]) assert.throws(
    () => validateSchemaOperationResponse("schema_backfill", bad), NotesRequestError);
  assert.throws(
    () => validateSchemaOperationResponse("schema_backfill", backfill("complete", 12000)),
    NotesRequestError);
});

test("UI continues across a deferred child boundary until campaign parent completes", async () => {
  const calls = [];
  const client = async (req) => {
    calls.push(req);
    if(req.operation === "schema_scan") return complete;
    if(req.payload.action === "status") return {kind:"schema_backfill",status:"not_started"};
    if(req.payload.action === "stage") return {
      ...backfill("in_progress", 0, 2), segment: 0, finished: false
    };
    const count = calls.filter(x=>x.operation==="schema_backfill" &&
      x.payload.action==="advance").length;
    if(count===1) return {...backfill("in_progress", 0, 1, 1), segment:0, finished:false};
    if(count===2) return {...backfill("in_progress", 1, 0, 1), segment:0, finished:false};
    if(count===3) return {...backfill("in_progress", 2, 1, 1), segment:1, finished:false};
    return {...backfill("awaiting_ai", 3, 0, 1), segment:2, finished:true};
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",
    propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<65;i++) await Promise.resolve();
  assert.equal(calls.filter(c=>c.operation==="schema_backfill" &&
    c.payload.action==="advance").length,4);
  assert.match(panel.panel.children[6].textContent,/3 propiedades completadas/);
  assert.match(panel.panel.children[6].textContent,/1 pendientes de IA/);
  assert.equal(panel.panel.children[7].hidden,true);
});

test("signed semantic follow-up needs a second user click, never runs during initial scan", async () => {
  const calls=[];
  const original = {...backfill("awaiting_ai",1,0,1),
    reserved_calls:0,call_limit:6};
  const staged = {...backfill("in_progress",0,1,0),segment:0,finished:false,
    reserved_calls:0,call_limit:6,phase:"semantic_followup"};
  const finished = {...backfill("complete",1),segment:1,finished:true,
    reserved_calls:2,call_limit:6,phase:"semantic_followup"};
  const client=async (x)=>{
    calls.push(x);
    if(x.operation==="schema_scan") return x.payload.action==="status"
      ? {kind:"schema_scan",status:"not_started"} : complete;
    const action=x.payload.action;
    if(action==="status") return {kind:"schema_backfill",status:"not_started"};
    if(action==="stage") return backfill("in_progress",0,2);
    if(action==="advance") return original;
    if(action==="status_followup") return {kind:"schema_backfill",status:"not_started"};
    if(action==="stage_followup") return staged;
    if(action==="advance_followup") return finished;
    throw new Error("Unexpected action "+action);
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",propertyId:"profesion",revision:1});
  await drain();
  panel.panel.children[3].click();
  await drain();
  assert.equal(calls.some(x=>x.payload.action.endsWith("_followup")),false);
  const action=panel.panel.children[7];
  assert.equal(action.hidden,false);
  assert.match(action.textContent,/Interpretar pendientes con IA/);
  assert.match(panel.panel.children[6].textContent,/0 de 6/);
  action.click();
  await drain();
  assert.deepEqual(calls.filter(x=>x.payload.action.endsWith("_followup"))
    .map(x=>x.payload.action),["status_followup","stage_followup","advance_followup"]);
  assert.match(panel.panel.children[6].textContent,/2 de 6/);
  assert.equal(action.hidden,true);
});

test("semantic follow-up public receipts validate only capped counts and a declared phase", () => {
  const good={...backfill("in_progress",1,2),segment:0,finished:false,
    call_limit:6,reserved_calls:2,phase:"semantic_followup"};
  assert.deepEqual(validateSchemaOperationResponse("schema_backfill",good),good);
  const initial={...backfill("awaiting_ai",1,0,1),call_limit:6,reserved_calls:0};
  assert.deepEqual(validateSchemaOperationResponse("schema_backfill",initial),initial);
  for (const bad of [
    {...good,call_limit:0},
    {...good,call_limit:37},
    {...good,call_limit:6,reserved_calls:7},
    {...good,reserved_calls:-1},
    {...good,phase:"initial"},
    {...good,actor_id:"other"},
    {...good,note_ids:["secret"]},
    {...good,private_quote:"secret"},
    {...good,call_limit:undefined},
    {...backfill("in_progress",1,1),phase:"semantic_followup"},
    {...initial,reserved_calls:undefined},
  ]) assert.throws(
    ()=>validateSchemaOperationResponse("schema_backfill",bad),NotesRequestError
  );
});

test("provider failure before write has a clear nonretryable pause, not Git uncertainty", async () => {
  const calls=[];
  const budget={call_limit:6,reserved_calls:0};
  const client=async (x)=>{
    calls.push(x);
    if(x.operation==="schema_scan") return complete;
    if(x.payload.action==="status") return {kind:"schema_backfill",status:"not_started"};
    if(x.payload.action==="stage") return {...backfill("in_progress",0,1),...budget};
    if(x.payload.action==="advance") return {...backfill("awaiting_ai",0,0,1),...budget};
    if(x.payload.action==="status_followup") return {kind:"schema_backfill",status:"not_started"};
    if(x.payload.action==="stage_followup") return {
      ...backfill("in_progress",0,1),...budget,segment:0,finished:false,
      phase:"semantic_followup",
    };
    if(x.payload.action==="advance_followup") {
      throw Object.assign(Error("source deferred, no write"),{
        code:"SCHEMA_BACKFILL_SEMANTIC_PAUSED",
      });
    }
    throw Error("Unexpected operation");
  };
  const panel=createSchemaScanPanel({root:new Node("section"),client});
  panel.show({scanKind:"backfill_property",typeId:"person",propertyId:"profesion",revision:1,autoStart:true});
  for(let i=0;i<50;i++) await Promise.resolve();
  assert.match(panel.panel.children[7].textContent,/Interpretar pendientes con IA/);
  panel.panel.children[7].click();
  for(let i=0;i<50;i++) await Promise.resolve();
  assert.match(panel.panel.children[6].textContent,/pausado antes de escribir/);
  assert.match(panel.panel.children[6].textContent,/no se reintentará automáticamente/i);
  assert.equal(panel.panel.children[7].hidden,true);
  assert.equal(calls.filter(x=>x.payload.action==="advance_followup").length,1);
});
