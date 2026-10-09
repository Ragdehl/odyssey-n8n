import test from "node:test";
import assert from "node:assert/strict";
import {
  DiagnosticPreviewError,
  renderExecutionFlow,
  renderFactCandidatePreview,
  validateExecutionCheckpoint,
  validateFactCandidatePreview,
} from "../odyssey_web/progress.js";
import {readFileSync} from "node:fs";
import {validateRequestDetail, ProductRequestError} from "../odyssey_web/client.js";

class TestNode {
  constructor(tag) { this.tagName = tag; this.className = ""; this.children = []; this._text = ""; this.attrs = {}; this.classList = {add: (...values) => {this.className += ` ${values.join(" ")}`;}}; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(item => item.textContent).join(""); }
  setAttribute(key, value) { this.attrs[key] = value; }
  append(...children) { this.children.push(...children); }
  findAll(className) {return [...(this.className.split(" ").includes(className) ? [this] : []), ...this.children.flatMap(node => node.findAll(className))];}
  findTag(tag) {return [...(this.tagName === tag ? [this] : []), ...this.children.flatMap(node => node.findTag(tag))];}
}
const doc = {createElement(tag) {return new TestNode(tag);}, createElementNS(_namespace, tag) {return new TestNode(tag);}};
const stage = (name, duration_ms, extras = {}) => ({
  name, outcome: "completed", duration_ms, model: null, reasoning_effort: null,
  provider_calls: [], ...extras,
});
const cost = (amount_usd) => ({status: "estimated", amount_usd, pricing_basis: "2026-10-08"});
const flow = {
  version: 1, input: "Hoy tengo que ir al cine y mañana iré al teatro",
  parallel_preparation: true,
  routes: [
    {capability: "tasks", text: "Hoy tengo que ir al cine", status: "completed", stage_count: 2, temporal: [],
      plan: [{operation: "record", type: "task", target: "ir al cine", fact: "Tengo que ir al cine."}],
      entities: [], writes: [{status: "succeeded", operation: "CREATED", target: "ir al cine"}],
      steps: [{name: "tasks.interpretation", input: "Hoy tengo que ir al cine", output: "Operación: create"},
        {name: "planner", input: "Hoy tengo que ir al cine", output: "record · task → ir al cine"}]},
    {capability: "temporal", text: "mañana iré al teatro", status: "completed", stage_count: 3,
      temporal: [{source: "mañana", value: "2026-10-09"}],
      plan: [{operation: "record", type: "calendar_day", target: "2026-10-09", fact: "Mi {{ref:0}} fue al teatro."}],
      entities: [{mention: "mi hija", name: "Cloe", status: "resolved", type: "person"}],
      writes: [{status: "succeeded", operation: "UPDATED", target: "2026-10-09"}],
      steps: [
        {name: "temporal.interpretation", input: "mañana", output: "mañana → 2026-10-09"},
        {name: "planner", input: "mañana iré al teatro\nContexto temporal: mañana → 2026-10-09", output: "record · calendar_day → 2026-10-09 · Mi {{ref:0}} fue al teatro."},
        {name: "action.write", input: "record · calendar_day → 2026-10-09", output: "succeeded: UPDATED · 2026-10-09\nmi hija → Cloe"},
      ]},
  ],
};
const operational = {
  total_duration_ms: 11000,
  stages: [
    stage("index_barrier", 0),
    stage("application.router", 2250, {model: "gpt-6-luna", provider_calls: [
      stage("application.router", 2250, {model: "gpt-6-luna", usage: {input_tokens: 300, output_tokens: 80}})],
      estimated_cost: cost(0.00011)}),
    stage("tasks.interpretation", 2000, {model: "gpt-6-luna"}),
    stage("planner", 3400, {model: "luna-first", estimated_cost: cost(.0014),
      provider_calls: [stage("planner.luna", 3400, {model: "gpt-5.6-luna", usage: {input_tokens: 12000, cached_input_tokens: 11000, output_tokens: 150}})]}),
    stage("temporal.interpretation", 1900, {model: "gpt-6-luna"}),
    stage("planner", 3450, {model: "luna-first"}),
    stage("action.write", 35),
    stage("git", 55),
  ],
};

function diagnostic() {
  return validateRequestDetail({request_id: "flow-1", operational, flow, changes: {affected_stable_note_ids: ["date:2026-10-09"], units: []}, estimated_cost: cost(.0041)}, "flow-1");
}

test("directed execution graph preserves actual route order, source, dates and metadata", () => {
  const graph = renderExecutionFlow(doc, diagnostic());
  assert.equal(graph.findAll("flow-lane").length, 2);
  assert.equal(graph.findAll("flow-paths-viewport").length, 1);
  assert.equal(graph.findAll("flow-fork").length, 1);
  assert.equal(graph.findAll("flow-join").length, 1);
  assert.equal(graph.findAll("flow-icon").length, graph.findTag("svg").length);
  assert.ok(graph.findTag("path").length > 15, "Odyssey icons must be vectors, not emoji");
  assert.match(graph.textContent, /Desliza horizontalmente/);
  assert.equal(graph.findAll("flow-arrow").length >= 7, true);
  assert.match(graph.textContent, /Hoy tengo que ir al cine/);
  assert.match(graph.textContent, /mañana iré al teatro/);
  const [first, second] = graph.findAll("flow-lane");
  assert.match(first.textContent, /Tasks/);
  assert.doesNotMatch(first.textContent, /2026-10-09/);
  assert.match(second.textContent, /mañana.*2026-10-09/);
  assert.match(second.textContent, /mi hija → Cloe/);
  assert.equal(second.findAll("flow-entities").length, 1);
  assert.equal(second.findAll("flow-entity-resolved").length, 1);
  assert.equal(second.findAll("flow-io").length, 3);
  assert.equal(first.findAll("flow-io").length, 2);
  assert.match(second.textContent, /Entrada/);
  assert.match(second.textContent, /Salida/);
  assert.match(second.textContent, /Contexto temporal/);
  assert.match(second.textContent, /succeeded: UPDATED/);
  assert.match(second.textContent, /record.*calendar_day.*2026-10-09/);
  assert.match(second.textContent, /Mi ↗ referencia fue al teatro/);
  assert.match(second.textContent, /UPDATED.*2026-10-09/);
  assert.match(first.textContent, /tengo que ir al cine/i);
  assert.match(graph.textContent, /Dividido en 2 fragmentos/);
  assert.equal(graph.findAll("flow-icon").length >= 7, true);
  assert.match(first.textContent, /gpt-5.6-luna/);
  assert.match(first.textContent, /11.000 caché/);
  assert.match(first.textContent, /\$0\.001400/);
  assert.match(graph.textContent, /Preparación simultánea/);
  assert.match(graph.textContent, /Rutas completadas/);
  assert.match(first.textContent, /Estado de ruta: completed/);
  assert.match(second.textContent, /Resultado de escritura Core registrado: UPDATED/);
  assert.doesNotMatch(second.textContent, /gpt-6-luna · 35 ms/);
});

test("stage I/O must match actual stage order and remain within strict bounds", () => {
  const mismatched = {...flow, routes: flow.routes.map((route, i) => i ? {...route,
    steps: [{...route.steps[0], name: "planner"}, ...route.steps.slice(1)]} : route)};
  assert.throws(() => validateRequestDetail({request_id: "flow-1", operational, flow: mismatched}, "flow-1"), ProductRequestError);
  const oversized = {...flow, routes: flow.routes.map((route, i) => i ? {...route,
    steps: [{...route.steps[0], output: "x".repeat(769)}, ...route.steps.slice(1)]} : route)};
  assert.throws(() => validateRequestDetail({request_id: "flow-1", operational, flow: oversized}, "flow-1"), ProductRequestError);
});

test("invalid per-route stage mapping fails closed before graph rendering", () => {
  const mismatched = {...flow, routes: [{...flow.routes[0], stage_count: 16}, flow.routes[1]]};
  assert.throws(() => validateRequestDetail({request_id:"flow-1", operational, flow:mismatched}, "flow-1"), ProductRequestError);
});

test("the legacy detail renders actual recorded stages without fabricating routes", () => {
  const graph = renderExecutionFlow(doc, {request_id: "old", operational:{total_duration_ms: 45, stages: [stage("planner", 45)]}});
  assert.equal(graph.findAll("flow-lane").length, 0);
  assert.match(graph.textContent, /no conserva la división de Router/);
  assert.match(graph.textContent, /Planner/);
});

test("a partial route is not presented as a complete success", () => {
  const partial = diagnostic();
  partial.flow.routes[1].status = "failed";
  const graph = renderExecutionFlow(doc, partial);
  assert.match(graph.textContent, /Resultado parcial/);
  assert.doesNotMatch(graph.textContent, /Completado/);
});

test("one route explicitly displays no split and ungrounded mention stays unresolved", () => {
  const actual = diagnostic();
  actual.flow.routes = [{...actual.flow.routes[1], text: "mañana iré al teatro", stage_count: 1,
    entities: [{mention: "mi hija", name: "", status: "unresolved", type: "person"}], steps: [{name: "git", input: "0 notas afectadas", output: "disabled"}]}];
  actual.operational.stages = [actual.operational.stages[1], actual.operational.stages[7]];
  const output = renderExecutionFlow(doc, actual);
  assert.match(output.textContent, /Sin división · 1 camino/);
  assert.doesNotMatch(output.textContent, /mi hija → Cloe/);
  // A stage without entity-binding evidence must never synthesize an identity card.
  assert.equal(output.findAll("flow-entity-resolved").length, 0);
});

test("graph validation rejects ungrounded output injected as an entity name", () => {
  const invalid = {...flow, routes: flow.routes.map((route, i) => i ? {...route,
    entities: [{mention: "mi hija", name: "Cloe", status: "invented", type: "person"}]} : route)};
  assert.throws(() => validateRequestDetail({request_id:"flow-1", operational, flow: invalid}, "flow-1"), ProductRequestError);
});

test("legacy graph still shows a separately matched original user message", () => {
  const graph = renderExecutionFlow(doc, {
    request_id: "old", operational: {total_duration_ms: 42, stages: [stage("planner", 42)]},
  }, {sourceText: "Mi hijo fue al museo ayer"});
  assert.match(graph.textContent, /Mi hijo fue al museo ayer/);
  assert.equal(graph.findAll("flow-lane").length, 0);
  assert.match(graph.textContent, /no conserva la división/);
});

test("mobile route diagram keeps horizontal scroll and never uses emoji icon glyphs", () => {
  const css = readFileSync(new URL("../odyssey_web/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.flow-paths-viewport\s*\{[^}]*overflow-x:\s*auto/);
  assert.match(css, /\.flow-lanes\.flow-multiple\s*\{[^}]*grid-auto-flow:\s*column/);
  const renderer = readFileSync(new URL("../odyssey_web/progress.js", import.meta.url), "utf8");
  assert.match(renderer, /createElementNS\(SVG_NS, "svg"\)/);
  assert.doesNotMatch(renderer, /[💬🧠🗓📁📋🗃✅🔗🔀✍]/u);
});

const checkpoint = {
  version: 1, request_id: "flow-1", stage: "failed_or_unknown", outcome: "failed_or_unknown",
  sequence: 3, observed_at: "2026-10-09T10:02:00+02:00", truncated: false,
  events: [
    {sequence: 1, stage: "routing.started", outcome: "milestone_observed", observed_at: "2026-10-09T10:00:00+02:00"},
    {sequence: 2, stage: "delivery.result_persisted", outcome: "result_persisted", observed_at: "2026-10-09T10:01:00+02:00"},
    {sequence: 3, stage: "failed_or_unknown", outcome: "failed_or_unknown", observed_at: "2026-10-09T10:02:00+02:00"},
  ],
};

test("validated route graph and checkpoint history render without claiming a canonical write", () => {
  const detail = diagnostic();
  detail.flow.routes[0].writes = [];
  const graph = renderExecutionFlow(doc, detail, {checkpoint});
  assert.match(graph.textContent, /Historial de ejecución/);
  assert.match(graph.textContent, /No hay resultado de escritura Core registrado/);
  assert.match(graph.textContent, /Resultado de entrega persistido \(no confirma una nota\)/);
  assert.match(graph.textContent, /Interrumpido o desconocido/);
  assert.doesNotMatch(graph.textContent, /nota escrita/);
});

test("checkpoint validation rejects corrupt and old snapshots while renderer keeps the graph legible", () => {
  const corrupt = {...checkpoint, events: [{...checkpoint.events[0], sequence: 2}]};
  assert.throws(() => validateExecutionCheckpoint(corrupt), DiagnosticPreviewError);
  assert.throws(() => validateExecutionCheckpoint({...checkpoint, unexpected: true}), DiagnosticPreviewError);
  const truncated = structuredClone(checkpoint);
  truncated.sequence = 65;
  truncated.truncated = true;
  truncated.events = checkpoint.events.map((event, index) => ({...event, sequence: 63 + index}));
  truncated.stage = "failed_or_unknown";
  assert.equal(validateExecutionCheckpoint(truncated).truncated, true);
  const graph = renderExecutionFlow(doc, diagnostic(), {checkpoint: corrupt});
  assert.match(graph.textContent, /no es válido o pertenece a un formato anterior/);
  assert.match(graph.textContent, /Rutas completadas/);
});

test("checkpoint with another request ID never attaches to a valid graph", () => {
  const mismatched = {...checkpoint, request_id: "another-actor-request"};
  const graph = renderExecutionFlow(doc, diagnostic(), {checkpoint: mismatched});
  assert.match(graph.textContent, /El historial de ejecución no es válido/);
  assert.match(graph.textContent, /Rutas completadas/);
  assert.equal(graph.findAll("flow-checkpoint-event").length, 0);
  assert.throws(() => validateExecutionCheckpoint({...checkpoint, observed_at: "2026-10-09T12:00:00"}), DiagnosticPreviewError);
});

test("local candidate preview grounds every role in the message and never interpolates HTML", () => {
  const preview = {
    version: 1,
    user_message: "Proyecto <img src=x onerror=alert(1)> tiene un fallo y depende de mañana.",
    candidates: [{
      id: "candidate-project-failure", source: "tiene un fallo", occurrence: 0, dependency_target: null,
      roles: [
        {role: "subject", source: "Proyecto <img src=x onerror=alert(1)>", occurrence: 0, provenance: "explicit", authority: null},
        {role: "predicate", source: "tiene un fallo", occurrence: 0, provenance: "verified", authority: "core"},
        {role: "date", source: "mañana", occurrence: 0, provenance: "inherited", authority: null},
      ],
    }],
  };
  const safe = validateFactCandidatePreview(preview);
  const output = renderFactCandidatePreview(doc, safe);
  assert.match(output.textContent, /Vista previa de diseño/);
  assert.match(output.textContent, /verificado por Core indicado en la prueba/);
  assert.match(output.textContent, /no autoriza ni demuestra una escritura/);
  assert.match(output.textContent, /<img src=x/);
  assert.equal(output.findTag("img").length, 0);
  assert.throws(() => validateFactCandidatePreview({...preview, candidates: [{...preview.candidates[0], roles: [
    {...preview.candidates[0].roles[1], authority: null},
  ]}]}), DiagnosticPreviewError);
  assert.throws(() => validateFactCandidatePreview({...preview, candidates: [{...preview.candidates[0], roles: [
    {...preview.candidates[0].roles[0], source: "invented"},
  ]}]}), DiagnosticPreviewError);
});
