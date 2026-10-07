import {
  ProductRequestError,
  createSubmission,
  findRecoverableSubmission,
  renderProductResultWithContinuity,
  requestProductResult,
  requestConversation,
} from "./client.js";
import {actionButton, mountNotes, setActionIcon} from "./notes.js";
import {mountCalendar} from "./calendar.js";
import {createProcessingIndicator, startProgressPolling} from "./progress.js";

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
const chatSurface = document.querySelector("#chat-surface");
const notesSurface = document.querySelector("#notes-surface");
const calendarSurface = document.querySelector("#calendar-surface");
const chatHomeTab = document.querySelector("#chat-home-tab");
const chatTab = document.querySelector("#chat-tab");
const notesTab = document.querySelector("#notes-tab");
const notesHomeTab = document.querySelector("#notes-home-tab");
const calendarTab = document.querySelector("#calendar-tab");
const notesCalendarTab = document.querySelector("#notes-calendar-tab");
const calendarChatTab = document.querySelector("#calendar-chat-tab");
const calendarNotesTab = document.querySelector("#calendar-notes-tab");
const calendarHomeTab = document.querySelector("#calendar-home-tab");
const clarificationStatus = document.querySelector("#clarification-status");
for (const [control, icon, label] of [
  [chatHomeTab, "chat", "Chat"],
  [chatTab, "chat", "Chat"],
  [calendarChatTab, "chat", "Chat"],
  [notesTab, "notes", "Notas"],
  [notesHomeTab, "notes", "Notas"],
  [calendarNotesTab, "notes", "Notas"],
  [calendarTab, "calendar", "Calendario"],
  [notesCalendarTab, "calendar", "Calendario"],
  [calendarHomeTab, "calendar", "Calendario"],
]) {
  if (control) setActionIcon(control, icon, label);
}
if (sendButton) setActionIcon(sendButton, "send", "Enviar");
let conversationId = MAIN_CONVERSATION_ID;
let retrySubmission = null;
let olderCursor = null;
let hasOlder = false;
let loadingOlder = false;
let recoveryControl = null;

function showDeploymentMarker() {
  const deployment = globalThis.ODYSSEY_DEPLOYMENT;
  if (!deployment || deployment.environment !== "DEV") return;
  const marker = document.createElement("span");
  marker.className = "deployment-marker";
  marker.textContent = deployment.commit ? "DEV · " + deployment.commit.slice(0, 12) : "DEV";
  document.querySelector("#chat-title")?.append(document.createTextNode(" "), marker);
}

showDeploymentMarker();

// Application controllers remain mounted for the page lifetime so each surface keeps its local state.
const notesController = notesSurface
  ? mountNotes(notesSurface, {endpoint: document.querySelector('meta[name="odyssey-notes-endpoint"]')?.content ?? "/api/notes"})
  : null;
const calendarController = calendarSurface
  ? mountCalendar(calendarSurface, {
    endpoint: document.querySelector('meta[name="odyssey-calendar-endpoint"]')?.content ?? "/api/calendar",
    notesEndpoint: document.querySelector('meta[name="odyssey-notes-endpoint"]')?.content ?? "/api/notes",
  })
  : null;
function selectSurface(surface) {
  const active = ["chat", "notes", "calendar"].includes(surface) ? surface : "chat";
  if (chatSurface) chatSurface.hidden = active !== "chat";
  if (notesSurface) notesSurface.hidden = active !== "notes";
  if (calendarSurface) calendarSurface.hidden = active !== "calendar";
  document.documentElement.dataset.activeView = active;
  for (const control of [chatHomeTab, chatTab, calendarChatTab]) {
    control?.setAttribute("aria-current", active === "chat" ? "page" : "false");
  }
  for (const control of [notesTab, notesHomeTab, calendarNotesTab]) {
    control?.setAttribute("aria-current", active === "notes" ? "page" : "false");
  }
  for (const control of [calendarTab, notesCalendarTab, calendarHomeTab]) {
    control?.setAttribute("aria-current", active === "calendar" ? "page" : "false");
  }
}
for (const control of [chatHomeTab, chatTab, calendarChatTab]) {
  control?.addEventListener("click", () => selectSurface("chat"));
}
for (const control of [notesTab, notesHomeTab, calendarNotesTab]) {
  control?.addEventListener("click", () => {
    notesController?.showList?.();
    selectSurface("notes");
  });
}
for (const control of [calendarTab, notesCalendarTab, calendarHomeTab]) {
  control?.addEventListener("click", () => {
    calendarController?.showMonth?.();
    selectSurface("calendar");
  });
}
document.addEventListener("odyssey:open-note", () => selectSurface("notes"));
document.addEventListener("odyssey:open-calendar-day", () => selectSurface("calendar"));
selectSurface("chat");

function conversationPayload() {
  return conversationId ? {conversation_id: conversationId} : {};
}

async function loadMainConversation() {
  const data = await requestConversation({endpoint: conversationEndpoint, operation: "main", payload: {limit: 40}});
  conversationId = data.conversation_id;
  olderCursor = data.before ?? null;
  hasOlder = data.has_older === true;
  conversation.replaceChildren();
  recoveryControl = null;
  const userMessages = new Map();
  let visibleDay = null;
  for (const turn of data.turns ?? []) {
    const createdAt = validTurnTime(turn.created_at);
    const day = localDayKey(createdAt);
    if (day !== visibleDay) {
      appendDateSeparator(createdAt);
      visibleDay = day;
    }
    const message = appendMessage(
      turn.role === "assistant" ? "odyssey" : "user",
      turn.text,
      turn.status,
      {createdAt, groupDate: false},
    );
    if (turn.role === "user" && typeof turn.request_id === "string") {
      userMessages.set(turn.request_id, message);
    }
    if (turn.role === "assistant") {
      appendDetailButton(message, turn.request_detail);
      appendNoteSetAffordance(message, turn.note_result_snapshot);
    }
  }
  const recoverable = findRecoverableSubmission(data.turns, conversationId);
  if (recoverable) {
    retrySubmission = recoverable;
    appendRecoveryControl(recoverable, userMessages.get(recoverable.requestId));
  }
  conversation.scrollTop = conversation.scrollHeight;
}

void (async () => {
  try {
    await loadMainConversation();
  } catch {
    if (!conversation.children.length) {
      const message = appendMessage(
        "odyssey",
        "No se ha podido cargar la conversación. Puedes seguir usando Odyssey o volver a intentarlo más tarde.",
      );
      message.classList.add("message-error");
    }
  }
})();

function setBusy(isBusy) {
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  setActionIcon(sendButton, "send", isBusy ? "Enviando" : "Enviar");
}

function appendMessage(
  role,
  message,
  status = "",
  {
    prepend = false,
    scroll = true,
    createdAt = new Date().toISOString(),
    insert = true,
    groupDate = true,
  } = {},
) {
  const timestamp = validTurnTime(createdAt);
  const day = localDayKey(timestamp);
  if (insert && groupDate && !prepend && day !== lastMessageDay()) appendDateSeparator(timestamp);
  const article = document.createElement("article");
  article.className = "message message-" + role;
  article.dataset.day = day;
  article.dataset.createdAt = timestamp;
  const body = document.createElement("p");
  body.className = "message-text";
  body.textContent = message;
  const header = document.createElement("div");
  header.className = "message-header";
  const actions = document.createElement("div");
  actions.className = "message-actions";
  header.append(actions);
  const footer = document.createElement("footer");
  footer.className = "message-footer";
  const time = document.createElement("time");
  time.className = "message-time";
  time.dateTime = timestamp;
  time.textContent = messageTime(timestamp);
  footer.append(time);
  article.append(header, body, footer);
  if (status === "partial") {
    const notice = document.createElement("p");
    notice.className = "partial-notice";
    notice.textContent = "La respuesta puede ser incompleta.";
    article.append(notice);
  }
  if (insert) {
    if (prepend) conversation.prepend(article);
    else conversation.append(article);
  }
  if (insert && scroll) conversation.scrollTop = conversation.scrollHeight;
  return article;
}

function validTurnTime(value) {
  const parsed = typeof value === "string" ? new Date(value) : new Date();
  return Number.isNaN(parsed.valueOf()) ? new Date().toISOString() : parsed.toISOString();
}

function localDayKey(value) {
  const date = new Date(value);
  const part = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())}`;
}

function lastMessageDay() {
  const children = Array.from(conversation.children);
  for (let index = children.length - 1; index >= 0; index -= 1) {
    if (children[index].classList?.contains?.("message") || children[index].className?.split(" ").includes("message")) {
      return children[index].dataset.day ?? null;
    }
  }
  return null;
}

function appendDateSeparator(value, {prepend = false, insert = true} = {}) {
  const day = localDayKey(value);
  const separator = document.createElement("p");
  separator.className = "conversation-date";
  separator.dataset.day = day;
  separator.textContent = conversationDateLabel(value);
  if (insert) {
    if (prepend) conversation.prepend(separator);
    else conversation.append(separator);
  }
  return separator;
}

function conversationDateLabel(value) {
  const date = new Date(value);
  const today = new Date();
  const dayNumber = (item) => Date.UTC(item.getFullYear(), item.getMonth(), item.getDate());
  const difference = Math.round((dayNumber(today) - dayNumber(date)) / 86_400_000);
  if (difference === 0) return "Hoy";
  if (difference === 1) return "Ayer";
  if (difference > 1 && difference < 7) {
    const weekday = new Intl.DateTimeFormat("es-ES", {weekday: "long"}).format(date);
    return weekday.charAt(0).toUpperCase() + weekday.slice(1);
  }
  return new Intl.DateTimeFormat("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

function messageTime(value) {
  const date = new Date(value);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

async function loadOlderConversation() {
  if (!hasOlder || !olderCursor || loadingOlder) return;
  loadingOlder = true;
  const cursor = olderCursor;
  const previousHeight = conversation.scrollHeight;
  const previousTop = conversation.scrollTop;
  try {
    const data = await requestConversation({endpoint: conversationEndpoint, operation: "main", payload: {limit: 40, before: cursor}});
    if (cursor !== olderCursor) return;
    const olderNodes = [];
    let olderDay = null;
    for (const turn of data.turns ?? []) {
      const createdAt = validTurnTime(turn.created_at);
      const day = localDayKey(createdAt);
      if (day !== olderDay) {
        olderNodes.push(appendDateSeparator(createdAt, {insert: false}));
        olderDay = day;
      }
      const message = appendMessage(
        turn.role === "assistant" ? "odyssey" : "user",
        turn.text,
        turn.status,
        {createdAt, insert: false, scroll: false, groupDate: false},
      );
      if (turn.role === "assistant") {
        appendDetailButton(message, turn.request_detail);
        appendNoteSetAffordance(message, turn.note_result_snapshot);
      }
      olderNodes.push(message);
    }
    const firstExistingMessage = Array.from(conversation.children).find((child) =>
      child.className?.split(" ").includes("message"),
    );
    if (olderDay && firstExistingMessage?.dataset.day === olderDay) {
      const duplicate = Array.from(conversation.children).find((child) =>
        child.className === "conversation-date" && child.dataset.day === olderDay,
      );
      duplicate?.remove();
    }
    if (olderNodes.length) conversation.prepend(...olderNodes);
    olderCursor = data.before ?? null;
    hasOlder = data.has_older === true;
    conversation.scrollTop = previousTop + conversation.scrollHeight - previousHeight;
  } catch {
    // The current bounded page remains usable when older presentation history is unavailable.
  } finally {
    loadingOlder = false;
  }
}

conversation.addEventListener("scroll", () => {
  if (conversation.scrollTop <= 80) void loadOlderConversation();
});

function appendDetailButton(article, detail) {
  if (!detail || !requestDetailSheet || article.querySelector(".detail-button")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-button";
  button.setAttribute("aria-label", "Ver detalles de esta solicitud");
  button.textContent = "ⓘ";
  button.addEventListener("click", () => openRequestDetail(detail));
  article.querySelector(".message-actions")?.append(button);
}

function appendNoteSetAffordance(article, snapshot) {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
      !Array.isArray(snapshot.note_ids) || !Number.isInteger(snapshot.total) ||
      typeof snapshot.truncated !== "boolean" ||
      (snapshot.version !== 1 && snapshot.version !== 2) ||
      (snapshot.version === 1 && typeof snapshot.query !== "string") ||
      (snapshot.version === 2 && (snapshot.kind !== "affected_notes" || snapshot.total < 1))) return;
  const visible = snapshot.truncated ? `${snapshot.note_ids.length} de ${snapshot.total}` : snapshot.total;
  const label = snapshot.total === 1 ? "Ver nota" : `Ver ${visible} notas`;
  const button = actionButton("openNote", label, () => {
    selectSurface("notes");
    document.dispatchEvent(new CustomEvent("odyssey:open-note-snapshot", {detail: snapshot}));
  }, "note-set-button action-open-note");
  if (snapshot.total > 1) {
    const count = document.createElement("span");
    count.className = "note-set-count";
    count.textContent = String(visible);
    button.append(count);
  }
  article.querySelector(".message-actions")?.append(button);
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
  const loading = appendMessage("odyssey", "");
  loading.classList.add("message-loading");
  const indicator = createProcessingIndicator(document);
  loading.querySelector(".message-text")?.replaceChildren(indicator.element);
  loading.processingIndicator = indicator;
  return loading;
}

function appendRetryControl(submission, label = "Reintentar") {
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "retry-button";
  retry.textContent = label;
  retry.addEventListener("click", () => {
    if (retrySubmission !== submission) return;
    retrySubmission = null;
    retry.remove();
    void sendSubmission(submission, true);
  });
  conversation.append(retry);
  conversation.scrollTop = conversation.scrollHeight;
}

function appendRecoveryControl(submission, userMessage) {
  const control = document.createElement("div");
  control.className = "recovery-control";
  control.dataset.requestId = submission.requestId;
  const text = document.createElement("p");
  text.textContent = "Esta solicitud no tiene una respuesta guardada.";
  const action = document.createElement("button");
  action.type = "button";
  action.className = "recovery-action";
  action.textContent = "Recuperar resultado";
  action.addEventListener("click", () => {
    if (retrySubmission !== submission || recoveryControl !== control) return;
    action.disabled = true;
    action.textContent = "Recuperando…";
    control.dataset.state = "recovering";
    void sendSubmission(submission, true, control);
  });
  control.append(text, action);
  (userMessage ?? conversation).append(control);
  recoveryControl = control;
  conversation.scrollTop = conversation.scrollHeight;
}

function restoreRecoveryControl(control) {
  const action = control.querySelector(".recovery-action");
  if (!action) return;
  action.disabled = false;
  action.textContent = "Recuperar resultado";
  control.dataset.state = "retryable";
}

function failRecoveryControl(control) {
  const text = control.querySelector("p");
  if (text) text.textContent = "No se ha podido recuperar el resultado.";
  control.querySelector(".recovery-action")?.remove();
  control.dataset.state = "failed";
  recoveryControl = null;
}

function removeRecoveryControl(control) {
  if (recoveryControl === control) recoveryControl = null;
  control?.remove();
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
  if (result.kind === "acknowledgement" && result.note_result_snapshot?.kind === "affected_notes") {
    message.querySelector(".message-text").textContent = "Guardado";
    message.classList.add("message-acknowledgement");
  }
  appendDetailButton(message, result.request_detail);
  appendNoteSetAffordance(message, result.note_result_snapshot);
  appendClarificationCard(message, result.clarification);
  if (clarificationStatus) clarificationStatus.hidden = result.kind !== "clarification";
}

function appendClarificationCard(article, clarification) {
  if (!clarification?.options?.length) return;
  article.classList.add("message-clarification");
  if (clarification.explanation) {
    article.querySelector(".message-text").textContent = clarification.explanation;
  }
  const list = document.createElement("div");
  list.className = "clarification-options";
  clarification.options.forEach((option) => {
    const row = document.createElement("article");
    row.className = "clarification-option";
    const heading = document.createElement("h3");
    heading.textContent = option.label;
    const controls = document.createElement("div");
    controls.className = "clarification-controls";
    const choose = document.createElement("button");
    choose.type = "button";
    choose.textContent = "Elegir";
    choose.addEventListener("click", () => submitClarificationReply(`He elegido a ${option.label}.`));
    const inspect = actionButton("openNote", "Ver nota", () => {
      selectSurface("notes");
      document.dispatchEvent(new CustomEvent("odyssey:open-note", {detail: {note_id: option.id}}));
    }, "clarification-inspect action-open-note");
    controls.append(choose, inspect);
    row.append(heading);
    if (option.note_type && option.evidence) {
      const type = document.createElement("p");
      type.className = "clarification-type";
      type.textContent = option.note_type;
      const evidence = document.createElement("p");
      evidence.className = "clarification-evidence";
      evidence.textContent = option.evidence;
      row.append(type, evidence);
    }
    row.append(controls);
    list.append(row);
  });
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "clarification-cancel";
  cancel.textContent = "Cancelar";
  cancel.addEventListener("click", () => submitClarificationReply("cancel"));
  article.append(list, cancel);
}

function submitClarificationReply(reply) {
  try {
    void sendSubmission(createSubmission(reply, globalThis.crypto, conversationId));
  } catch {
    input.focus();
  }
}

async function sendSubmission(submission, isRetry = false, activeRecoveryControl = null) {
  if (!isRetry) appendMessage("user", submission.request);
  const loading = appendLoading();
  const stopProgress = startProgressPolling({
    requestId: submission.requestId,
    requestProgress: (requestId) => requestConversation({
      endpoint: conversationEndpoint,
      operation: "progress",
      payload: {request_id: requestId},
    }),
    onProgress: (snapshot) => loading.processingIndicator?.update(snapshot),
  });
  setBusy(true);
  try {
    const result = await requestProductResult({endpoint, submission, conversationId});
    retrySubmission = null;
    stopProgress();
    loading.processingIndicator?.complete();
    loading.remove();
    removeRecoveryControl(activeRecoveryControl);
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
            request_detail: result.request_detail,
            note_result_snapshot: result.note_result_snapshot,
          },
        });
      },
      warnContinuity: appendContinuityWarning,
    });
  } catch (error) {
    retrySubmission = error instanceof ProductRequestError && error.retryable ? submission : null;
    stopProgress();
    loading.remove();
    if (activeRecoveryControl) {
      if (retrySubmission) {
        restoreRecoveryControl(activeRecoveryControl);
      } else {
        failRecoveryControl(activeRecoveryControl);
      }
      return;
    }
    const message = appendMessage(
      "odyssey",
      retrySubmission
        ? "No se ha podido confirmar la solicitud. Puedes reintentar la misma entrega."
        : "Odyssey no ha podido procesar esta solicitud.",
    );
    message.classList.add("message-error");
    if (retrySubmission) appendRetryControl(retrySubmission);
  } finally {
    stopProgress();
    loading.processingIndicator?.destroy();
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
