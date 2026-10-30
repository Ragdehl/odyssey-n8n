import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "jsCode: `const body = $input.first().json.body || {};";
const start = source.indexOf(marker);
const end = source.indexOf("` }, position: [220, 0]", start + marker.length);
assert.ok(start >= 0 && end > start);
const execute = new Function("$input", source.slice(start + "jsCode: `".length, end)
  .replace("${productionPrincipalProjection}", "")
  .replace("${deploymentEnvironment === 'PROD' ? ', external_principal' : ''}", ""));
const send = body => execute({first: () => ({json: {body}})})[0].json;

test("real n8n validation preserves a bounded explicit pending locator", () => {
  const valid = send({request: "Con Luis", request_id: "web-new",
    reply_to_request_id: "web-old-r1"});
  assert.equal(valid.valid, true);
  assert.equal(valid.reply_to_request_id, "web-old-r1");
  assert.equal(send({request: "Una solicitud", request_id: "web-new"}).valid, true);
  for (const invalid of ["../secret", "two words", "", 1, true, [], "x".repeat(129)]) {
    const answer = send({request: "Con Luis", request_id: "web-new",
      reply_to_request_id: invalid});
    assert.equal(answer.valid, false);
  }
});

test("private n8n call forwards only the validated pending request field", () => {
  assert.match(source, /\{reply_to_request_id: \$json\.reply_to_request_id\}/);
  assert.match(source, /request_id: \$json\.request_id, \.\.\.\(\$json\.reply_to_request_id/);
  assert.doesNotMatch(source, /reply_to_request_id: \$input\.first\(\)\.json\.body\.reply_to_request_id/);
});
