import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {validateProductResponse} from "../odyssey_web/client.js";

// Execute the actual generated routing code with synthetic transport objects,
// not a rewritten copy of its conditions. No n8n API, runtime or vault access.
const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const routeCode = `";
const start = source.indexOf(marker);
assert.notEqual(start, -1);
const end = source.indexOf("`;\n\nconst finishCode =", start + marker.length);
assert.notEqual(end, -1);
const helpersMarker = "const costHelpers = String.raw`";
const helpersStart = source.indexOf(helpersMarker);
const helpersEnd = source.indexOf("`;\n\nconst routeCode", helpersStart + helpersMarker.length);
assert.ok(helpersStart >= 0 && helpersEnd > helpersStart);
const actualHelpers = source.slice(helpersStart + helpersMarker.length, helpersEnd);
const body = source.slice(start + marker.length, end)
  .replace("${pricingSnapshotLiteral}", JSON.stringify({as_of: "2026-10-08", models: {}}))
  .replace("${costHelpers}", actualHelpers);
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
      status: "completed", temporal: [{source: "mañana", value: "2026-10-09"}],
      plan: [{operation: "record", type: "calendar_day", target: "2026-10-09", fact: "Veo a mi hija"}],
      entities: [{mention: "mi hija", name: "Cloe", status: "resolved", type: "person"}],
      writes: [{status: "succeeded", operation: "UPDATED", target: "2026-10-09"}],
      steps: [{name: "temporal.interpretation", input: "mañana", output: "mañana → 2026-10-09"}]}],
  };
  const result = execute({
    request_id: "synthetic-partial", status: "completed",
    product_outcome: "ANSWER", affected_stable_note_ids: ["date:2026-10-09"],
    actions: [{units: [{status: "completed", stable_note_id: "date:2026-10-09"}]}],
    execution_flow: actualFlow,
    operational: {total_duration_ms: 123, stages: [
      {name: "application.router", duration_ms: 1, outcome: "completed", model: "gpt-6-luna", provider_calls: []},
      {name: "temporal.interpretation", duration_ms: 122, outcome: "completed", model: "gpt-6-luna", provider_calls: []},
    ]},
  });
  assert.deepEqual(result.request_detail.flow, actualFlow);
  assert.equal(result.request_detail.operational.stages[1].estimated_cost.status, "unavailable");
});

test("workflow preserves a bounded dependent route for the browser contract", () => {
  const flow = {
    version: 1, input: "Ayer hablé con Eric. Mañana iré con él. Hoy compré pan.",
    parallel_preparation: true,
    routes: [
      {capability: "temporal", text: "Ayer hablé con Eric.", stage_count: 1, status: "completed", temporal: []},
      {capability: "temporal", text: "Mañana iré con él.", stage_count: 1, status: "needs_attention", temporal: [],
        depends_on: 0, reason: "ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE"},
      {capability: "temporal", text: "Hoy compré pan.", stage_count: 1, status: "completed", temporal: []},
    ],
  };
  const result = execute({
    request_id: "synthetic-partial", status: "partial", product_outcome: "ANSWER",
    affected_stable_note_ids: [], actions: [], execution_flow: flow,
    operational: {total_duration_ms: 3, stages: [
      {name: "application.router", outcome: "completed", duration_ms: 0, model: null, provider_calls: []},
      {name: "planner", outcome: "completed", duration_ms: 1, model: null, provider_calls: []},
      {name: "planner", outcome: "deferred", duration_ms: 1, model: null, provider_calls: []},
      {name: "planner", outcome: "completed", duration_ms: 1, model: null, provider_calls: []},
    ]},
  });

  assert.equal(result.request_detail.flow.routes[1].depends_on, 0);
  assert.equal(validateProductResponse(result).request_detail.flow.routes[1].reason,
    "ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE");
});


test("four routed day writes keep all stage evidence and a valid product answer", () => {
  const names = ["temporal.interpretation", "planner", "action.write", "git", "pending"];
  const stages = ["index_barrier", "application.router",
    ...Array.from({length: 4}, () => names).flat()].map(name => ({
    name, outcome: "completed", duration_ms: 4, model: null,
    reasoning_effort: null, error_category: null, provider_calls: [],
  }));
  const routes = Array.from({length: 4}, (_, i) => ({
    capability: "temporal", text: `Frase ${i + 1} mañana`, stage_count: 5,
    status: "completed", temporal: [{source: "mañana", value: "2026-10-09"}],
    plan: [], entities: [], writes: [], steps: names.map(name => ({
      name, input: `Frase ${i + 1} mañana`, output: "Resultado validado",
    })),
  }));
  const response = execute({request_id: "synthetic-partial", status: "completed",
    product_outcome: "ANSWER", affected_stable_note_ids: ["date:2026-10-09"],
    actions: [{units: [{status: "succeeded", operation: "UPDATED", stable_note_id: "date:2026-10-09"}]}],
    operational: {total_duration_ms: 77, stages},
    execution_flow: {version: 1, input: "Cuatro hechos con fechas", parallel_preparation: true, routes},
  });
  assert.equal(response.status, "completed");
  assert.equal(response.request_detail.operational.stages.length, 22);
  assert.equal(response.request_detail.flow.routes.length, 4);
  assert.equal(validateProductResponse(response).request_detail.flow.routes.length, 4);
});

test("overflowing optional stage telemetry cannot turn a saved write into a red client failure", () => {
  const stage = {name: "planner", outcome: "completed", duration_ms: 1, model: null,
    reasoning_effort: null, error_category: null, provider_calls: []};
  const response = execute({request_id: "synthetic-partial", status: "completed",
    product_outcome: "ANSWER", affected_stable_note_ids: ["date:2026-10-09"],
    actions: [{units: [{status: "succeeded", stable_note_id: "date:2026-10-09"}]}],
    operational: {total_duration_ms: 77, stages: Array.from({length: 65}, () => stage)},
    execution_flow: {version: 1, input: "Registro truncado", parallel_preparation: false,
      routes: [{capability: "core", text: "Registro truncado", status: "completed",
        stage_count: 1, temporal: [], plan: [], entities: [], writes: [],
        steps: [{name: "planner", input: "Registro truncado", output: ""}]}]},
  });
  assert.equal(response.status, "completed");
  assert.equal(response.request_detail.operational.stages.length, 0);
  assert.equal(response.request_detail.flow, undefined);
  assert.equal(validateProductResponse(response).status, "completed");
});


test("inconsistent split Temporal returns actionable safe message and retains blocked route graph", () => {
  const names = ["temporal.interpretation", "temporal.coherence"];
  const stages = ["application.router", ...names, ...names].map(name => ({
    name, outcome: name === "temporal.coherence" ? "failed" : "completed",
    duration_ms: name === "temporal.coherence" ? 0 : 3, model: null,
    reasoning_effort: null, error_category: name === "temporal.coherence" ? "TEMPORAL_COHORT_YEAR_CONFLICT" : null,
    provider_calls: [],
  }));
  const routes = ["El 20 de octubre", "El 22 de octubre"].map((text, index) => ({
    capability: "temporal", text, stage_count: 2, status: "needs_attention",
    temporal: [{source: text, value: index ? "2026-10-22" : "2025-10-20"}],
    plan: [], entities: [], writes: [], steps: names.map(name => ({name, input: text, output: ""})),
  }));
  const result = execute({
    request_id: "synthetic-partial", status: "needs_attention",
    product_outcome: "CANNOT_ANSWER", product_reason: "TEMPORAL_COHORT_YEAR_CONFLICT",
    affected_stable_note_ids: [], actions: [], operational: {stages, total_duration_ms: 8},
    execution_flow: {version: 1, input: "El 20 de octubreEl 22 de octubre", parallel_preparation: true, routes},
  });
  assert.equal(result.status, "failed");
  assert.equal(result.kind, "cannot_answer");
  assert.match(result.message, /años incompatibles/);
  assert.match(result.message, /No he guardado nada/);
  assert.equal(result.request_detail.flow.routes.length, 2);
  assert.equal(result.request_detail.changes.affected_stable_note_ids.length, 0);
});
