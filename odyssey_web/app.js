import {
  ProductRequestError,
  createSubmission,
  renderProductResultWithContinuity,
  requestProductResult,
  requestConversation,
} from "./client.js";

const form = document.querySelector("#odyssey-form");
const input = document.querySelector("#request-input");
const sendButton = document.querySelector("#send-button");
const conversation = document.querySelector("#interaction");
const endpoint = document.querySelector('meta[name="odyssey-api-endpoint"]')?.content ?? "/api/request";
const requestDetailSheet = document.querySelector("#request-detail-sheet");
const requestDetailTitle = document.querySelector("#request-detail-title");
const requestDetailContent = document.querySelector("#request-detail-content");
const conversationEndpoint = document.querySelector('meta[name="odyssey-conversation-endpoint"]')?.content ?? "/api/conversation";
const MAIN_CONVERSATION_ID = "main";
let conversationId = MAIN_CONVERSATION_ID;
let retrySubmission = null;

function showDeploymentMarker() {
  const deployment = globalThis.ODYSSEY_DEPLOYMENT;
  if (!deployment || deployment.environment !== "DEV") return;
  const marker = document.createElement("p");
  marker.className = "deployment-marker";
  marker.textContent = deployment.commit ? "DEV · " + deployment.commit.slice(0, 12) : "DEV";
  document.querySelector(".brand")?.append(marker);
}

showDeploymentMarker();

function conversationPayload() {
  return conversationId ? {conversation_id: conversationId} : {};
}

async function loadMainConversation() {
  const data = await requestConversation({endpoint: conversationEndpoint, operation: "main"});
  conversationId = data.conversation_id;
  conversation.replaceChildren();
  for (const turn of data.turns ?? []) appendMessage(turn.role === "assistant" ? "odyssey" : "user", turn.text, turn.status);
}

void (async () => {
  try {
    await loadMainConversation();
  } catch {
    // The existing chat remains usable if the optional history projection is unavailable.
  }
})();

function setBusy(isBusy) {
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  sendButton.textContent = isBusy ? "Enviando…" : "Enviar";
}

function appendMessage(role, message, status = "") {
  const article = document.createElement("article");
  article.className = "message message-" + role;
  const label = document.createElement("p");
  label.className = "eyebrow";
  label.textContent = role === "user" ? "Tú" : "Odyssey";
  const body = document.createElement("p");
  body.className = "message-text";
  body.textContent = message;
  const header = document.createElement("div");
  header.className = "message-header";
  header.append(label);
  article.append(header, body);
  if (status === "partial") {
    const notice = document.createElement("p");
    notice.className = "partial-notice";
    notice.textContent = "La respuesta puede ser incompleta.";
    article.append(notice);
  }
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
  return article;
}

function appendDetailButton(article, detail) {
  if (!detail || !requestDetailSheet) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-button";
  button.setAttribute("aria-label", "Ver detalles de esta solicitud");
  button.textContent = "ⓘ";
  button.addEventListener("click", () => openRequestDetail(detail));
  article.querySelector(".message-header")?.append(button);
}

function appendDetailLine(parent, label, value) {
  if (value === null || value === undefined || value === "") return;
  const line = document.createElement("p");
  line.className = "detail-line";
  const name = document.createElement("span");
  name.className = "detail-label";
  name.textContent = label;
  const content = document.createElement("span");
  content.textContent = String(value);
  line.append(name, content);
  parent.append(line);
}

function openRequestDetail(detail) {
  requestDetailContent.replaceChildren();
  requestDetailTitle.textContent = "Detalles de la solicitud";
  appendDetailLine(requestDetailContent, "Solicitud", detail.request_id);
  appendDetailLine(requestDetailContent, "Latencia total", formatDuration(detail.operational.total_duration_ms));
  appendDetailLine(requestDetailContent, "Coste estimado", formatEstimatedCost(detail.estimated_cost));
  appendDetailLine(requestDetailContent, "Base de precios", detail.estimated_cost?.pricing_basis);
  const stages = document.createElement("section");
  stages.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = "Etapas";
  stages.append(heading);
  for (const stage of detail.operational.stages) {
    const row = document.createElement("article");
    row.className = "detail-stage";
    appendDetailLine(row, "Etapa", stage.name);
    appendDetailLine(row, "Resultado", stage.outcome);
    appendDetailLine(row, "Duración", formatDuration(stage.duration_ms));
    appendDetailLine(row, "Modelo", stage.model);
    appendDetailLine(row, "Razonamiento", stage.reasoning_effort);
    appendDetailLine(row, "Error", stage.error_category);
    appendDetailLine(row, "Llamadas de proveedor", stage.provider_calls.length || null);
    if (stage.usage) appendDetailLine(row, "Tokens", formatUsage(stage.usage));
    for (const call of stage.provider_calls) {
      appendDetailLine(row, call.name || "Proveedor", `${call.model || "No disponible"} · ${formatDuration(call.duration_ms)}`);
      appendDetailLine(row, "Resultado de proveedor", call.outcome);
      if (call.usage) appendDetailLine(row, "Tokens de proveedor", formatUsage(call.usage));
    }
    stages.append(row);
  }
  requestDetailContent.append(stages);
  if (detail.changes) {
    const changes = document.createElement("section");
    changes.className = "detail-section";
    const heading = document.createElement("h3");
    heading.textContent = "Cambios";
    changes.append(heading);
    appendDetailLine(changes, "Notas afectadas", detail.changes.affected_stable_note_ids.length || null);
    for (const unit of detail.changes.units) {
      appendDetailLine(changes, unit.operation || "Unidad", unit.status);
    }
    requestDetailContent.append(changes);
  }
  requestDetailSheet.showModal();
}

function formatDuration(value) {
  return typeof value === "number" ? `${Math.round(value)} ms` : "No disponible";
}

function formatEstimatedCost(value) {
  return value?.status === "estimated" && typeof value.amount_usd === "number"
    ? `~$${value.amount_usd.toFixed(6)}`
    : "No disponible";
}

function formatUsage(usage) {
  return Object.entries(usage).map(([key, value]) => `${key}: ${value}`).join(" · ");
}

function appendLoading() {
  const loading = appendMessage("odyssey", "Procesando…");
  loading.classList.add("message-loading");
  return loading;
}

function appendRetryControl(submission) {
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "retry-button";
  retry.textContent = "Reintentar";
  retry.addEventListener("click", () => {
    if (retrySubmission !== submission) return;
    retrySubmission = null;
    retry.remove();
    void sendSubmission(submission, true);
  });
  conversation.append(retry);
  conversation.scrollTop = conversation.scrollHeight;
}

function appendContinuityWarning() {
  const warning = document.createElement("p");
  warning.className = "continuity-warning";
  warning.textContent = "La respuesta se ha obtenido, pero no se ha podido guardar la continuidad de esta conversación.";
  conversation.append(warning);
  conversation.scrollTop = conversation.scrollHeight;
}

function renderProductResult(result) {
  const message = appendMessage("odyssey", result.message, result.status);
  message.querySelector(".eyebrow").textContent = resultLabel(result);
  appendDetailButton(message, result.request_detail);
}

function resultLabel(result) {
  return {
    acknowledgement: "Hecho",
    clarification: "Aclara tu solicitud",
    empty: "Sin resultados",
    error: "No completado",
  }[result.kind] ?? "Odyssey";
}

async function sendSubmission(submission, isRetry = false) {
  if (!isRetry) appendMessage("user", submission.request);
  const loading = appendLoading();
  setBusy(true);
  try {
    const result = await requestProductResult({endpoint, submission, conversationId});
    retrySubmission = null;
    loading.remove();
    await renderProductResultWithContinuity({
      result,
      renderResult: renderProductResult,
      persistAssistantTurn: async () => {
        if (!conversationId) return;
        await requestConversation({
          endpoint: conversationEndpoint,
          operation: "turn",
          payload: {
            conversation_id: conversationId,
            request_id: submission.requestId,
            role: "assistant",
            text: result.message,
            status: result.status,
          },
        });
      },
      warnContinuity: appendContinuityWarning,
    });
  } catch (error) {
    retrySubmission = error instanceof ProductRequestError && error.retryable ? submission : null;
    loading.remove();
    const message = appendMessage(
      "odyssey",
      retrySubmission
        ? "No se ha podido confirmar la solicitud. Puedes reintentar la misma entrega."
        : "Odyssey no ha podido procesar esta solicitud.",
    );
    message.classList.add("message-error");
    if (retrySubmission) appendRetryControl(retrySubmission);
  } finally {
    setBusy(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  let submission;
  try {
    submission = createSubmission(input.value, globalThis.crypto, conversationId);
  } catch {
    input.focus();
    return;
  }
  input.value = "";
  retrySubmission = null;
  void sendSubmission(submission);
});

input.addEventListener("keydown", (event) => {
  if (globalThis.matchMedia?.("(pointer: coarse)").matches) return;
  if (event.key !== "Enter" || event.isComposing) return;
  if (event.shiftKey) return;
  event.preventDefault();
  form.requestSubmit();
});

document.querySelector("#request-detail-close")?.addEventListener("click", () => {
  requestDetailSheet?.close();
});
