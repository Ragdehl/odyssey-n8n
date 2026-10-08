import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

// Execute the actual generated routing code with synthetic transport objects,
// not a rewritten copy of its conditions. No n8n API, runtime or vault access.
const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const routeCode = `";
const start = source.indexOf(marker);
assert.notEqual(start, -1);
const end = source.indexOf("`;\n\nconst finishCode =", start + marker.length);
assert.notEqual(end, -1);
const body = source.slice(start + marker.length, end)
  .replace("${pricingSnapshotLiteral}", JSON.stringify({as_of: "2026-10-08", models: {}}))
  .replace("${costHelpers}", "function safeOperational(x){return x}; function requestCost(){return {status:'unavailable', amount_usd:null}};");
const route = new Function("$input", "$", body);
const snapshot = {
  version: 2, kind: "affected_notes", executed_at: "2026-10-08T13:00:00+02:00",
  note_ids: ["date:2026-10-08"], total: 1, truncated: false,
};
function execute(result) {
  return route(
    {first: () => ({json: result})},
    (label) => {
      assert.equal(label, "Odyssey product request");
      return {item: {json: {body: {request_id: "synthetic-partial"}}}};
    }
  )[0].json;
}

test("partial writes are disclosed instead of misreported as entirely failed", () => {
  const result = execute({
    request_id: "synthetic-partial", status: "partial",
    product_outcome: "CANNOT_ANSWER", product_reason: "INCOMPLETE_EVIDENCE",
    affected_stable_note_ids: ["date:2026-10-08"],
    actions: [{units: [{status: "succeeded", operation: "UPDATED", stable_note_id: "date:2026-10-08"}]}],
    operational: {total_duration_ms: 1000, stages: []},
    note_result_snapshot: snapshot,
  });
  assert.equal(result.status, "partial");
  assert.equal(result.kind, "acknowledgement");
  assert.match(result.message, /He guardado parte de la información/);
  assert.match(result.message, /no he podido completar/);
  assert.deepEqual(result.request_detail.changes.affected_stable_note_ids, ["date:2026-10-08"]);
  assert.deepEqual(result.note_result_snapshot, snapshot);
});

test("full failure without a write remains a failure and never claims saved work", () => {
  const result = execute({
    request_id: "synthetic-partial", status: "failed",
    product_outcome: "CANNOT_ANSWER", product_reason: "ROUTER_INVALID",
    affected_stable_note_ids: [], operational: {total_duration_ms: 500, stages: []},
  });
  assert.equal(result.status, "failed");
  assert.equal(result.kind, "cannot_answer");
  assert.match(result.message, /No he guardado nada/);
  assert.equal(result.note_result_snapshot, undefined);
});

test("unconfirmed writes cannot be promoted into partial success", () => {
  const result = execute({
    request_id: "synthetic-partial", status: "partial",
    product_outcome: "CANNOT_ANSWER", product_reason: "INCOMPLETE_EVIDENCE",
    affected_stable_note_ids: [], operational: {total_duration_ms: 1000, stages: []},
  });
  assert.equal(result.status, "failed");
  assert.doesNotMatch(result.message, /He guardado parte/);
});


test("workflow carries only validated route provenance and stage cost projections", () => {
  const actualFlow = {
    version: 1, input: "Hoy hice una cosa y mañana otra", parallel_preparation: true,
    routes: [{capability: "temporal", text: "mañana otra", stage_count: 1,
      status: "completed", temporal: [{source: "mañana", value: "2026-10-09"}]}],
  };
  const result = execute({
    request_id: "synthetic-partial", status: "completed",
    product_outcome: "ANSWER", affected_stable_note_ids: ["date:2026-10-09"],
    actions: [{units: [{status: "completed", stable_note_id: "date:2026-10-09"}]}],
    execution_flow: actualFlow,
    operational: {total_duration_ms: 123, stages: [{name: "temporal.interpretation", duration_ms: 123,
      outcome: "completed", model: "gpt-6-luna", provider_calls: []}]},
  });
  assert.deepEqual(result.request_detail.flow, actualFlow);
  assert.equal(result.request_detail.operational.stages[0].estimated_cost.status, "unavailable");
});
