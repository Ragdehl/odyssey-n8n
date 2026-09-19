const ALLOWED_STATUSES = new Set(["completed", "partial", "needs_attention", "failed"]);
const ALLOWED_KINDS = new Set(["answer", "acknowledgement", "clarification", "empty", "error"]);
// The private runtime has a 120-second n8n deadline. Leave five seconds for
// n8n to shape its bounded response before treating delivery as uncertain.
export const PRODUCT_REQUEST_TIMEOUT_MS = 125_000;

/**
 * Represents a browser-side request failure without exposing server internals.
 */
export class ProductRequestError extends Error {
  /**
   * Create a bounded request error.
   *
   * @param {string} message Human-safe diagnostic for client logic.
   * @param {boolean} retryable Whether retrying the same logical delivery is appropriate.
   */
  constructor(message, retryable = false) {
    super(message);
    this.name = "ProductRequestError";
    this.retryable = retryable;
  }
}

/**
 * Create a safe delivery identifier for one new browser submission.
 *
 * @param {Crypto} cryptoImpl Browser crypto implementation.
 * @returns {string} Safe `web-...` request identifier.
 * @throws {ProductRequestError} When a secure UUID source is unavailable.
 */
export function createRequestId(cryptoImpl = globalThis.crypto) {
  if (!cryptoImpl || typeof cryptoImpl.randomUUID !== "function") {
    throw new ProductRequestError("No secure request identifier source is available.");
  }
  return `web-${cryptoImpl.randomUUID()}`;
}

/**
 * Normalize one new user submission and assign its delivery identity.
 *
 * @param {string} rawRequest User-entered request text.
 * @param {Crypto} cryptoImpl Browser crypto implementation.
 * @returns {{request: string, requestId: string}} Submission ready for transport.
 * @throws {ProductRequestError} When the request is empty.
 */
export function createSubmission(rawRequest, cryptoImpl = globalThis.crypto, conversationId = null) {
  const request = String(rawRequest ?? "").trim();
  if (!request) {
    throw new ProductRequestError("The request is empty.");
  }
  const submission = {request, requestId: createRequestId(cryptoImpl)};
  if (typeof conversationId === "string" && conversationId) submission.conversationId = conversationId;
  return submission;
}

/** Send one bounded conversation operation through the existing same-origin boundary. */
export async function requestConversation({endpoint = "/api/conversation", operation, payload = {}, fetchImpl = globalThis.fetch}) {
  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: {"Content-Type": "application/json", Accept: "application/json"},
    credentials: "same-origin",
    body: JSON.stringify({...payload, operation}),
  });
  if (!response.ok) throw new ProductRequestError("No se ha podido cargar la conversación.", false);
  const value = await response.json();
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey devolvió una conversación inválida.", false);
  }
  return value;
}

/**
 * Render a valid product result before attempting optional transcript continuity persistence.
 *
 * @param {{result: object, renderResult: (result: object) => void, persistAssistantTurn: () => Promise<void>, warnContinuity: () => void}} options Rendering and persistence callbacks.
 * @returns {Promise<void>} Resolves after the best-effort persistence attempt.
 */
export async function renderProductResultWithContinuity({result, renderResult, persistAssistantTurn, warnContinuity}) {
  renderResult(result);
  try {
    await persistAssistantTurn();
  } catch {
    warnContinuity();
  }
}

/**
 * Validate the narrow browser response contract returned by Odyssey Online.
 *
 * @param {unknown} value Parsed response payload.
 * @returns {{request_id: string, status: string, kind: string, message: string}} Valid response.
 * @throws {ProductRequestError} When the payload does not satisfy the product contract.
 */
export function validateProductResponse(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey returned an invalid response.");
  }

  const {request_id, status, kind, message} = value;
  if (typeof request_id !== "string" || request_id.length === 0) {
    throw new ProductRequestError("Odyssey returned an invalid request identifier.");
  }
  if (!ALLOWED_STATUSES.has(status)) {
    throw new ProductRequestError("Odyssey returned an unsupported status.");
  }
  if (!ALLOWED_KINDS.has(kind)) {
    throw new ProductRequestError("Odyssey returned an unsupported response kind.");
  }
  if (typeof message !== "string" || message.trim().length === 0) {
    throw new ProductRequestError("Odyssey returned an empty message.");
  }

  const result = {request_id, status, kind, message};
  if (value.request_detail !== undefined) {
    result.request_detail = validateRequestDetail(value.request_detail, request_id);
  }
  if (value.note_result_snapshot !== undefined) {
    result.note_result_snapshot = validateNoteResultSnapshot(value.note_result_snapshot);
  }
  return result;
}

function validateNoteResultSnapshot(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.version !== 1 ||
      typeof value.query !== "string" || value.query.length === 0 || !Array.isArray(value.filters) ||
      !Array.isArray(value.note_ids) || !Number.isInteger(value.total) ||
      typeof value.truncated !== "boolean" || typeof value.sort !== "string" ||
      typeof value.ranking_version !== "string" || typeof value.executed_at !== "string" ||
      value.note_ids.length > 64 || new Set(value.note_ids).size !== value.note_ids.length ||
      value.note_ids.some((id) => typeof id !== "string" || !id) ||
      value.truncated !== (value.total > value.note_ids.length)) {
    throw new ProductRequestError("Odyssey returned an invalid Notes result set.");
  }
  return {version: 1, query: value.query, filters: value.filters, sort: value.sort,
    ranking_version: value.ranking_version, executed_at: value.executed_at,
    note_ids: value.note_ids, total: value.total, truncated: value.truncated};
}

/**
 * Validate bounded diagnostic evidence for one logical request.
 *
 * @param {unknown} value Provider/runtime evidence projected by the product boundary.
 * @param {string} requestId Request identifier that must match the detail record.
 * @returns {object} Safe request detail suitable for text-only rendering.
 * @throws {ProductRequestError} When diagnostic evidence is malformed.
 */
export function validateRequestDetail(value, requestId) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.request_id !== requestId) {
    throw new ProductRequestError("Odyssey returned invalid request details.");
  }
  const operational = value.operational;
  if (!operational || typeof operational !== "object" || Array.isArray(operational)) {
    throw new ProductRequestError("Odyssey returned invalid operational details.");
  }
  if (operational.total_duration_ms !== null && typeof operational.total_duration_ms !== "number") {
    throw new ProductRequestError("Odyssey returned invalid request timing.");
  }
  if (!Array.isArray(operational.stages)) {
    throw new ProductRequestError("Odyssey returned invalid request stages.");
  }
  const stages = operational.stages.map((stage) => validateDetailStage(stage));
  const changes = value.changes === undefined ? undefined : validateDetailChanges(value.changes);
  const estimated_cost = value.estimated_cost === undefined ? undefined : validateEstimatedCost(value.estimated_cost);
  return {request_id: requestId, operational: {total_duration_ms: operational.total_duration_ms, stages}, changes, estimated_cost};
}

function validateEstimatedCost(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      !["estimated", "unavailable"].includes(value.status) || typeof value.pricing_basis !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(value.pricing_basis)) {
    throw new ProductRequestError("Odyssey returned invalid cost details.");
  }
  if (value.status === "estimated" && (typeof value.amount_usd !== "number" || !Number.isFinite(value.amount_usd) || value.amount_usd < 0)) {
    throw new ProductRequestError("Odyssey returned invalid cost details.");
  }
  return {status: value.status, amount_usd: value.status === "estimated" ? value.amount_usd : null, pricing_basis: value.pricing_basis};
}

function validateDetailStage(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey returned invalid stage details.");
  }
  const textFields = ["name", "outcome", "model", "reasoning_effort", "error_category"];
  if (typeof value.name !== "string" || typeof value.outcome !== "string") {
    throw new ProductRequestError("Odyssey returned invalid stage metadata.");
  }
  for (const field of textFields) {
    if (value[field] !== null && value[field] !== undefined && typeof value[field] !== "string") {
      throw new ProductRequestError("Odyssey returned invalid stage metadata.");
    }
  }
  if (value.duration_ms !== null && value.duration_ms !== undefined && typeof value.duration_ms !== "number") {
    throw new ProductRequestError("Odyssey returned invalid stage timing.");
  }
  if (!Array.isArray(value.provider_calls)) {
    throw new ProductRequestError("Odyssey returned invalid provider details.");
  }
  const usage = value.usage === null || value.usage === undefined ? undefined : validateUsage(value.usage);
  const providerCalls = value.provider_calls.map((call) => validateDetailStage({...call, provider_calls: []}));
  return {name: value.name, outcome: value.outcome, duration_ms: value.duration_ms, model: value.model,
    reasoning_effort: value.reasoning_effort, usage, error_category: value.error_category, provider_calls: providerCalls};
}

function validateUsage(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey returned invalid token details.");
  }
  const result = {};
  const allowed = new Set(["input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens"]);
  for (const [key, count] of Object.entries(value)) {
    if (!allowed.has(key)) throw new ProductRequestError("Odyssey returned unsupported token details.");
    if (!Number.isInteger(count) || count < 0) throw new ProductRequestError("Odyssey returned invalid token details.");
    result[key] = count;
  }
  return result;
}

function validateDetailChanges(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || !Array.isArray(value.units)) {
    throw new ProductRequestError("Odyssey returned invalid change details.");
  }
  const units = value.units.map((unit) => {
    if (!unit || typeof unit !== "object" || typeof unit.status !== "string" ||
        (unit.stable_note_id !== null && typeof unit.stable_note_id !== "string")) {
      throw new ProductRequestError("Odyssey returned invalid change details.");
    }
    return {status: unit.status, operation: typeof unit.operation === "string" ? unit.operation : null,
      stable_note_id: unit.stable_note_id};
  });
  return {affected_stable_note_ids: Array.isArray(value.affected_stable_note_ids)
    ? value.affected_stable_note_ids.filter((id) => typeof id === "string") : [], units};
}

/**
 * Send one logical browser delivery through the same-origin Odyssey product endpoint.
 *
 * @param {object} options Transport options.
 * @param {string} options.endpoint Same-origin endpoint selected by the page.
 * @param {{request: string, requestId: string}} options.submission Logical submission to send.
 * @param {typeof fetch} options.fetchImpl Fetch-compatible transport implementation.
 * @param {number} options.timeoutMs Maximum time to wait for a bounded product response.
 * @param {typeof AbortController} options.AbortControllerImpl Abort controller implementation.
 * @param {typeof setTimeout} options.setTimeoutImpl Timer implementation for the deadline.
 * @param {typeof clearTimeout} options.clearTimeoutImpl Timer cleanup implementation.
 * @returns {Promise<{request_id: string, status: string, kind: string, message: string}>} Valid result.
 * @throws {ProductRequestError} On transport, HTTP, JSON, or product-contract failure.
 */
export async function requestProductResult({
  endpoint,
  submission,
  conversationId = submission?.conversationId,
  fetchImpl = globalThis.fetch,
  timeoutMs = PRODUCT_REQUEST_TIMEOUT_MS,
  AbortControllerImpl = globalThis.AbortController,
  setTimeoutImpl = globalThis.setTimeout,
  clearTimeoutImpl = globalThis.clearTimeout,
}) {
  const controller = new AbortControllerImpl();
  const timeout = setTimeoutImpl(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetchImpl(endpoint, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        request: submission.request,
        request_id: submission.requestId,
        ...(conversationId ? {conversation_id: conversationId} : {}),
      }),
      signal: controller.signal,
    });
  } catch {
    throw new ProductRequestError("The request outcome is unknown because the network failed.", true);
  } finally {
    clearTimeoutImpl(timeout);
  }

  if (!response.ok) {
    const retryable = response.status >= 500;
    throw new ProductRequestError("Odyssey rejected or could not complete the HTTP request.", retryable);
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ProductRequestError("Odyssey returned an unreadable response.", true);
  }

  const result = validateProductResponse(payload);
  if (result.request_id !== submission.requestId) {
    throw new ProductRequestError("Odyssey returned a mismatched request identifier.");
  }
  return result;
}
