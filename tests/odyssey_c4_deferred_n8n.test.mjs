import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const conversationValidate = node(";
const begin = source.indexOf(marker);
const start = source.indexOf("jsCode: `", begin) + "jsCode: `".length;
const end = source.indexOf("` }, position:", start);
assert.ok(begin >= 0 && start > begin && end > start);
const body = source.slice(start, end)
  .replace("${conversationIdentity}", "const authenticated_actor = {stable_user_id: 'synthetic-user'};")
  .replace("${deploymentEnvironment === 'DEV' ? ', authenticated_actor' : ', external_principal'}", ", authenticated_actor");
const validate = new Function("$input", body);
const run = body => validate({first: () => ({json: {body}})})[0].json;

test("n8n isolates a diagnosis lookup from any mutation fields", () => {
  const valid = run({operation: "diagnosis", request_id: "safe-request"});
  assert.equal(valid.operation, "diagnosis");
  assert.equal(valid.request_id, "safe-request");
  assert.equal(valid.authenticated_actor.stable_user_id, "synthetic-user");
  assert.equal(valid.text, undefined);
  for (const bad of [
    {operation: "diagnosis", request_id: "../private"},
    {operation: "diagnosis", request_id: "safe-request", text: "alter this"},
    {operation: "diagnosis", request_id: "safe-request", role: "user"},
    {operation: "diagnosis", request_id: "safe-request", note_result_snapshot: {}},
    {operation: "diagnosis", request_id: "safe-request", session_id: "unknown"},
  ]) {
    assert.equal(run(bad).invalid, true);
  }
  assert.equal(run({operation: "progress", request_id: "safe-request"}).invalid, undefined);
});
