import {
  ProductRequestError,
  createSubmission,
  requestProductResult,
} from "./client.js";

const form = document.querySelector("#odyssey-form");
const input = document.querySelector("#request-input");
const sendButton = document.querySelector("#send-button");
const conversation = document.querySelector("#interaction");
const endpoint = document.querySelector('meta[name="odyssey-api-endpoint"]')?.content ?? "/api/request";
let retrySubmission = null;

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
  article.append(label, body);
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

function appendLoading() {
  const loading = appendMessage("odyssey", "Procesando…");
  loading.classList.add("message-loading");
  return loading;
}

function resultLabel(result) {
  return {
    acknowledgement: "Hecho",
    empty: "Sin resultados",
    error: "No completado",
  }[result.kind] ?? "Odyssey";
}

async function sendSubmission(submission) {
  appendMessage("user", submission.request);
  const loading = appendLoading();
  setBusy(true);
  try {
    const result = await requestProductResult({endpoint, submission});
    retrySubmission = null;
    loading.remove();
    const message = appendMessage("odyssey", result.message, result.status);
    message.querySelector(".eyebrow").textContent = resultLabel(result);
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
  } finally {
    setBusy(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  let submission;
  try {
    submission = createSubmission(input.value);
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
