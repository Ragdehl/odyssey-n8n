const ALLOWED_STATUSES = new Set(["completed", "partial", "needs_attention", "failed"]);
const ALLOWED_KINDS = new Set(["answer", "acknowledgement", "clarification", "cannot_answer", "empty", "error", "note_set"]);
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

/**
 * Find the newest durable user turn whose same-ID assistant outcome is missing.
 *
 * The caller may offer this original logical delivery for explicit recovery after reload, but must
 * not automatically resend it.
 */
export function findRecoverableSubmission(turns, conversationId = "main") {
  if (!Array.isArray(turns) || typeof conversationId !== "string" || !conversationId) return null;
  const answered = new Set(
    turns
      .filter((turn) => turn && turn.role === "assistant" && typeof turn.request_id === "string")
      .map((turn) => turn.request_id),
  );
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    const turn = turns[index];
    if (!turn || turn.role !== "user" || typeof turn.request_id !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(turn.request_id) ||
        typeof turn.text !== "string" || !turn.text.trim() || answered.has(turn.request_id)) continue;
    return {request: turn.text, requestId: turn.request_id, conversationId};
  }
  return null;
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
  if (value.turns === undefined) return value;
  if (!Array.isArray(value.turns)) {
    throw new ProductRequestError("Odyssey devolvió una conversación inválida.", false);
  }
  return {...value, turns: value.turns.map(validateConversationTurn)};
}

function validateConversationTurn(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey devolvió una conversación inválida.", false);
  }
  if (value.note_result_snapshot === undefined) return value;
  return {...value, note_result_snapshot: validateNoteResultSnapshot(value.note_result_snapshot)};
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
  if (value.collection_members !== undefined) {
    if (!Array.isArray(value.collection_members) || value.collection_members.length > 64 ||
        value.collection_members.some((member) => !member || typeof member.value !== "string" ||
          !member.value.trim() || member.value.length > 512 ||
          (member.kind !== "literal" && member.kind !== "identity") ||
          typeof member.source_note_id !== "string" || !member.source_note_id ||
          member.source_note_id.length > 128 ||
          (member.stable_note_id !== null &&
            (typeof member.stable_note_id !== "string" || member.stable_note_id.length > 128)))) {
      throw new ProductRequestError("Odyssey returned an invalid collection.");
    }
    result.collection_members = value.collection_members;
  }
  if (value.clarification !== undefined) {
    const clarification = value.clarification;
    if (!clarification || typeof clarification.request_id !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(clarification.request_id) ||
        !Array.isArray(clarification.options) || clarification.options.length > 4 ||
        clarification.options.some((option) => !option || typeof option.id !== "string" ||
          !option.id || option.id.length > 128 ||
          typeof option.label !== "string" || !option.label.trim() || option.label.length > 160)) {
      throw new ProductRequestError("Odyssey returned an invalid clarification.");
    }
    result.clarification = clarification;
  }
  return result;
}

function validateNoteResultSnapshot(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductRequestError("Odyssey returned an invalid Notes result set.");
  }
  if (value.version === 2) return validateAffectedNotesSnapshot(value);
  if (value.version !== 1 ||
      typeof value.query !== "string" || value.query.length === 0 || !Array.isArray(value.filters) ||
      !Array.isArray(value.note_ids) || !Number.isInteger(value.total) ||
      typeof value.truncated !== "boolean" || typeof value.sort !== "string" ||
      typeof value.ranking_version !== "string" || typeof value.executed_at !== "string" ||
      value.note_ids.length > 64 || new Set(value.note_ids).size !== value.note_ids.length ||
      utf8Bytes(value.query) > 512 || value.filters.length > 16 ||
      value.filters.some((filter) => !filter || typeof filter !== "object" || Array.isArray(filter) ||
        Object.keys(filter).length !== 3 || typeof filter.field !== "string" || typeof filter.op !== "string" || !("value" in filter)) ||
      value.note_ids.some((id) => typeof id !== "string" || !id) ||
      value.truncated !== (value.total > value.note_ids.length)) {
    throw new ProductRequestError("Odyssey returned an invalid Notes result set.");
  }
  return {version: 1, query: value.query, filters: value.filters, sort: value.sort,
    ranking_version: value.ranking_version, executed_at: value.executed_at,
    note_ids: value.note_ids, total: value.total, truncated: value.truncated};
}

function validateAffectedNotesSnapshot(value) {
  if (Object.keys(value).length !== 6 || value.kind !== "affected_notes" ||
      typeof value.executed_at !== "string" || !Array.isArray(value.note_ids) ||
      !Number.isInteger(value.total) || typeof value.truncated !== "boolean" ||
      value.note_ids.length > 64 || new Set(value.note_ids).size !== value.note_ids.length ||
      value.note_ids.some((id) => typeof id !== "string" || !id) ||
      value.total < 1 ||
      value.total < value.note_ids.length ||
      value.truncated !== (value.total > value.note_ids.length)) {
    throw new ProductRequestError("Odyssey returned an invalid Notes result set.");
  }
  return {version: 2, kind: "affected_notes", executed_at: value.executed_at,
    note_ids: value.note_ids, total: value.total, truncated: value.truncated};
}

function utf8Bytes(value) { return new TextEncoder().encode(value).length; }

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
  const operational = validateOperational(value.operational);
  const changes = value.changes === undefined ? undefined : validateDetailChanges(value.changes);
  const estimated_cost = value.estimated_cost === undefined ? undefined : validateEstimatedCost(value.estimated_cost);
  return {request_id: requestId, operational, changes, estimated_cost};
}

/** Validate the same bounded operational hierarchy for Chat and intelligent Notes. */
export function validateOperational(operational) {
  if (!operational || typeof operational !== "object" || Array.isArray(operational)) {
    throw new ProductRequestError("Odyssey returned invalid operational details.");
  }
  if (operational.total_duration_ms !== null && !validMs(operational.total_duration_ms)) {
    throw new ProductRequestError("Odyssey returned invalid request timing.");
  }
  if (!Array.isArray(operational.stages)) {
    throw new ProductRequestError("Odyssey returned invalid request stages.");
  }
  const stages = operational.stages.map((stage) => validateDetailStage(stage));
  const coverage = operational.coverage === undefined ? undefined : validateCoverage(operational.coverage);
  const productExecution = operational.product_execution_duration_ms;
  const browserProduct = operational.browser_product_duration_ms;
  if (productExecution !== undefined && !validMs(productExecution)) {
    throw new ProductRequestError("Odyssey returned invalid product timing.");
  }
  if (browserProduct !== undefined && !validMs(browserProduct)) {
    throw new ProductRequestError("Odyssey returned invalid product timing.");
  }
  return {total_duration_ms: operational.total_duration_ms, stages,
    ...(coverage ? {coverage} : {}), ...(productExecution !== undefined ? {product_execution_duration_ms: productExecution} : {}),
    ...(browserProduct !== undefined ? {browser_product_duration_ms: browserProduct} : {})};
}

function validMs(value) { return typeof value === "number" && Number.isFinite(value) && value >= 0; }

function validateCoverage(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      ["attributed_ms", "unattributed_ms", "coverage_pct", "overlapping_ms"].some(key => !validMs(value[key])) ||
      value.coverage_pct > 100) throw new ProductRequestError("Odyssey returned invalid timing coverage.");
  return {attributed_ms: value.attributed_ms, unattributed_ms: value.unattributed_ms,
    coverage_pct: value.coverage_pct, overlapping_ms: value.overlapping_ms};
}

function validateSpans(value) {
  if (!Array.isArray(value) || value.length > 128) throw new ProductRequestError("Odyssey returned invalid timing spans.");
  return value.map(span => {
    if (!span || typeof span !== "object" || Array.isArray(span) || typeof span.name !== "string" || span.name.length > 80 ||
        typeof span.outcome !== "string" || !validMs(span.start_offset_ms) || !validMs(span.duration_ms) ||
        (span.error_category != null && (typeof span.error_category !== "string" || span.error_category.length > 120))) {
      throw new ProductRequestError("Odyssey returned invalid timing spans.");
    }
    return {name: span.name, outcome: span.outcome, start_offset_ms: span.start_offset_ms,
      duration_ms: span.duration_ms, error_category: span.error_category ?? null};
  });
}

function validateInputSizes(value) {
  const allowed = new Set(["fixed_instructions_bytes", "retrieval_capabilities_bytes", "write_capabilities_bytes",
    "recent_context_bytes", "luna_rules_examples_bytes", "user_request_bytes", "structured_output_schema_bytes"]);
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length > 12 ||
      Object.entries(value).some(([key, size]) => !allowed.has(key) || !Number.isInteger(size) || size < 0)) {
    throw new ProductRequestError("Odyssey returned invalid input-size evidence.");
  }
  return {...value};
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
  if (value.start_offset_ms !== undefined && !validMs(value.start_offset_ms)) throw new ProductRequestError("Odyssey returned invalid stage offset.");
  const substeps = value.substeps === undefined ? undefined : validateSpans(value.substeps);
  const coverage = value.coverage === undefined ? undefined : validateCoverage(value.coverage);
  const input_sizes = value.input_sizes === undefined ? undefined : validateInputSizes(value.input_sizes);
  const diagnostics = {};
  for (const key of ["validation_stage", "validation_code", "provider_status", "incomplete_reason", "parse_status", "result_kind"]) {
    if (value[key] == null) continue;
    if (typeof value[key] !== "string" || value[key].length > 120) throw new ProductRequestError("Odyssey returned invalid provider diagnostics.");
    diagnostics[key] = value[key];
  }
  for (const key of ["ordinal", "attempt_count", "output_text_chars", "output_text_bytes"]) {
    if (value[key] == null) continue;
    if (!Number.isInteger(value[key]) || value[key] < 0) throw new ProductRequestError("Odyssey returned invalid provider diagnostics.");
    diagnostics[key] = value[key];
  }
  return {name: value.name, outcome: value.outcome, duration_ms: value.duration_ms, model: value.model,
    reasoning_effort: value.reasoning_effort, usage, error_category: value.error_category, provider_calls: providerCalls,
    ...(value.start_offset_ms !== undefined ? {start_offset_ms: value.start_offset_ms} : {}),
    ...(substeps ? {substeps} : {}), ...(coverage ? {coverage} : {}), ...(input_sizes ? {input_sizes} : {}), ...diagnostics};
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
  monotonicImpl = globalThis.performance?.now?.bind(globalThis.performance),
}) {
  const controller = new AbortControllerImpl();
  const timeout = setTimeoutImpl(() => controller.abort(), timeoutMs);
  const started = typeof monotonicImpl === "function" ? monotonicImpl() : null;
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
        ...(submission.replyToRequestId ? {reply_to_request_id: submission.replyToRequestId} : {}),
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
  const finished = typeof monotonicImpl === "function" ? monotonicImpl() : null;
  if (result.request_detail && validMs(started) && validMs(finished) && finished >= started) {
    result.request_detail.operational.browser_product_duration_ms = finished - started;
  }
  return result;
}
