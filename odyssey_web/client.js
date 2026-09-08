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
export function createSubmission(rawRequest, cryptoImpl = globalThis.crypto) {
  const request = String(rawRequest ?? "").trim();
  if (!request) {
    throw new ProductRequestError("The request is empty.");
  }
  return {request, requestId: createRequestId(cryptoImpl)};
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

  return {request_id, status, kind, message};
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
