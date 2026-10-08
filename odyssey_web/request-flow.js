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

function stageCard(doc, stage, route = null) {
  const card = element(doc, "article", `flow-card ${stage.outcome === "failed" ? "flow-card-failed" : ""}`);
  const heading = element(doc, "h4", "flow-node-heading", stageTitle(stage.name));
  card.append(heading);
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

function plainCard(doc, heading, body, kind = "") {
  const node = element(doc, "article", `flow-card flow-${kind}`);
  node.append(element(doc, "h4", "flow-node-heading", heading));
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
    root.append(stageCard(doc, stages[routerIndex]));
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
      for (const stage of routeStages) {
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
