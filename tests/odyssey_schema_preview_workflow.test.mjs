// Run the actual n8n Notes-validator JavaScript with synthetic browser envelopes.
// This is local contract evidence, not a deployed n8n/Chromium acceptance test.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const routeStart = source.indexOf("const notesValidate = node(");
const routeEnd = source.indexOf("\nconst notesValid = node(", routeStart);
assert.ok(routeStart >= 0 && routeEnd > routeStart);
const route = source.slice(routeStart, routeEnd);
const begin = route.indexOf("jsCode: `");
const end = route.indexOf("` }, position:", begin);
assert.ok(begin >= 0 && end > begin);
const code = route.slice(begin + "jsCode: `".length, end).replace(
  "${conversationIdentity}",
  "const authenticated_actor = {stable_user_id: '00000000-0000-4000-8000-000000000001'};",
).replace(
  "${deploymentEnvironment === 'DEV' ? ', authenticated_actor' : ', external_principal'}",
  ", authenticated_actor",
);
assert.ok(!code.includes("${"), "All template placeholders must be substituted");
const validate = new Function("$input", code);

const change = {
  operation: "add_property", type_id: "person",
  property: {id: "occupation", value_type: "string", description: "Profession when known."},
};
function run(body) {
  const result = validate({first: () => ({json: {body}})})[0].json;
  return result;
}

test("n8n forwards only the schema preview proposal and its trusted actor", () => {
  const submitted = run({operation: "schema_preview", expected_revision: 0, change});
  assert.equal(submitted.invalid, undefined);
  assert.deepEqual(submitted, {
    operation: "schema_preview", expected_revision: 0, change,
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"},
  });
});

test("n8n blocks extra authority, malformed versions, or missing proposal", () => {
  const bads = [
    {operation: "schema_publish", expected_revision: 0, change},
    {operation: "schema_confirm", expected_revision: 0, change},
    {operation: "schema_preview", expected_revision: 0, change, approved: true},
    {operation: "schema_preview", expected_revision: 0, change, request_id: "x"},
    {operation: "schema_preview", expected_revision: 0, change, authenticated_actor: {stable_user_id: "forged"}},
    {operation: "schema_preview", expected_revision: 0},
    {operation: "schema_preview", expected_revision: -1, change},
    {operation: "schema_preview", expected_revision: true, change},
    {operation: "schema_preview", expected_revision: 1.5, change},
    {operation: "schema_preview", expected_revision: 101, change},
    {operation: "schema_preview", expected_revision: 0, change: null},
    {operation: "schema_preview", expected_revision: 0, change: []},
    {operation: "schema_preview", expected_revision: 0, change: {note: "x".repeat(20000)}},
  ];
  for (const bad of bads) {
    const outcome = run(bad);
    assert.equal(outcome.invalid, true, JSON.stringify(bad).slice(0, 80));
    assert.equal(outcome.error, "invalid notes request");
  }
});

test("adding schema preview does not change the existing Notes capabilities route", () => {
  assert.deepEqual(run({operation: "capabilities"}), {
    operation: "capabilities",
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"},
  });
  assert.equal(run({operation: "capabilities", change}).invalid, true);
});


test("n8n forwards explicit typed schema confirmations, not caller-supplied identities", () => {
  const body = {operation: "schema_confirm", change, expected_revision: 0,
    proposal_hash: "a".repeat(64), request_id: "schema-ack-123"};
  const result = run(body);
  assert.deepEqual(result, {...body,
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"}});
  assert.deepEqual(run({operation: "schema_status", request_id: "schema-ack-123"}), {
    operation: "schema_status", request_id: "schema-ack-123",
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"},
  });
  assert.deepEqual(run({operation: "schema_status"}), {operation: "schema_status",
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"}});
});

test("n8n confirmation rejects malformed digests, authority overrides and extra fields", () => {
  const valid = {operation: "schema_confirm", change, expected_revision: 0,
    proposal_hash: "a".repeat(64), request_id: "schema-ack-123"};
  for (const extra of [
    {proposal_hash: "wrong"}, {request_id: ""}, {request_id: "bad id"},
    {expected_revision: true}, {expected_revision: -1},
    {change: []}, {change: null},
    {approved: true}, {actor_id: "attacker"},
    {authenticated_actor: {stable_user_id: "attacker"}},
  ]) {
    assert.equal(run({...valid, ...extra}).invalid, true, JSON.stringify(extra));
  }
  for (const invalid of [{operation: "schema_status", request_id: "bad id"},
    {operation: "schema_status", actor_id: "attacker"}]) {
    assert.equal(run(invalid).invalid, true);
  }
});

test("n8n allows only authenticated bounded conversational schema hints", () => {
  const valid = {operation: "schema_suggest", message: "Quiero fichas de mis libros", expected_revision: 0};
  assert.deepEqual(run(valid), {...valid,
    authenticated_actor: {stable_user_id: "00000000-0000-4000-8000-000000000001"},
  });
  for (const extra of [
    {message: ""}, {message: " ".repeat(20)}, {message: "a".repeat(1201)},
    {message: 1}, {expected_revision: -1}, {expected_revision: true},
    {approved: true}, {request_id: "forged"}, {proposal_hash: "a".repeat(64)},
    {authenticated_actor: {stable_user_id: "attacker"}},
    {change: {operation: "add_type"}},
  ]) {
    assert.equal(run({...valid, ...extra}).invalid, true, JSON.stringify(extra).slice(0, 80));
  }
});

test("n8n admits one bounded read-only schema review without allowing extra authority", () => {
  const body = {operation: "schema_review", message: "Mis libros", change,
    expected_revision: 0, proposal_hash: "a".repeat(64)};
  assert.deepEqual(run(body), {...body, authenticated_actor: {
    stable_user_id: "00000000-0000-4000-8000-000000000001"}});
  for (const extra of [
    {message: "a".repeat(1201)}, {message: 45}, {expected_revision: true},
    {expected_revision: 101}, {change: []}, {change: null},
    {proposal_hash: "invalid"}, {approved: true}, {request_id: "forged"},
    {authenticated_actor: {stable_user_id: "forged"}},
  ]) assert.equal(run({...body, ...extra}).invalid, true);
});

test("n8n permits only the bounded, actor-bound read-only schema scan envelope", () => {
  const input = {operation: "schema_scan", scan_kind:"backfill_property",
    target_type_id:"person", property_id:"profesion", expected_revision:1,
    action:"advance"};
  assert.deepEqual(run(input), {...input,
    authenticated_actor:{stable_user_id:"00000000-0000-4000-8000-000000000001"}});
  for (const wrong of [
    {...input, note_id:"target-to-mutate"},
    {...input, confirmed:true},
    {...input, actor_id:"other"},
    {...input, target_type_id:"../secret"},
    {...input, scan_kind:"reset"},
    {...input, action:"delete"},
    {...input, expected_revision:true},
    {...input, property_id:null},
    {...input, source_text:"private"},
    {...input, job_id:"client-controlled"},
  ]) assert.equal(run(wrong).invalid,true);
  const discovery = {...input, scan_kind:"discover_type", target_type_id:"libro",property_id:null,
    action:"status"};
  assert.equal(run(discovery).operation,"schema_scan");
});

test("n8n forwards only actor-bound deterministic property backfill actions", () => {
  const input={operation:"schema_backfill",target_type_id:"person",
    property_id:"profesion",expected_revision:1,action:"stage"};
  assert.deepEqual(run(input), {...input,
    authenticated_actor:{stable_user_id:"00000000-0000-4000-8000-000000000001"}});
  for (const bad of [
    {...input, property_id:null},
    {...input, expected_revision:0},
    {...input, expected_revision:true},
    {...input, action:"approve"},
    {...input, action:"delete"},
    {...input, reviewed_semantic:true},
    {...input, notes:["private"]},
    {...input, value:"arbitrary"},
    {...input, actor_id:"other"},
    {...input, authenticated_actor:{stable_user_id:"forged"}},
    {...input, request_id:"some"},
  ]) assert.equal(run(bad).invalid, true, JSON.stringify(bad));
});

test("actual n8n Notes validator forwards the three explicit semantic follow-up actions", () => {
  const base={operation:"schema_backfill",target_type_id:"book",property_id:"paginas",expected_revision:1};
  const actor={stable_user_id:"00000000-0000-4000-8000-000000000001"};
  for(const action of ["stage","status","advance","stage_followup","status_followup","advance_followup"]){
    const input={...base,action};
    assert.deepEqual(run(input),{...input,authenticated_actor:actor},action);
  }
  for(const bad of [
    {...base,action:"advance_followup",authenticated_actor:actor},
    {...base,action:"advance_followup",actor_id:"other"},
    {...base,action:"advance_followup",note_ids:["injected"]},
    {...base,action:"stage_followup",value:384},
    {...base,action:"stage_followup",call_limit:36},
    {...base,action:"stage_followup",expected_revision:true},
    {...base,action:"status_followup",property_id:"../invalid"},
    {...base,action:"reset_followup"},
    {...base,operation:"schema_scan",scan_kind:"backfill_property",action:"stage_followup"},
  ]){
    assert.equal(run(bad).invalid,true,JSON.stringify(bad));
  }
});
