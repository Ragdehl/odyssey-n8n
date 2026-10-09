const POLL_MS = 350;
const CREEP_MS = 280;
const SVG_NS = "http://www.w3.org/2000/svg";

const STAGE_COPY = {
  starting: "Preparando tu solicitud…",
  "routing.started": "Entendiendo tu mensaje…",
  "routing.ready": "He entendido cómo dividir tu mensaje.",
  "temporal.started": "Interpretando fechas y horas…",
  "temporal.ready": "He interpretado la fecha y la hora.",
  "planner.started": "Organizando la información…",
  "planner.ready": "He identificado las referencias importantes.",
  "action.retrieve.started": "Buscando la información relacionada…",
  "action.delegate.started": "Preparando la siguiente acción…",
  "action.write.started": "Guardando la información…",
  finalizing: "Terminando…",
};

function formatStage(snapshot) {
  const details = Array.isArray(snapshot?.details)
    ? snapshot.details.filter((item) => typeof item === "string" && item.trim()).slice(0, 6)
    : [];
  if (snapshot?.stage === "routing.ready" && details[0]) {
    return "He separado tu mensaje en " + details[0] + " partes.";
  }
  if (snapshot?.stage === "temporal.ready" && details.length) {
    return "Fecha y hora: " + details.join(" · ");
  }
  if (snapshot?.stage === "planner.ready" && details.length) {
    return "He identificado: " + details.join(", ");
  }
  return STAGE_COPY[snapshot?.stage] ?? "Odyssey está trabajando…";
}

function boundedProgress(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

export function createProcessingIndicator(documentImpl = document) {
  const wrapper = documentImpl.createElement("span");
  wrapper.className = "processing-indicator";

  const donut = documentImpl.createElement("span");
  donut.className = "processing-donut";
  donut.setAttribute("role", "progressbar");
  donut.setAttribute("aria-valuemin", "0");
  donut.setAttribute("aria-valuemax", "100");
  donut.setAttribute("aria-valuenow", "0");

  const svg = documentImpl.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 44 44");
  svg.setAttribute("aria-hidden", "true");
  const track = documentImpl.createElementNS(SVG_NS, "circle");
  track.setAttribute("class", "processing-donut-track");
  track.setAttribute("cx", "22");
  track.setAttribute("cy", "22");
  track.setAttribute("r", "17");
  track.setAttribute("pathLength", "100");
  const value = documentImpl.createElementNS(SVG_NS, "circle");
  value.setAttribute("class", "processing-donut-value");
  value.setAttribute("cx", "22");
  value.setAttribute("cy", "22");
  value.setAttribute("r", "17");
  value.setAttribute("pathLength", "100");
  value.setAttribute("stroke-dasharray", "100");
  value.setAttribute("stroke-dashoffset", "100");
  svg.append(track, value);

  const percentage = documentImpl.createElement("span");
  percentage.className = "processing-percent";
  percentage.textContent = "0";
  donut.append(svg, percentage);

  const copy = documentImpl.createElement("span");
  copy.className = "processing-copy";
  const dots = documentImpl.createElement("span");
  dots.className = "processing-dots";
  dots.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    const dot = documentImpl.createElement("span");
    dot.className = "processing-dot";
    dots.append(dot);
  }
  const copyRow = documentImpl.createElement("span");
  copyRow.className = "processing-copy-row";
  copyRow.append(copy, dots);
  const updateCopy = (text) => { copy.textContent = text.replace(/[…\s]+$/u, ""); };
  updateCopy(STAGE_COPY.starting);
  wrapper.append(donut, copyRow);

  let displayed = 0;
  let stageTarget = 0;
  const applyProgress = (next) => {
    displayed = boundedProgress(next);
    donut.setAttribute("aria-valuenow", String(displayed));
    value.setAttribute("stroke-dashoffset", String(100 - displayed));
    percentage.textContent = String(displayed);
  };

  const creepTimer = setInterval(() => {
    const cap = Math.min(96, stageTarget + 9);
    if (displayed < cap) applyProgress(displayed + 1);
  }, CREEP_MS);
  creepTimer?.unref?.();

  return {
    element: wrapper,
    update(snapshot) {
      stageTarget = Math.max(stageTarget, boundedProgress(snapshot?.progress));
      updateCopy(formatStage(snapshot));
      applyProgress(Math.max(displayed, stageTarget));
    },
    complete() {
      stageTarget = 100;
      updateCopy("Listo");
      applyProgress(100);
    },
    destroy() {
      clearInterval(creepTimer);
    },
  };
}

export function startProgressPolling({
  requestId,
  requestProgress,
  onProgress,
  setTimeoutImpl = setTimeout,
  clearTimeoutImpl = clearTimeout,
}) {
  let stopped = false;
  let timer = null;

  const poll = async () => {
    if (stopped) return;
    try {
      const snapshot = await requestProgress(requestId);
      if (!stopped && snapshot && typeof snapshot === "object") onProgress(snapshot);
    } catch {
      // Progress is optional UX. Delivery continues on the authoritative request channel.
    }
    if (!stopped) {
      timer = setTimeoutImpl(poll, POLL_MS);
      timer?.unref?.();
    }
  };

  void poll();
  return () => {
    stopped = true;
    if (timer !== null) clearTimeoutImpl(timer);
  };
}

export {formatStage};


/** Visualize only bounded, evidence-backed execution provenance, never simulated stages. */
function element(doc, tag, className = "", text = "") {
  const node = doc.createElement(tag);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function arrow(doc, name = "") {
  const line = element(doc, "div", "flow-arrow");
  line.setAttribute("aria-hidden", "true");
  if (name) line.classList.add(name);
  return line;
}

function chip(doc, text, type = "", title = "") {
  const value = element(doc, "span", `flow-chip ${type}`, text);
  if (title) value.title = title;
  return value;
}

function stageTitle(name) {
  if (name === "application.router") return "Router";
  if (name === "planner") return "Planner";
  if (name === "temporal.interpretation") return "Temporal";
  if (name === "temporal.coherence") return "Coherencia de fechas";
  if (name === "tasks.interpretation") return "Tasks";
  if (name === "git") return "Git";
  if (name === "index_barrier") return "Índices";
  if (name === "pending") return "Pendientes";
  if (name.startsWith("action.write") || name.startsWith("write")) return "Core · guardar";
  if (name.startsWith("action.")) return "Core · " + name.slice(7).replaceAll(".", " · ");
  if (name.startsWith("tasks.")) return "Tasks · " + name.slice(6).replaceAll("_", " ");
  return name.replaceAll("_", " ").replaceAll(".", " · ");
}

function duration(ms) {
  return typeof ms === "number" && Number.isFinite(ms) ? `${Math.round(ms)} ms` : "";
}

function tokens(usage) {
  if (!usage || typeof usage !== "object") return [];
  const results = [];
  if (Number.isInteger(usage.input_tokens)) results.push([`Entrada ${usage.input_tokens.toLocaleString("es-ES")}`, "Tokens de entrada enviados al modelo."]);
  if (Number.isInteger(usage.cached_input_tokens)) results.push([`Caché ${usage.cached_input_tokens.toLocaleString("es-ES")}`, "Parte de la entrada que el proveedor informó como caché."]);
  if (Number.isInteger(usage.cache_write_tokens)) results.push([`Escritura caché ${usage.cache_write_tokens.toLocaleString("es-ES")}`, "Tokens de entrada informados como escritura de caché por el proveedor."]);
  if (Number.isInteger(usage.output_tokens)) results.push([`Salida ${usage.output_tokens.toLocaleString("es-ES")}`, "Tokens de salida devueltos por el modelo."]);
  if (Number.isInteger(usage.reasoning_tokens)) results.push([`Razonamiento ${usage.reasoning_tokens.toLocaleString("es-ES")}`, "El razonamiento es un subconjunto de los tokens de salida; no se suma otra vez."]);
  return results;
}

function cost(value) {
  return value?.status === "estimated" && typeof value.amount_usd === "number"
    ? `Coste estimado ~$${value.amount_usd.toFixed(6)}` : "";
}

function costOrUnavailable(value, hasProviderCall) {
  return cost(value) || (hasProviderCall ? "Coste no disponible" : "");
}

// Reuse Odyssey's thin, rounded SVG stroke language; no platform emoji glyphs.
const FLOW_ICONS = Object.freeze({
  source: ["M21 12a8 8 0 0 1-8 8H7l-4 2 1.3-4.2A8 8 0 1 1 21 12Z"],
  fragment: ["M21 12a8 8 0 0 1-8 8H7l-4 2 1.3-4.2A8 8 0 1 1 21 12Z"],
  router: ["M12 3v6", "M12 9 5 16", "M12 9l7 7", "M3 16h4v4H3z", "M17 16h4v4h-4z", "M10 1h4v4h-4z"],
  tasks: ["M5 4h14v16H5z", "m8 12 2.5 2.5L16 9"],
  temporal: ["M5 5h14v14H5z", "M8 3v4M16 3v4M5 9h14", "M9 13h2v2H9z"],
  planner: ["M12 4a4 4 0 0 0-7 3 4 4 0 0 0-.5 7 4 4 0 0 0 4.5 6 4 4 0 0 0 3-2", "M12 4a4 4 0 0 1 7 3 4 4 0 0 1 .5 7 4 4 0 0 1-4.5 6 4 4 0 0 1-3-2", "M12 4v16", "M8 9l4 3 4-3", "M8 16l4-3 4 3"],
  core: ["M12 4c4.5 0 8 1.4 8 3s-3.5 3-8 3-8-1.4-8-3 3.5-3 8-3Z", "M4 7v10c0 1.7 3.5 3 8 3s8-1.3 8-3V7", "M4 12c0 1.7 3.5 3 8 3s8-1.3 8-3"],
  git: ["M3 7h7l2 2h9v11H3z", "M3 7V5h7l2 2"],
  index: ["M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z", "m16 16 5 5"],
  pending: ["M6 3h12v18H6z", "M9 9h6M9 13h6M9 17h4"],
  result: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "m7 12 3 3 7-7"],
  entities: ["M10 13a5 5 0 0 0 7 .4l2-2a5 5 0 0 0-7-7l-1.2 1.2", "M14 11a5 5 0 0 0-7-.4l-2 2a5 5 0 0 0 7 7l1.2-1.2"],
});

function headingWithIcon(doc, label, icon) {
  const heading = element(doc, "h4", "flow-node-heading");
  const emblem = element(doc, "span", "flow-icon");
  emblem.setAttribute("aria-hidden", "true");
  const svg = doc.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const pathData of (FLOW_ICONS[icon] || FLOW_ICONS.result)) {
    const path = doc.createElementNS(SVG_NS, "path");
    path.setAttribute("d", pathData);
    svg.append(path);
  }
  emblem.append(svg);
  heading.append(emblem, element(doc, "span", "", label));
  return heading;
}

function textInput(doc, source) {
  const preview = element(doc, "p", "flow-input", source);
  preview.setAttribute("aria-label", "Texto analizado");
  return preview;
}

function detailLine(doc, text, kind = "") {
  return element(doc, "p", `flow-semantics-line ${kind}`, text);
}

function ioRow(doc, label, value, missing = "") {
  const row = element(doc, "div", "flow-io-row");
  row.append(element(doc, "span", "flow-io-label", label));
  row.append(element(doc, "p", `flow-io-value ${value ? "" : "flow-io-missing"}`,
    value || missing));
  return row;
}

function ioPanel(doc, input, output) {
  const wrapper = element(doc, "div", "flow-io");
  wrapper.append(ioRow(doc, "Entrada", input, "No registrada"));
  wrapper.append(ioRow(doc, "Salida", output,
    "No hay salida estructurada validada para esta etapa"));
  return wrapper;
}

function stageCard(doc, stage, route = null, observedStep = null) {
  const card = element(doc, "article", `flow-card ${stage.outcome === "failed" ? "flow-card-failed" : ""}`);
  const icon = stage.name === "application.router" ? "router" :
    stage.name === "planner" ? "planner" :
    stage.name === "temporal.interpretation" ? "temporal" :
    stage.name === "tasks.interpretation" ? "tasks" :
    stage.name === "git" ? "git" :
    stage.name === "index_barrier" ? "index" :
    stage.name === "pending" ? "pending" :
    stage.name.startsWith("action.") ? "core" : "result";
  card.append(headingWithIcon(doc, stageTitle(stage.name), icon));
  if (observedStep) {
    card.append(ioPanel(doc, observedStep.input,
      observedStep.output.replace(/\{\{ref:\d+\}\}/gu, "↗ referencia")));
  } else if (route && ["planner", "tasks.interpretation", "temporal.interpretation"].includes(stage.name)) {
    card.append(textInput(doc, route.text));
  }
  if (!observedStep && stage.name === "planner" && route?.plan?.length) {
    const decisions = element(doc, "div", "flow-semantics");
    for (const item of route.plan) {
      decisions.append(detailLine(doc, `${item.operation} · ${item.type || "nota"} → ${item.target}`));
      if (item.fact) decisions.append(detailLine(doc,
        item.fact.replace(/\{\{ref:\d+\}\}/gu, "↗ referencia"), "flow-semantic-fact"));
    }
    card.append(decisions);
  }
  if (!observedStep && stage.name.startsWith("action.") && route) {
    const steps = element(doc, "div", "flow-semantics");
    for (const item of route.writes || []) {
      steps.append(detailLine(doc, `${item.operation} · ${item.target} (${item.status})`));
    }
    if (steps.children.length) card.append(steps);
  }
  if (stage.outcome === "failed" || stage.outcome === "deferred") {
    card.append(element(doc, "p", "flow-error", stage.error_category || stage.outcome));
  }
  if (stage.name === "temporal.interpretation" && route?.temporal?.length) {
    const conversions = element(doc, "div", "flow-temporal");
    for (const pair of route.temporal) {
      conversions.append(element(doc, "span", "flow-human-time", pair.source));
      conversions.append(element(doc, "span", "flow-time-arrow", "→"));
      conversions.append(element(doc, "strong", "flow-normalized-time", pair.value));
    }
    card.append(conversions);
  }
  const stats = element(doc, "div", "flow-stats");
  const calls = stage.provider_calls ?? [];
  const model = calls.length === 1 ? calls[0].model || stage.model : stage.model;
  const info = [model, stage.reasoning_effort, duration(stage.duration_ms),
    calls.length ? `${calls.length} llamada${calls.length === 1 ? "" : "s"}` : "", costOrUnavailable(stage.estimated_cost, Boolean(calls.length || model))];
  for (const value of info.filter(Boolean)) stats.append(chip(doc, String(value)));
  const usage = stage.usage || (calls.length === 1 ? calls[0].usage : null);
  for (const [label, title] of tokens(usage)) stats.append(chip(doc, label, "flow-chip-tokens", title));
  if (stats.children.length) card.append(stats);
  // Provider fallbacks must remain inspectable, not collapsed into a fictional model.
  if (calls.length > 1) {
    const attempts = element(doc, "details", "flow-provider-details");
    attempts.append(element(doc, "summary", "", `${calls.length} llamadas de proveedor`));
    for (const call of calls) {
      const attempt = element(doc, "div", "flow-provider-line");
      attempt.append(element(doc, "p", "", [call.model || call.name, duration(call.duration_ms), call.outcome,
        costOrUnavailable(call.estimated_cost, Boolean(call.model))].filter(Boolean).join(" · ")));
      for (const [label, title] of tokens(call.usage)) attempt.append(chip(doc, label, "flow-chip-tokens", title));
      attempts.append(attempt);
    }
    card.append(attempts);
  }
  return card;
}

function entitiesCard(doc, entities) {
  const node = element(doc, "article", "flow-card flow-entities");
  node.append(headingWithIcon(doc, "Referencias · Core", "entities"));
  const output = element(doc, "div", "flow-semantics");
  for (const item of entities) {
    const target = item.status === "resolved" ? item.name : "Resolución no disponible";
    output.append(detailLine(doc, `${item.mention} → ${target}`,
      item.status === "resolved" ? "flow-entity-resolved" : "flow-entity-unresolved"));
  }
  node.append(output);
  return node;
}

function routeEvidence(doc, route) {
  const evidence = element(doc, "div", "flow-route-evidence");
  evidence.append(detailLine(doc, `Estado de ruta: ${route.status}`, `flow-route-status flow-route-status-${route.status}`));
  if (route.writes?.length) {
    for (const write of route.writes) {
      evidence.append(detailLine(doc, `Resultado de escritura Core registrado: ${write.operation} · ${write.target} (${write.status})`, "flow-write-evidence"));
    }
  } else {
    evidence.append(detailLine(doc, "No hay resultado de escritura Core registrado para esta ruta.", "flow-no-write"));
  }
  return evidence;
}

function plainCard(doc, heading, body, kind = "") {
  const node = element(doc, "article", `flow-card flow-${kind}`);
  node.append(headingWithIcon(doc, heading, kind === "source" ? "source" : kind === "fragment" ? "fragment" : kind === "success" ? "result" : "result"));
  if (body) node.append(element(doc, "p", "flow-node-text", body));
  return node;
}

/** Render a responsive directed graph driven by validated per-route stage counts. */
export function renderExecutionFlow(doc, detail, {sourceText = "", checkpoint} = {}) {
  const root = element(doc, "section", "flow-graph");
  root.setAttribute("aria-label", "Diagrama de ejecución de la solicitud");
  const stages = detail.operational.stages;
  const flow = detail.flow;
  if (flow?.input || sourceText) {
    root.append(plainCard(doc, "Mensaje del usuario", flow?.input || sourceText, "source"));
    root.append(arrow(doc));
  }
  if (!flow?.routes?.length) {
    root.append(element(doc, "p", "flow-legacy", "Esta solicitud no conserva la división de Router ni las transformaciones por etapa. El mensaje original y las métricas registradas sí están disponibles."));
  }
  const routerIndex = stages.findIndex(stage => stage.name === "application.router");
  const prefix = routerIndex < 0 ? [] : stages.slice(0, routerIndex);
  if (prefix.length) {
    const prelim = element(doc, "details", "flow-technical");
    prelim.append(element(doc, "summary", "", "Preparación inicial"));
    for (const stage of prefix) prelim.append(stageCard(doc, stage));
    root.append(prelim);
  }
  if (routerIndex >= 0) {
    const router = stageCard(doc, stages[routerIndex]);
    if (flow?.routes?.length) {
      router.append(detailLine(doc, flow.routes.length > 1
        ? `Dividido en ${flow.routes.length} fragmentos`
        : "Sin división · 1 camino", "flow-split-result"));
    }
    if (flow?.routes?.length) {
      const routeOutput = flow.routes.map((route, index) =>
        `${index + 1}. ${route.capability} → ${route.text}`).join("\n");
      router.append(ioPanel(doc, flow.input, routeOutput));
    }
    root.append(router);
    if (!flow?.routes?.length) root.append(arrow(doc));
  }
  let consumed = routerIndex + 1;
  if (flow?.routes?.length) {
    const paths = element(doc, "div", "flow-paths-viewport");
    const inner = element(doc, "div", "flow-paths-inner");
    inner.append(arrow(doc, flow.routes.length > 1 ? "flow-fork" : "flow-single"));
    const lanes = element(doc, "div", "flow-lanes");
    if (flow.routes.length > 1) {
      lanes.classList.add("flow-multiple");
      root.append(element(doc, "p", "flow-lane-caption", "Desliza horizontalmente para ver cada camino"));
    }
    if (flow.parallel_preparation) {
      root.append(element(doc, "p", "flow-lane-caption", "Preparación simultánea · aplicación en orden"));
    }
    if (flow.routes.some(route => !route.steps)) {
      root.append(element(doc, "p", "flow-legacy",
        "Esta solicitud conserva sus rutas, pero es anterior al registro de entrada y salida por etapa."));
    }
    for (const [index, route] of flow.routes.entries()) {
      const lane = element(doc, "section", "flow-lane");
      lane.setAttribute("aria-label", `Camino ${index + 1}: ${route.capability}`);
      const fragment = plainCard(doc, `${index + 1} · ${route.capability}`, route.text, "fragment");
      if (route.depends_on !== undefined) {
        fragment.append(detailLine(doc, `Depende del camino ${route.depends_on + 1}`, "flow-dependency"));
        if (route.reason) fragment.append(detailLine(doc, route.reason, "flow-error"));
      }
      lane.append(fragment);
      lane.append(routeEvidence(doc, route));
      const routeStages = stages.slice(consumed, consumed + route.stage_count);
      consumed += route.stage_count;
      let entitiesDisplayed = false;
      for (const [stageIndex, stage] of routeStages.entries()) {
        if (stage.name === "pending" && stage.outcome === "skipped") continue;
        if (!entitiesDisplayed && stage.name.startsWith("action.") && route.entities?.length) {
          lane.append(arrow(doc));
          lane.append(entitiesCard(doc, route.entities));
          entitiesDisplayed = true;
        }
        lane.append(arrow(doc));
        lane.append(stageCard(doc, stage, route,
          route.steps ? route.steps[stageIndex] : null));
      }
      if (routeStages.length === 0) {
        lane.append(arrow(doc));
        lane.append(plainCard(doc, "Sin etapas registradas", route.status, "empty"));
      }
      lanes.append(lane);
    }
    inner.append(lanes);
    inner.append(arrow(doc, flow.routes.length > 1 ? "flow-join" : "flow-single"));
    paths.append(inner);
    root.append(paths);
  } else {
    const linear = element(doc, "div", "flow-linear");
    for (const stage of stages.slice(Math.max(0, consumed))) {
      linear.append(arrow(doc));
      linear.append(stageCard(doc, stage));
    }
    root.append(linear);
    consumed = stages.length;
  }
  const tail = stages.slice(consumed);
  if (tail.length) {
    const more = element(doc, "details", "flow-technical");
    more.append(element(doc, "summary", "", "Cierre y tareas auxiliares"));
    for (const stage of tail) more.append(stageCard(doc, stage));
    root.append(more);
  }
  if (!flow?.routes?.length) root.append(arrow(doc, "flow-single"));
  const outcomes = flow?.routes?.map(route => route.status) || [];
  const result = outcomes.length && outcomes.every(s => s === "completed") ? "Rutas completadas"
    : outcomes.some(s => s === "completed") ? "Resultado parcial"
    : outcomes.includes("needs_attention") ? "Necesita aclaración"
    : outcomes.includes("failed") ? "No completado" : "Resultado de Odyssey";
  const end = plainCard(doc, result, "", result === "Rutas completadas" ? "success" : "outcome");
  const stats = element(doc, "div", "flow-stats");
  const finalCost = cost(detail.estimated_cost);
  const totalLabel = finalCost ? finalCost.replace("Coste estimado", "Coste total estimado")
    : "Coste total no disponible";
  for (const text of [duration(detail.operational.total_duration_ms), totalLabel,
    detail.changes?.affected_stable_note_ids?.length ? `${detail.changes.affected_stable_note_ids.length} notas` : ""].filter(Boolean)) {
    stats.append(chip(doc, text));
  }
  end.append(stats);
  root.append(end);
  if (checkpoint !== undefined) root.append(renderCheckpointHistory(doc, checkpoint, detail.request_id));
  return root;
}

const CHECKPOINT_STAGES = new Set([
  "starting", "routing.started", "routing.ready", "temporal.started", "temporal.ready",
  "planner.started", "planner.ready", "action.retrieve.started", "action.delegate.started",
  "action.write.started", "finalizing", "delivery.result_persisted", "processing.returned",
  "failed_or_unknown",
]);
const CHECKPOINT_OUTCOMES = new Set([
  "milestone_observed", "result_persisted", "processing_returned", "failed_or_unknown",
]);
const CHECKPOINT_TERMINALS = new Map([
  ["delivery.result_persisted", "result_persisted"],
  ["processing.returned", "processing_returned"],
  ["failed_or_unknown", "failed_or_unknown"],
]);

export class DiagnosticPreviewError extends Error {}

function exactKeys(value, keys) {
  return Object.keys(value).length === keys.length && Object.keys(value).every(key => keys.includes(key));
}

function validTimestamp(value) {
  return typeof value === "string" && value.length <= 40 &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u.test(value) &&
    Number.isFinite(Date.parse(value));
}

function validateCheckpointEvent(event, expectedSequence) {
  if (!event || typeof event !== "object" || Array.isArray(event) ||
      !exactKeys(event, ["sequence", "stage", "outcome", "observed_at"]) ||
      !Number.isInteger(event.sequence) || event.sequence !== expectedSequence ||
      !CHECKPOINT_STAGES.has(event.stage) || !CHECKPOINT_OUTCOMES.has(event.outcome) ||
      !validTimestamp(event.observed_at)) {
    throw new DiagnosticPreviewError("Invalid execution checkpoint event.");
  }
  const required = CHECKPOINT_TERMINALS.get(event.stage) || "milestone_observed";
  if (event.outcome !== required) throw new DiagnosticPreviewError("Invalid checkpoint outcome.");
  return {sequence: event.sequence, stage: event.stage, outcome: event.outcome, observed_at: event.observed_at};
}

/** Validate the source-free, optional runtime checkpoint record before read-only display. */
export function validateExecutionCheckpoint(value) {
  const keys = ["version", "request_id", "stage", "outcome", "sequence", "observed_at", "events", "truncated"];
  if (!value || typeof value !== "object" || Array.isArray(value) || !exactKeys(value, keys) ||
      value.version !== 1 || typeof value.request_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u.test(value.request_id) ||
      !Number.isInteger(value.sequence) || value.sequence < 1 || value.sequence > 2 ** 31 - 1 ||
      typeof value.truncated !== "boolean" || !Array.isArray(value.events) ||
      value.events.length < 1 || value.events.length > 64) {
    throw new DiagnosticPreviewError("Invalid execution checkpoint.");
  }
  const events = value.events.map((event, index) => validateCheckpointEvent(
    event, value.sequence - value.events.length + index + 1,
  ));
  const latest = events.at(-1);
  if (value.truncated !== (value.sequence > events.length) ||
      !latest || value.stage !== latest.stage || value.outcome !== latest.outcome ||
      value.observed_at !== latest.observed_at) {
    throw new DiagnosticPreviewError("Inconsistent execution checkpoint.");
  }
  return {version: 1, request_id: value.request_id, stage: latest.stage, outcome: latest.outcome,
    sequence: value.sequence, observed_at: latest.observed_at, events, truncated: value.truncated};
}

function checkpointLabel(event) {
  if (event.outcome === "failed_or_unknown") return "Interrumpido o desconocido";
  if (event.outcome === "result_persisted") return "Resultado de entrega persistido (no confirma una nota)";
  if (event.outcome === "processing_returned") return "Procesamiento devuelto (no confirma una nota)";
  return "Hito observado";
}

/** Render only an already validated bounded checkpoint snapshot; it has no write authority. */
export function renderCheckpointHistory(doc, checkpoint, expectedRequestId = null) {
  const section = element(doc, "section", "flow-checkpoint-history");
  section.append(element(doc, "h3", "flow-checkpoint-heading", "Historial de ejecución (solo diagnóstico)"));
  let safe;
  try {
    safe = validateExecutionCheckpoint(checkpoint);
    if (expectedRequestId !== null && safe.request_id !== expectedRequestId) {
      throw new DiagnosticPreviewError("Checkpoint request does not match detail.");
    }
  } catch {
    section.append(element(doc, "p", "flow-diagnostic-warning", "El historial de ejecución no es válido o pertenece a un formato anterior; no se muestra."));
    return section;
  }
  if (safe.truncated) section.append(element(doc, "p", "flow-diagnostic-warning", "El historial está truncado: los hitos iniciales no están disponibles."));
  const list = element(doc, "ol", "flow-checkpoint-list");
  for (const event of safe.events) {
    const item = element(doc, "li", `flow-checkpoint-event flow-checkpoint-${event.outcome}`);
    item.append(element(doc, "strong", "", `${event.sequence} · ${stageTitle(event.stage)}`));
    item.append(element(doc, "span", "", checkpointLabel(event)));
    item.append(element(doc, "span", "", event.observed_at));
    list.append(item);
  }
  section.append(list);
  return section;
}

const CANDIDATE_ROLES = new Set(["subject", "participants", "object", "location", "time", "date", "predicate", "condition"]);
const CANDIDATE_PROVENANCE = new Set(["explicit", "inherited", "overridden", "unresolved", "verified"]);

function occurrenceAt(message, source, occurrence) {
  let start = -1;
  for (let index = 0; index <= occurrence; index += 1) {
    start = message.indexOf(source, start + 1);
    if (start < 0) return false;
  }
  return true;
}

/** Validate a local-only v1 candidate fixture; it is not a Router or persistence contract. */
export function validateFactCandidatePreview(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      !exactKeys(value, ["version", "user_message", "candidates"]) || value.version !== 1 ||
      typeof value.user_message !== "string" || !value.user_message || value.user_message.length > 4096 ||
      !Array.isArray(value.candidates) || value.candidates.length < 1 || value.candidates.length > 26) {
    throw new DiagnosticPreviewError("Invalid fact-candidate preview.");
  }
  const ids = new Set();
  const candidates = value.candidates.map(candidate => {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate) ||
        !exactKeys(candidate, ["id", "source", "occurrence", "roles", "dependency_target"]) ||
        typeof candidate.id !== "string" || !/^candidate-[A-Za-z0-9_-]{1,48}$/u.test(candidate.id) || ids.has(candidate.id) ||
        typeof candidate.source !== "string" || !candidate.source || candidate.source.length > 240 ||
        !Number.isInteger(candidate.occurrence) || candidate.occurrence < 0 || !occurrenceAt(value.user_message, candidate.source, candidate.occurrence) ||
        !Array.isArray(candidate.roles) || candidate.roles.length < 1 || candidate.roles.length > 8 ||
        (candidate.dependency_target !== null && (typeof candidate.dependency_target !== "string" || !/^candidate-[A-Za-z0-9_-]{1,48}$/u.test(candidate.dependency_target)))) {
      throw new DiagnosticPreviewError("Invalid fact candidate.");
    }
    ids.add(candidate.id);
    const roles = candidate.roles.map(role => {
      if (!role || typeof role !== "object" || Array.isArray(role) ||
          !exactKeys(role, ["role", "source", "occurrence", "provenance", "authority"]) ||
          !CANDIDATE_ROLES.has(role.role) || typeof role.source !== "string" || !role.source || role.source.length > 160 ||
          !Number.isInteger(role.occurrence) || role.occurrence < 0 || !occurrenceAt(value.user_message, role.source, role.occurrence) ||
          !CANDIDATE_PROVENANCE.has(role.provenance) ||
          (role.authority !== null && role.authority !== "core") ||
          (role.provenance === "verified" && role.authority !== "core") ||
          (role.provenance !== "verified" && role.authority !== null)) {
        throw new DiagnosticPreviewError("Invalid candidate role.");
      }
      return {...role};
    });
    return {id: candidate.id, source: candidate.source, occurrence: candidate.occurrence, roles,
      dependency_target: candidate.dependency_target};
  });
  if (candidates.some(candidate => candidate.dependency_target === candidate.id ||
      (candidate.dependency_target !== null && !ids.has(candidate.dependency_target)))) {
    throw new DiagnosticPreviewError("Invalid candidate dependency.");
  }
  return {version: 1, user_message: value.user_message, candidates};
}

/** Render an explicitly supplied design fixture, never a production request detail. */
export function renderFactCandidatePreview(doc, preview) {
  const section = element(doc, "section", "flow-candidate-preview");
  section.append(element(doc, "h3", "flow-candidate-heading", "Vista previa de diseño · candidatos v1"));
  section.append(element(doc, "p", "flow-diagnostic-warning", "No es una ejecución de Router ni un registro de notas; no autoriza ni demuestra una escritura."));
  let safe;
  try {
    safe = validateFactCandidatePreview(preview);
  } catch {
    section.append(element(doc, "p", "flow-diagnostic-warning", "La vista previa de candidatos no es válida y no se muestra."));
    return section;
  }
  section.append(textInput(doc, safe.user_message));
  for (const candidate of safe.candidates) {
    const card = element(doc, "article", "flow-card flow-candidate-card");
    card.append(headingWithIcon(doc, candidate.id, "fragment"));
    card.append(detailLine(doc, `Fuente: ${candidate.source}`, "flow-candidate-source"));
    if (candidate.dependency_target) card.append(detailLine(doc, `Dependencia propuesta: ${candidate.dependency_target}`, "flow-dependency"));
    for (const role of candidate.roles) {
      const label = role.provenance === "verified"
        ? `${role.role}: ${role.source} · verificado por Core indicado en la prueba`
        : `${role.role}: ${role.source} · ${role.provenance}`;
      card.append(detailLine(doc, label, `flow-candidate-role flow-candidate-${role.provenance}`));
    }
    section.append(card);
  }
  return section;
}
