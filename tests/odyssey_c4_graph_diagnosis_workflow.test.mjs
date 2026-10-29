// Run the ACTUAL n8n route code; no fake implementation of its security checks.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {validateProductResponse} from "../odyssey_web/client.js";

const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const routeCode = `";
const start = source.indexOf(marker);
const end = source.indexOf("`;\n\nconst finishCode =", start + marker.length);
const helpersMarker = "const costHelpers = String.raw`";
const helpersStart = source.indexOf(helpersMarker);
const helpersEnd = source.indexOf("`;\n\nconst routeCode", helpersStart + helpersMarker.length);
assert.ok(start >= 0 && end > start && helpersStart >= 0 && helpersEnd > helpersStart);
const body = source.slice(start + marker.length, end)
  .replace("${pricingSnapshotLiteral}", JSON.stringify({as_of: "2026-10-29", models: {}}))
  .replace("${costHelpers}", source.slice(helpersStart + helpersMarker.length, helpersEnd));
const route = new Function("$input", "$", body);
const ID = "c4-graph-synthetic";
const stage = "candidate.source_boundary_review";
const diagnostic = {
  status: "needs_attention", reason_code: "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
  write_evidence: "UNKNOWN", evidence_stage: stage,
  explanation: "La revisión no pudo confirmar que se conservaran todas las partes de la frase.",
  next_step: "ASK_USER", user_question: "¿Puedes aclarar la relación entre las dos actividades?",
};
const ledger = {
  version: 1, request_id: ID, status: "needs_attention", events: [],
  event_sequence: null, events_truncated: false,
  stages: [{name: stage, outcome: "failed", duration_ms: 9, start_offset_ms: 0,
    error_category: "COVERAGE_UNVERIFIED", provider_call_count: 1, route_index: null}],
  routes: [], write_receipts: [], affected_stable_note_ids: [],
};
const base = {
  request_id: ID, status: "needs_attention", product_outcome: "CLARIFY",
  clarification_code: diagnostic.reason_code, product_reason: diagnostic.reason_code,
  actions: [], affected_stable_note_ids: [], operational: {total_duration_ms: 12, stages: []},
  execution_ledger: ledger,
  clarification: {request_id: ID, options: []},
  error_diagnosis: diagnostic,
};
const render = overrides => route(
  {first: () => ({json: {...base, ...overrides}})},
  name => {
    assert.equal(name, "Odyssey product request");
    return {item: {json: {body: {request_id: ID}}}};
  },
)[0].json;

test("AI explains real Router coverage failure before Core identity matching", () => {
  const result = render({});
  assert.equal(result.kind, "clarification");
  assert.equal(result.status, "needs_attention");
  assert.match(result.message, /revisión no pudo confirmar/);
  assert.match(result.message, /relación entre las dos actividades/);
  assert.match(result.message, /No puedo confirmar todavía si se ha guardado/);
  assert.doesNotMatch(result.message, /qué persona|mi hijo|especificar el nombre/i);
  assert.equal(result.clarification.options.length, 0);
  assert.equal(validateProductResponse(result).kind, "clarification");
});

test("model hallucination of stages, writes, commands and source is discarded", () => {
  const mutations = [
    {error_diagnosis: {...diagnostic, evidence_stage: "core.identity_resolution"}},
    {error_diagnosis: {...diagnostic, explanation: "No he guardado nada; reintentar."}},
    {error_diagnosis: {...diagnostic, explanation: "No se actualizó ninguna nota, prueba otra vez."}},
    {error_diagnosis: {...diagnostic, next_step: "AUTO_RETRY", user_question: ""}},
    {error_diagnosis: {...diagnostic, retry_authorized: true}},
    {error_diagnosis: {...diagnostic, reason_code: "ANOTHER_FAILURE"}},
    {error_diagnosis: {...diagnostic, write_evidence: "ZERO_CONFIRMED"}},
    {execution_ledger: {...ledger, status: "completed"}},
    {execution_ledger: undefined},
  ];
  for (const mutation of mutations) {
    const result = render(mutation);
    assert.equal(result.status, "needs_attention");
    assert.equal(result.kind, "clarification");
    assert.doesNotMatch(result.message, /revisión no pudo confirmar/);
  }
});

test("Core-verified entity alternatives still win over AI diagnosis", () => {
  const result = render({clarification: {
    request_id: ID, requested_reference: "él",
    explanation: "¿A cuál de las dos personas te refieres?",
    options: [{id: "person-a", label: "Una persona"}, {id: "person-b", label: "Otra persona"}],
  }});
  assert.equal(result.message, "¿A cuál de las dos personas te refieres?");
  assert.equal(result.clarification.options.length, 2);
});
