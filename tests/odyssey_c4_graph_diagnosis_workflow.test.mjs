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
  write_evidence: "UNKNOWN", evidence_stage: stage, route_index: null,
  next_step: "INSPECT_RESULT", verified_stage_only: true,
  stage_view: {version: 1, label: "Core · revisión de la división", icon: "core"},
};
const ledger = {
  version: 1, request_id: ID, status: "needs_attention", events: [],
  event_sequence: null, events_truncated: false,
  stages: [{name: stage, outcome: "failed", duration_ms: 9, start_offset_ms: 0,
    error_category: "COVERAGE_UNVERIFIED", provider_call_count: 1, route_index: null,
    stage_view: {version: 1, label: "Core · revisión de la división", icon: "core"}}],
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
  assert.match(result.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
  assert.doesNotMatch(result.message, /relación entre las dos actividades/);
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
    {error_diagnosis: {...diagnostic, explanation: "No hay notas nuevas. Puedes probar otra vez."}},
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
    assert.doesNotMatch(result.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
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


test("AI cannot blame the completed Router or claim absence of new notes from an unproven result", () => {
  const result = render({
    execution_ledger: {...ledger, stages: [{...ledger.stages[0], name: "application.router",
      outcome: "completed", error_category: null}]},
    error_diagnosis: {...diagnostic, evidence_stage: "application.router",
      explanation: "El módulo de identidad falló. No hay notas nuevas."},
  });
  assert.equal(result.kind, "clarification");
  assert.doesNotMatch(result.message, /El módulo de identidad falló|No hay notas nuevas/);
});

test("valid AI graph diagnosis takes precedence over a fixed known CLARIFY fallback", () => {
  const result = render({
    clarification_code: "ROUTER_CLARIFY", product_reason: "ROUTER_CLARIFY",
    error_diagnosis: {...diagnostic, reason_code: "ROUTER_CLARIFY"},
  });
  assert.match(result.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
  assert.doesNotMatch(result.message, /No puedo decidir con seguridad qué aplicación/);
});


test("repeated stage names across routes require the right failed route index", () => {
  const routes = [
    {route_index: 0, capability: "core", status: "completed", depends_on: null},
    {route_index: 1, capability: "tasks", status: "failed", depends_on: null},
  ];
  const duplicated = [
    {...ledger.stages[0], route_index: 0, outcome: "completed"},
    {...ledger.stages[0], route_index: 1, outcome: "failed"},
  ];
  const common = {execution_ledger: {...ledger, routes, stages: duplicated}};
  const wrong = render({...common, error_diagnosis: {...diagnostic, route_index: 0}});
  assert.doesNotMatch(wrong.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
  const correct = render({...common, error_diagnosis: {...diagnostic, route_index: 1}});
  assert.match(correct.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
});


test("verified AI diagnosis preserves a noncompleted Core status", () => {
  const original = render({
    status: "needs_attention", product_outcome: "CANNOT_ANSWER",
    product_reason: diagnostic.reason_code,
    execution_ledger: {...ledger, status: "needs_attention"},
  });
  assert.equal(original.kind, "cannot_answer");
  assert.equal(original.status, "needs_attention");
  assert.match(original.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
});


test("n8n rejects generic parent attribution when a failed nested provider stage exists", () => {
  const parent = {...ledger.stages[0], name: "application.source_processing", parent_stage: null};
  const child = {...ledger.stages[0], name: "provider.semantic_review",
    parent_stage: parent.name, stage_view: {version: 1,
      label: "Consulta al servicio de IA", icon: "router"}};
  const nested = {...ledger, stages: [parent, child]};
  const misleading = render({execution_ledger: nested,
    error_diagnosis: {...diagnostic, evidence_stage: parent.name}});
  assert.doesNotMatch(misleading.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
  const grounded = render({execution_ledger: nested,
    error_diagnosis: {...diagnostic, evidence_stage: child.name,
      stage_view: child.stage_view}});
  assert.match(grounded.message, /No he podido completar la solicitud en «Consulta al servicio de IA»/);
});

test("semantically reviewed writer-stage explanation bypasses obsolete lexical rejection only with typed marker", () => {
  const text = "La etapa de escritura falló; el resultado físico de la operación no está confirmado.";
  const lexical = render({error_diagnosis: {...diagnostic, explanation: text}});
  assert.doesNotMatch(lexical.message, /La etapa de escritura falló/);
  const vetted = render({error_diagnosis: {...diagnostic, explanation: text, semantic_reviewed: true}});
  assert.doesNotMatch(vetted.message, /La etapa de escritura falló/);
  // Even a forged semantic attestation in n8n cannot lift the write-claim
  // guard; verified stage membership is necessary but insufficient.
  assert.match(vetted.message, /No he podido interpretar este mensaje/);
  const invalid = render({error_diagnosis: {...diagnostic, explanation: text,
    semantic_reviewed: false}});
  assert.doesNotMatch(invalid.message, /La etapa de escritura falló/);
  const invented = render({error_diagnosis: {...diagnostic, explanation: text,
    semantic_reviewed: true, retry_authorized: true}});
  assert.doesNotMatch(invented.message, /La etapa de escritura falló/);
  const typed = render({error_diagnosis: {
    status: diagnostic.status, reason_code: diagnostic.reason_code,
    evidence_stage: stage, route_index: null, write_evidence: 'UNKNOWN',
    next_step: 'INSPECT_RESULT', verified_stage_only: true,
    stage_view: {version: 1, label: "Core · revisión de la división", icon: "core"},
  }});
  assert.match(typed.message, /No he podido completar la solicitud en «Core · revisión de la división»/);
  assert.doesNotMatch(typed.message, /candidate.source_boundary_review/);
  assert.doesNotMatch(typed.message, /La etapa de escritura falló|ya está guardada/);
  const invalidTyped = render({error_diagnosis: {
    status: diagnostic.status, reason_code: diagnostic.reason_code,
    evidence_stage: 'core.identity_resolution', route_index: null, write_evidence: 'UNKNOWN',
    next_step: 'INSPECT_RESULT', verified_stage_only: true,
    stage_view: {version: 1, label: "Core · revisión de la división", icon: "core"},
  }});
  assert.doesNotMatch(invalidTyped.message, /Core · revisión de la división/);
  const forgedView = render({error_diagnosis: {
    status: diagnostic.status, reason_code: diagnostic.reason_code,
    evidence_stage: stage, route_index: null, write_evidence: 'UNKNOWN',
    next_step: 'INSPECT_RESULT', verified_stage_only: true,
    stage_view: {version: 1, label: 'He guardado todos los archivos', icon: 'core'},
  }});
  assert.doesNotMatch(forgedView.message, /He guardado todos los archivos/);
  const malformedLedger = render({execution_ledger: {...ledger, stages: [
    {...ledger.stages[0], stage_view: {version: 1, label: 'N', icon: 'invalid'}}
  ]}, error_diagnosis: {
    status: diagnostic.status, reason_code: diagnostic.reason_code,
    evidence_stage: stage, route_index: null, write_evidence: 'UNKNOWN',
    next_step: 'INSPECT_RESULT', verified_stage_only: true,
    stage_view: {version: 1, label: 'N', icon: 'invalid'},
  }});
  assert.doesNotMatch(malformedLedger.message, /He guardado|No he podido completar la solicitud en/);
});

test("reviewed stage_view requires failed owner route even with repeated stage names", () => {
  const routes = [
    {route_index: 0, capability: "core", status: "completed", depends_on: null},
    {route_index: 1, capability: "tasks", status: "failed", depends_on: null},
  ];
  const shared = {...ledger.stages[0]};
  const updated = {...ledger, routes, stages: [
    {...shared, route_index: 0, outcome: "completed"},
    {...shared, route_index: 1, outcome: "failed"},
  ]};
  const reviewed = {status: diagnostic.status, reason_code: diagnostic.reason_code,
    evidence_stage: stage, route_index: 1, write_evidence: "UNKNOWN",
    next_step: "INSPECT_RESULT", verified_stage_only: true,
    stage_view: {...shared.stage_view}};
  const valid = render({execution_ledger: updated, error_diagnosis: reviewed});
  assert.match(valid.message, /Core · revisión de la división/);
  const wrongOwner = render({execution_ledger: updated,
    error_diagnosis: {...reviewed, route_index: 0}});
  assert.doesNotMatch(wrongOwner.message, /Core · revisión de la división/);
  const wrongLabel = render({execution_ledger: updated,
    error_diagnosis: {...reviewed, stage_view: {...reviewed.stage_view, label: "Otro resultado"}}});
  assert.doesNotMatch(wrongLabel.message, /Otro resultado/);
});


test("CANNOT_ANSWER without synchronous advisory preserves Core needs_attention status", () => {
  const result = render({
    product_outcome: "CANNOT_ANSWER",
    error_diagnosis: undefined,
    clarification: undefined,
  });
  assert.equal(result.kind, "cannot_answer");
  assert.equal(result.status, "needs_attention");
  assert.equal(validateProductResponse(result).status, "needs_attention");
});

test("n8n refuses all legacy model prose regardless of its language or purported physical proof", () => {
  const messages = [
    "No hay evidencia de escritura.",
    "Tus notas ya están guardadas, todo correcto.",
    "Обработка прошла успешно, файл обновлен.",
    "Please delete the note and retry.",
  ];
  for (const explanation of messages) {
    const raw = {status: diagnostic.status, reason_code: diagnostic.reason_code,
      write_evidence: "UNKNOWN", evidence_stage: stage, route_index: null,
      next_step: "INSPECT_RESULT", explanation, user_question: ""};
    const result = render({error_diagnosis: raw});
    assert.equal(result.kind, "clarification");
    assert.doesNotMatch(result.message, /No he podido completar la solicitud en/);
    assert.ok(!result.message.includes(explanation));
  }
});


test("a failed writer stage cannot carry CHECK_SYSTEM or unsafe retry through n8n", () => {
  const writer = {...ledger.stages[0], name: "tasks.writer.persist",
    stage_view: {version: 1, label: "Escritura", icon: "core"}};
  const observed = {...ledger, stages: [writer]};
  const checked = {...diagnostic, evidence_stage: writer.name,
    stage_view: writer.stage_view, next_step: "INSPECT_RESULT"};
  const safe = render({execution_ledger: observed, error_diagnosis: checked});
  assert.match(safe.message, /No he podido completar la solicitud en «Escritura»/);
  for (const next_step of ["CHECK_SYSTEM", "REVIEW_SAFE_RETRY"]) {
    const refused = render({execution_ledger: observed,
      error_diagnosis: {...checked, next_step}});
    assert.doesNotMatch(refused.message, /No he podido completar la solicitud en «Escritura»/);
  }
});


test("n8n demands source-executor prewrite proof, never stage-name guesses", () => {
  const stageName = "custom.persist";
  const observed = {...ledger, stages: [{
    ...ledger.stages[0], name: stageName,
    stage_view: {version: 1, label: "Resultado de la operación", icon: "core"},
  }]};
  const candidate = {...diagnostic, evidence_stage: stageName,
    stage_view: observed.stages[0].stage_view, next_step: "CHECK_SYSTEM"};
  const unproven = render({execution_ledger: observed, error_diagnosis: candidate});
  assert.doesNotMatch(unproven.message, /Resultado de la operación/);
  const corroborated = render({execution_ledger: observed,
    prewrite_recovery_proven: true, error_diagnosis: candidate});
  assert.match(corroborated.message, /Resultado de la operación/);
  const forgedRetry = render({execution_ledger: observed,
    error_diagnosis: {...candidate, next_step: "REVIEW_SAFE_RETRY"}});
  assert.doesNotMatch(forgedRetry.message, /Resultado de la operación/);
  const inspect = render({execution_ledger: observed,
    error_diagnosis: {...candidate, next_step: "INSPECT_RESULT"}});
  assert.match(inspect.message, /Resultado de la operación/);
});


test("a routine journal failure never directs an ordinary user to admin graphs", () => {
  const result = render({
    error_diagnosis: null,
    error_guidance: null,
    product_reason: "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
    clarification_code: "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
    prewrite_recovery_proven: true,
  });
  assert.equal(result.kind, "clarification");
  assert.match(result.message, /No he podido interpretar este mensaje/);
  assert.doesNotMatch(result.message, /gr[aá]fico|diagrama|etapa|inspecciona/i);
  assert.equal(validateProductResponse(result).kind, "clarification");
});

test("a coverage-review refusal never sends the user to the internal graph", () => {
  const result = render({
    error_diagnosis: null,
    product_reason: "CANDIDATE_COVERAGE_REVIEW_REQUIRED",
    clarification_code: "CANDIDATE_COVERAGE_REVIEW_REQUIRED",
  });
  assert.equal(result.kind, "clarification");
  assert.doesNotMatch(result.message, /gr[aá]fico|diagrama/i);
});
