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
