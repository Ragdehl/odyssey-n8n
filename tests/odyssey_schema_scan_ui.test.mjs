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
