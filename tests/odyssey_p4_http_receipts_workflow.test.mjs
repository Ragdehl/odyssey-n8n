// Characterize REAL P4 HTTP receipts through actual n8n route JavaScript.
// This executes n8n source locally, NOT through an actual live n8n webhook.
// Passing tests cannot be mistaken for user-visible acceptance.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {validateProductResponse} from "../odyssey_web/client.js";

const receipts = JSON.parse(readFileSync(new URL(
  "../benchmarks/application_router/light_router_poc_20261016/p4_runtime_http_receipts.json",
  import.meta.url), "utf8"));
const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const routeCode = `";
const start = source.indexOf(marker);
const end = source.indexOf("`;\n\nconst finishCode =", start + marker.length);
const helpersMarker = "const costHelpers = String.raw`";
const helpersStart = source.indexOf(helpersMarker);
const helpersEnd = source.indexOf("`;\n\nconst routeCode", helpersStart + helpersMarker.length);
assert.ok(start >= 0 && end > start && helpersStart >= 0 && helpersEnd > helpersStart);
const actualHelpers = source.slice(helpersStart + helpersMarker.length, helpersEnd);
const body = source.slice(start + marker.length, end)
  .replace("${pricingSnapshotLiteral}", JSON.stringify({as_of: "2026-10-16", models: {}}))
  .replace("${costHelpers}", actualHelpers);
const route = new Function("$input", "$", body);
function translate(row) {
  const id = row.id;
  const incoming = {
    request_id: id, status: row.product_status, product_outcome: row.product_outcome,
    product_reason: null, clarification_code: row.expected_safe_abstention
      ? "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED" : null,
    affected_stable_note_ids: row.notes,
    actions: Array.from({length: row.action_count}, () => ({
      units: [{status: "succeeded", operation: "UPDATED", stable_note_id: row.notes[0]}],
    })),
    operational: {total_duration_ms: row.duration_s * 1000, stages: []},
  };
  const response = route(
    {first: () => ({json: incoming})},
    (label) => {
      assert.equal(label, "Odyssey product request");
      return {item: {json: {body: {request_id: id}}}};
    },
  )[0].json;
  return validateProductResponse(response);
}

test("five actual HTTP cases are authentic and were replay-safe before mapping", () => {
  assert.equal(receipts.transport.includes("real TCP HTTP"), true);
  assert.equal(receipts.n8n_traversed, false);
  assert.equal(receipts.browser_traversed, false);
  assert.equal(receipts.cases.length, 5);
  for (const row of receipts.cases) {
    assert.equal(row.http_status, 200);
    assert.equal(row.replay_http_status, 200);
    assert.equal(row.replay_marked, true);
    assert.equal(row.replay_preserved_all_note_bytes, true);
    assert.equal(row.real_model_runs, 1);
  }
});

test("existing n8n mapping would render the three true completions", () => {
  for (const row of receipts.cases.filter((r) => !r.expected_safe_abstention)) {
    const converted = translate(row);
    assert.equal(converted.status, "completed");
    assert.equal(converted.kind, "acknowledgement");
  }
});

test("known P4 blocker: existing n8n fallback for Ana and pronoun ambiguity is generic", () => {
  for (const row of receipts.cases.filter((r) => r.expected_safe_abstention)) {
    assert.equal(row.safe_no_write, true);
    assert.equal(row.notes.length, 0);
    const converted = translate(row);
    assert.equal(converted.status, "needs_attention");
    assert.equal(converted.kind, "clarification");
    assert.equal(converted.clarification.options.length, 0);
    assert.match(converted.message, /Necesito que precises/);
    // This passing characterization is NOT UX acceptance. An actual valid
    // choice-based continuation has yet to be integrated with P4 and n8n.
  }
});
