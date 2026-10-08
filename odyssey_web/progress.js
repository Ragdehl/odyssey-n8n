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

function chip(doc, text, type = "") {
  return element(doc, "span", `flow-chip ${type}`, text);
}

function stageTitle(name) {
  if (name === "application.router") return "Router";
  if (name === "planner") return "Planner";
  if (name === "temporal.interpretation") return "Temporal";
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
  if (Number.isInteger(usage.input_tokens)) results.push(`↓ ${usage.input_tokens.toLocaleString("es-ES")}`);
  if (Number.isInteger(usage.cached_input_tokens)) results.push(`↳ ${usage.cached_input_tokens.toLocaleString("es-ES")} caché`);
  if (Number.isInteger(usage.output_tokens)) results.push(`↑ ${usage.output_tokens.toLocaleString("es-ES")}`);
  if (Number.isInteger(usage.reasoning_tokens)) results.push(`◈ ${usage.reasoning_tokens.toLocaleString("es-ES")}`);
  return results;
}

function cost(value) {
  return value?.status === "estimated" && typeof value.amount_usd === "number"
    ? `~$${value.amount_usd.toFixed(6)}` : "";
}

const FLOW_ICONS = {
  source: "💬", fragment: "💬", router: "🔀", tasks: "📋",
  temporal: "🗓️", planner: "🧠", core: "🗃️", git: "📁",
  index: "🔎", pending: "📌", result: "✅", entities: "🔗",
};

function headingWithIcon(doc, label, icon) {
  const heading = element(doc, "h4", "flow-node-heading");
  const emblem = element(doc, "span", "flow-icon", FLOW_ICONS[icon] || "◈");
  emblem.setAttribute("aria-hidden", "true");
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

function stageCard(doc, stage, route = null) {
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
  if (route && ["planner", "tasks.interpretation", "temporal.interpretation"].includes(stage.name)) {
    card.append(textInput(doc, route.text));
  }
  if (stage.name === "planner" && route?.plan?.length) {
    const decisions = element(doc, "div", "flow-semantics");
    for (const item of route.plan) {
      decisions.append(detailLine(doc, `${item.operation} · ${item.type || "nota"} → ${item.target}`));
      if (item.fact) decisions.append(detailLine(doc,
        item.fact.replace(/\{\{ref:\d+\}\}/gu, "↗ referencia"), "flow-semantic-fact"));
    }
    card.append(decisions);
  }
  if (stage.name.startsWith("action.") && route) {
    const steps = element(doc, "div", "flow-semantics");
    for (const item of route.writes || []) {
      steps.append(detailLine(doc, `✍️ ${item.operation} · ${item.target} (${item.status})`));
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
    calls.length ? `${calls.length} llamada${calls.length === 1 ? "" : "s"}` : "", cost(stage.estimated_cost)];
  for (const value of info.filter(Boolean)) stats.append(chip(doc, String(value)));
  const usage = stage.usage || (calls.length === 1 ? calls[0].usage : null);
  for (const value of tokens(usage)) stats.append(chip(doc, value, "flow-chip-tokens"));
  if (stats.children.length) card.append(stats);
  // Provider fallbacks must remain inspectable, not collapsed into a fictional model.
  if (calls.length > 1) {
    const attempts = element(doc, "details", "flow-provider-details");
    attempts.append(element(doc, "summary", "", `${calls.length} llamadas de proveedor`));
    for (const call of calls) {
      const label = [call.model || call.name, duration(call.duration_ms), call.outcome].filter(Boolean).join(" · ");
      attempts.append(element(doc, "p", "flow-provider-line", label));
    }
    card.append(attempts);
  }
  return card;
}

function entitiesCard(doc, entities) {
  const node = element(doc, "article", "flow-card flow-entities");
  node.append(headingWithIcon(doc, "Entidades · Core", "entities"));
  const output = element(doc, "div", "flow-semantics");
  for (const item of entities) {
    const target = item.status === "resolved" ? item.name : "Resolución no disponible";
    output.append(detailLine(doc, `${item.mention} → ${target}`,
      item.status === "resolved" ? "flow-entity-resolved" : "flow-entity-unresolved"));
  }
  node.append(output);
  return node;
}

function plainCard(doc, heading, body, kind = "") {
  const node = element(doc, "article", `flow-card flow-${kind}`);
  node.append(headingWithIcon(doc, heading, kind === "source" ? "source" : kind === "fragment" ? "fragment" : kind === "success" ? "result" : "result"));
  if (body) node.append(element(doc, "p", "flow-node-text", body));
  return node;
}

/** Render a responsive directed graph driven by validated per-route stage counts. */
export function renderExecutionFlow(doc, detail) {
  const root = element(doc, "section", "flow-graph");
  root.setAttribute("aria-label", "Diagrama de ejecución de la solicitud");
  const stages = detail.operational.stages;
  const flow = detail.flow;
  if (flow?.input) {
    root.append(plainCard(doc, "Mensaje del usuario", flow.input, "source"));
    root.append(arrow(doc));
  } else {
    root.append(element(doc, "p", "flow-legacy", "Esta solicitud es anterior a la traza de rutas; se muestran únicamente las etapas registradas."));
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
        ? `🔀 Dividido en ${flow.routes.length} fragmentos`
        : "➡️ Sin división · 1 camino", "flow-split-result"));
    }
    root.append(router);
    root.append(arrow(doc, flow?.routes?.length > 1 ? "flow-fork" : ""));
  }
  let consumed = routerIndex + 1;
  if (flow?.routes?.length) {
    const lanes = element(doc, "div", "flow-lanes");
    if (flow.routes.length > 1) lanes.classList.add("flow-multiple");
    if (flow.parallel_preparation) {
      root.append(element(doc, "p", "flow-lane-caption", "Preparación simultánea · aplicación en orden"));
    }
    for (const [index, route] of flow.routes.entries()) {
      const lane = element(doc, "section", "flow-lane");
      lane.setAttribute("aria-label", `Camino ${index + 1}: ${route.capability}`);
      const fragment = plainCard(doc, `${index + 1} · ${route.capability}`, route.text, "fragment");
      lane.append(fragment);
      const routeStages = stages.slice(consumed, consumed + route.stage_count);
      consumed += route.stage_count;
      let entitiesDisplayed = false;
      for (const stage of routeStages) {
        if (stage.name === "pending" && stage.outcome === "skipped") continue;
        if (!entitiesDisplayed && stage.name.startsWith("action.") && route.entities?.length) {
          lane.append(arrow(doc));
          lane.append(entitiesCard(doc, route.entities));
          entitiesDisplayed = true;
        }
        lane.append(arrow(doc));
        lane.append(stageCard(doc, stage, route));
      }
      if (routeStages.length === 0) {
        lane.append(arrow(doc));
        lane.append(plainCard(doc, "Sin etapas registradas", route.status, "empty"));
      }
      lanes.append(lane);
    }
    root.append(lanes);
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
  root.append(arrow(doc, flow?.routes?.length > 1 ? "flow-join" : "flow-single"));
  const outcomes = flow?.routes?.map(route => route.status) || [];
  const result = outcomes.length && outcomes.every(s => s === "completed") ? "Completado"
    : outcomes.some(s => s === "completed") ? "Resultado parcial"
    : outcomes.includes("needs_attention") ? "Necesita aclaración"
    : outcomes.includes("failed") ? "No completado" : "Resultado de Odyssey";
  const end = plainCard(doc, result, "", result === "Completado" ? "success" : "outcome");
  const stats = element(doc, "div", "flow-stats");
  for (const text of [duration(detail.operational.total_duration_ms), cost(detail.estimated_cost),
    detail.changes?.affected_stable_note_ids?.length ? `${detail.changes.affected_stable_note_ids.length} notas` : ""].filter(Boolean)) {
    stats.append(chip(doc, text));
  }
  end.append(stats);
  root.append(end);
  return root;
}
