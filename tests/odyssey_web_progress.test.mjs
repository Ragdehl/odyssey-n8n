import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

import {
  createProcessingIndicator,
  formatStage,
  renderExecutionFlow,
  startProgressPolling,
} from "../odyssey_web/progress.js";

class Element {
  constructor(tagName, namespaceURI = null) {
    this.tagName = tagName;
    this.namespaceURI = namespaceURI;
    this.className = "";
    if (namespaceURI === "http://www.w3.org/2000/svg") {
      Object.defineProperty(this, "className", {
        get: () => ({baseVal: this.attributes?.get("class") ?? ""}),
      });
    }
    this.children = [];
    this.attributes = new Map();
    this._textContent = "";
    this.classList = {add: (...names) => {
      this.className = [this.className, ...names].filter(Boolean).join(" ");
    }};
  }
  append(...nodes) { this.children.push(...nodes); }
  set textContent(value) { this._textContent = String(value); this.children = []; }
  get textContent() { return this._textContent + this.children.map((c) => c.textContent).join(""); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  querySelector(selector) {
    for (const child of this.children) {
      const classes = typeof child.className === "string" ? child.className : child.getAttribute("class") ?? "";
      if (selector.startsWith(".") && classes.split(" ").includes(selector.slice(1))) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
}

const fakeDocument = {
  createElement: (tag) => new Element(tag),
  createElementNS: (namespace, tag) => new Element(tag, namespace),
};

test("progress copy keeps only the latest user-facing stage", () => {
  assert.equal(formatStage({stage: "routing.started", details: []}), "Entendiendo tu mensaje…");
  assert.equal(
    formatStage({stage: "routing.ready", details: ["2"]}),
    "He separado tu mensaje en 2 partes.",
  );
  assert.equal(
    formatStage({stage: "temporal.ready", details: ["mañana: 2026-10-08", "20h: 2026-10-08T20:00:00+02:00"]}),
    "Fecha y hora: mañana: 2026-10-08 · 20h: 2026-10-08T20:00:00+02:00",
  );
  assert.equal(
    formatStage({stage: "planner.ready", details: ["Cloe", "Bruno", "Beatriz"]}),
    "He identificado: Cloe, Bruno, Beatriz",
  );
});

test("Core source-boundary review has actual progress labels instead of generic processing", () => {
  assert.match(
    formatStage({stage: "routing.boundary_review_started", details: []}),
    /Comprobando que las partes conservan su significado/,
  );
  assert.match(
    formatStage({stage: "routing.boundary_review_ready", details: []}),
    /He verificado la división/,
  );
  assert.match(
    formatStage({stage: "routing.boundary_review_required", details: []}),
    /Necesito revisar/,
  );
});

test("donut updates monotonically and completes at 100", () => {
  const indicator = createProcessingIndicator(fakeDocument);
  const donut = indicator.element.querySelector(".processing-donut");
  const copy = indicator.element.querySelector(".processing-copy");

  indicator.update({stage: "planner.started", progress: 50, details: []});
  assert.equal(donut.getAttribute("aria-valuenow"), "50");
  assert.equal(copy.textContent, "Organizando la información");
  const svg = donut.children.find((child) => child.tagName === "svg");
  assert.equal(svg.namespaceURI, "http://www.w3.org/2000/svg");
  assert.ok(svg.children.every((child) => child.namespaceURI === svg.namespaceURI));
  assert.equal(svg.children[0].getAttribute("class"), "processing-donut-track");
  assert.equal(svg.children[1].getAttribute("class"), "processing-donut-value");
  const dots = indicator.element.querySelector(".processing-dots");
  assert.equal(dots.children.length, 3);
  assert.ok(dots.children.every((child) => child.className === "processing-dot"));

  indicator.update({stage: "routing.ready", progress: 18, details: []});
  assert.equal(donut.getAttribute("aria-valuenow"), "50");

  indicator.complete();
  assert.equal(donut.getAttribute("aria-valuenow"), "100");
  assert.equal(copy.textContent, "Listo");
  indicator.destroy();
});

test("fact timeline separates facts rather than drawing one continuous border", () => {
  const css = readFileSync(new URL("../odyssey_web/styles.css", import.meta.url), "utf8");
  const groupRule = css.split(".note-fact-group {")[1]?.split("}")[0];
  assert.ok(groupRule);
  assert.ok(!groupRule.includes("border-left: 2px"));
  assert.ok(css.includes(".note-fact-list > li::before"));
  assert.match(css, /@keyframes processing-dot-bounce/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});

test("execution graph makes a validated dependency and its blocked reason visible", () => {
  const graph = renderExecutionFlow(fakeDocument, {
    operational: {total_duration_ms: 3, stages: [
      {name: "application.router", outcome: "completed", duration_ms: 0, provider_calls: []},
      {name: "planner", outcome: "completed", duration_ms: 1, provider_calls: []},
      {name: "planner", outcome: "deferred", duration_ms: 1, provider_calls: []},
      {name: "planner", outcome: "completed", duration_ms: 1, provider_calls: []},
    ]},
    flow: {version: 1, input: "Primero. Después. Independiente.", parallel_preparation: true,
      routes: [
        {capability: "core", text: "Primero.", stage_count: 1, status: "completed", temporal: []},
        {capability: "core", text: "Después.", stage_count: 1, status: "needs_attention", temporal: [],
          depends_on: 0, reason: "ROUTE_DEPENDENCY_PREDECESSOR_NOT_COMPLETED"},
        {capability: "core", text: "Independiente.", stage_count: 1, status: "completed", temporal: []},
      ]},
  });

  assert.match(graph.textContent, /Depende del camino 1/);
  assert.match(graph.textContent, /ROUTE_DEPENDENCY_PREDECESSOR_NOT_COMPLETED/);
});

test("poller tolerates progress failures without affecting delivery", async () => {
  const queued = [];
  let calls = 0;
  const stop = startProgressPolling({
    requestId: "web-test",
    requestProgress: async () => {
      calls += 1;
      if (calls === 1) throw new Error("transient");
      return {stage: "planner.started", progress: 50, details: []};
    },
    onProgress: (value) => queued.push(value.stage),
    setTimeoutImpl(callback) {
      queueMicrotask(callback);
      return 1;
    },
    clearTimeoutImpl() {},
  });
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  stop();

  assert.ok(calls >= 1);
  assert.ok(queued.length <= 1);
});

test("progress never fabricates elapsed percentage while waiting for a provider", () => {
  const originalInterval = globalThis.setInterval;
  let called = false;
  try {
    globalThis.setInterval = () => {called = true; throw new Error("synthetic autonomous progress forbidden");};
    const indicator = createProcessingIndicator(fakeDocument);
    assert.equal(called, false, "no timer should invent progress");
    const donut = indicator.element.querySelector(".processing-donut");
    assert.match(donut.getAttribute("title"), /etapas verificadas/);
    indicator.update({stage: "action.write.started", progress: 84, details: []});
    assert.equal(donut.getAttribute("aria-valuenow"), "84");
    indicator.update({stage: "action.write.started", progress: 84, details: []});
    assert.equal(donut.getAttribute("aria-valuenow"), "84");
    indicator.update({stage: "finalizing", progress: 94, details: []});
    assert.equal(donut.getAttribute("aria-valuenow"), "94");
    indicator.complete();
    assert.equal(donut.getAttribute("aria-valuenow"), "100");
    indicator.destroy();
  } finally {
    globalThis.setInterval = originalInterval;
  }
});

test("donut displays newly observed App label and ignores stale sequence after concurrent stages", () => {
  const indicator = createProcessingIndicator(fakeDocument);
  const donut = indicator.element.querySelector(".processing-donut");
  const copy = indicator.element.querySelector(".processing-copy");
  indicator.update({request_id: "test", stage: "planner.started", sequence: 5, progress: 50});
  indicator.update({request_id: "test", stage: "events.classify_occurrence.started", sequence: 6,
    progress: 50, stage_view: {version: 1, label: "Events · análisis en curso", icon: "result"}});
  assert.equal(copy.textContent, "Events · análisis en curso");
  assert.equal(donut.getAttribute("aria-valuenow"), "50");
  indicator.update({request_id: "test", stage: "temporal.ready", sequence: 4, progress: 42});
  assert.equal(copy.textContent, "Events · análisis en curso");
  indicator.update({request_id: "test", stage: "events.classify_occurrence.ready", sequence: 7,
    progress: 50, stage_view: {version: 1, label: "Events · preparado", icon: "result"}});
  assert.equal(copy.textContent, "Events · preparado");
  indicator.complete();
  indicator.update({request_id: "test", stage: "temporal.ready", sequence: 8, progress: 90});
  assert.equal(copy.textContent, "Listo");
  assert.equal(donut.getAttribute("aria-valuenow"), "100");
});

test("invalid stage view cannot replace observed safe fallback", () => {
  assert.equal(formatStage({stage: "planner.started", stage_view: {
    version: 1, label: "bad", icon: "unknown"
  }}), "Organizando la información…");
});

test("polling ignores mismatched deliveries and stale sequence but accepts future stages", async () => {
  const queued = [];
  const inputs = [
    {request_id: "different-request", sequence: 2, stage: "planner.ready", progress: 68},
    {request_id: "ours", sequence: 3, stage: "events.prepare.started", progress: 42},
    {request_id: "ours", sequence: 2, stage: "temporal.ready", progress: 42},
    {request_id: "ours", sequence: 4, stage: "events.prepare.ready", progress: 42},
  ];
  const timers = [];
  const stop = startProgressPolling({
    requestId: "ours",
    requestProgress: async () => inputs.shift() ?? {request_id:"ours", sequence:4, stage:"events.prepare.ready", progress:42},
    onProgress: snapshot => queued.push(snapshot.stage),
    setTimeoutImpl: callback => {timers.push(callback); return timers.length;},
    clearTimeoutImpl() {},
  });
  await new Promise(resolve => setImmediate(resolve));
  for (let i = 0; i < 3; i += 1) {
    const task = timers.shift();
    task();
    await new Promise(resolve => setImmediate(resolve));
  }
  stop();
  assert.deepEqual(queued, ["events.prepare.started", "events.prepare.ready"]);
});

test("execution graph displays both verified Core and Session predecessor routes", () => {
  const graph = renderExecutionFlow(fakeDocument, {
    operational: {total_duration_ms: 3, stages: [
      {name: "application.router", outcome: "completed", duration_ms: 0, provider_calls: []},
      ...Array.from({length: 4}, () =>
        ({name: "planner", outcome: "completed", duration_ms: 1, provider_calls: []})),
    ]},
    flow: {version: 1, input: "Core A. Core B. Start. Stop.", parallel_preparation: false,
      routes: [
        {capability: "core", text: "Core A.", stage_count: 1, status: "completed", temporal: []},
        {capability: "core", text: "Core B.", stage_count: 1, status: "completed", temporal: []},
        {capability: "tasks", text: "Start.", stage_count: 1, status: "completed", temporal: [],
          depends_on: 0, reason: null},
        {capability: "tasks", text: "Stop.", stage_count: 1, status: "completed", temporal: [],
          depends_on: 2, reason: null, dependency_indices: [0, 2]},
      ]},
  });
  assert.match(graph.textContent, /Depende del camino 1/);
  assert.match(graph.textContent, /Depende de los caminos 1, 3/);
});


test("graph reports an actual failed Core read preflight without inventing missing identity", () => {
  const graph = renderExecutionFlow(fakeDocument, {
    operational: {total_duration_ms: 5, stages: [
      {name: "core.read_preflight", outcome: "failed", duration_ms: 2, error_category: "ValueError", provider_calls: []},
      {name: "application.router", outcome: "completed", duration_ms: 1, provider_calls: []},
    ]},
    execution_ledger: {status: "needs_attention", stages: [
      {name: "core.read_preflight", outcome: "failed", route_index: null, parent_stage: null},
    ], write_receipts: [], affected_stable_note_ids: [], events: [], routes: [], events_truncated: false},
  }, {sourceText: "¿Quién es mi padre?"});
  assert.match(graph.textContent, /Core · interpretación inicial de lectura/);
  assert.match(graph.textContent, /no demuestra que la información buscada sea inexistente/);
  assert.match(graph.textContent, /Necesita revisión/);
  assert.doesNotMatch(graph.textContent, /padre no existe|no tienes padre/i);
});

test("graph admits that it cannot identify failure stage instead of saying every route completed", () => {
  const graph = renderExecutionFlow(fakeDocument, {
    operational: {total_duration_ms: 4, stages: [
      {name: "planner", outcome: "completed", duration_ms: 4, provider_calls: []},
    ]},
    execution_ledger: {status: "needs_attention", stages: [
      {name: "planner", outcome: "completed", route_index: null, parent_stage: null},
    ], write_receipts: [], affected_stable_note_ids: [], events: [], routes: [], events_truncated: false},
  });
  assert.match(graph.textContent, /historial no identifica una etapa fallida/);
  assert.match(graph.textContent, /Necesita revisión/);
  assert.doesNotMatch(graph.textContent, /Rutas completadas/);
});
