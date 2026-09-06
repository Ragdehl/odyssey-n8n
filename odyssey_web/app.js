import {
  ProductRequestError,
  createSubmission,
  requestProductResult,
} from "./client.js";

const form = document.querySelector("#odyssey-form");
const input = document.querySelector("#request-input");
const sendButton = document.querySelector("#send-button");
const interaction = document.querySelector("#interaction");
const requestCard = document.querySelector("#request-card");
const requestText = document.querySelector("#request-text");
const resultCard = document.querySelector("#result-card");
const resultLabel = document.querySelector("#result-label");
const resultMessage = document.querySelector("#result-message");
const statusBadge = document.querySelector("#status-badge");
const partialNotice = document.querySelector("#partial-notice");
const loadingCard = document.querySelector("#loading-card");
const errorCard = document.querySelector("#transport-error");
const errorMessage = document.querySelector("#transport-error-message");
const retryButton = document.querySelector("#retry-button");

const endpoint = document.querySelector('meta[name="odyssey-api-endpoint"]')?.content || "/api/request";
let retrySubmission = null;

function setBusy(isBusy) {
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  retryButton.disabled = isBusy;
  sendButton.textContent = isBusy ? "Enviando…" : "Enviar";
}

function showRequest(submission) {
  interaction.hidden = false;
  requestCard.hidden = false;
  requestText.textContent = submission.request;
}

function resetOutcome() {
  resultCard.hidden = true;
  loadingCard.hidden = true;
  errorCard.hidden = true;
  retryButton.hidden = true;
  partialNotice.hidden = true;
  statusBadge.hidden = true;
}

function showLoading() {
  resetOutcome();
  loadingCard.hidden = false;
}

function showResult(result) {
  resetOutcome();
  resultCard.hidden = false;
  resultMessage.textContent = result.message;

  const labels = {
    answer: "Odyssey",
    acknowledgement: "Hecho",
    empty: "Sin resultados",
    error: "No completado",
  };
  resultLabel.textContent = labels[result.kind] || "Odyssey";

  if (result.status === "partial") {
    statusBadge.textContent = "Parcial";
    statusBadge.hidden = false;
    partialNotice.hidden = false;
  }
}

function showTransportError(error) {
  resetOutcome();
  errorCard.hidden = false;
  const retryable = error instanceof ProductRequestError && error.retryable;
  errorMessage.textContent = retryable
    ? "No se ha podido confirmar si Odyssey recibió la solicitud. Puedes reintentar la misma entrega."
    : "Odyssey no ha podido procesar esta solicitud.";
  retryButton.hidden = !retryable;
}

async function sendSubmission(submission) {
  showRequest(submission);
  showLoading();
  setBusy(true);

  try {
    const result = await requestProductResult({endpoint, submission});
    retrySubmission = null;
    showResult(result);
  } catch (error) {
    retrySubmission = error instanceof ProductRequestError && error.retryable ? submission : null;
    showTransportError(error);
  } finally {
    setBusy(false);
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

  retrySubmission = null;
  void sendSubmission(submission);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

retryButton.addEventListener("click", () => {
  if (retrySubmission) {
    void sendSubmission(retrySubmission);
  }
});
