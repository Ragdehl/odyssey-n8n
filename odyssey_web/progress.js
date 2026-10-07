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
