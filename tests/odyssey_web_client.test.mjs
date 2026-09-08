import assert from "node:assert/strict";
import test from "node:test";

import {
  ProductRequestError,
  PRODUCT_REQUEST_TIMEOUT_MS,
  createRequestId,
  createSubmission,
  requestProductResult,
  validateProductResponse,
} from "../odyssey_web/client.js";

const fakeCrypto = {randomUUID: () => "11111111-2222-4333-8444-555555555555"};

function response({ok = true, status = 200, payload}) {
  return {
    ok,
    status,
    async json() {
      return payload;
    },
  };
}

test("new submissions trim text and receive a safe web request id", () => {
  assert.equal(createRequestId(fakeCrypto), "web-11111111-2222-4333-8444-555555555555");
  assert.deepEqual(createSubmission("  ¿Dónde trabaja Marta?  ", fakeCrypto), {
    request: "¿Dónde trabaja Marta?",
    requestId: "web-11111111-2222-4333-8444-555555555555",
  });
});

test("empty submissions fail before transport", () => {
  assert.throws(() => createSubmission("   ", fakeCrypto), ProductRequestError);
});

test("product response validation accepts only the narrow browser contract", () => {
  const valid = {
    request_id: "web-1",
    status: "partial",
    kind: "answer",
    message: "Marta trabaja en Thales.",
  };
  assert.deepEqual(validateProductResponse(valid), valid);
  assert.throws(
    () => validateProductResponse({...valid, kind: "debug_dump"}),
    ProductRequestError,
  );
  assert.throws(
    () => validateProductResponse({...valid, message: ""}),
    ProductRequestError,
  );
});

test("transport sends only request and request_id through same-origin JSON", async () => {
  const submission = {request: "Hola", requestId: "web-test"};
  let captured;
  const fetchImpl = async (endpoint, options) => {
    captured = {endpoint, options};
    return response({
      payload: {
        request_id: "web-test",
        status: "completed",
        kind: "acknowledgement",
        message: "Hecho.",
      },
    });
  };

  const result = await requestProductResult({
    endpoint: "/api/request",
    submission,
    fetchImpl,
  });

  assert.equal(captured.endpoint, "/api/request");
  assert.equal(captured.options.method, "POST");
  assert.equal(captured.options.credentials, "same-origin");
  assert.deepEqual(JSON.parse(captured.options.body), {
    request: "Hola",
    request_id: "web-test",
  });
  assert.equal(result.kind, "acknowledgement");
});

test("network failure is retryable so caller can reuse the same submission id", async () => {
  const submission = {request: "Hola", requestId: "web-retry"};
  const fetchImpl = async () => {
    throw new Error("offline");
  };

  await assert.rejects(
    requestProductResult({endpoint: "/api/request", submission, fetchImpl}),
    (error) => error instanceof ProductRequestError && error.retryable === true,
  );
  assert.equal(submission.requestId, "web-retry");
});

test("transport timeout aborts the same delivery and leaves it retryable", async () => {
  const submission = {request: "Hola", requestId: "web-timeout"};
  let timeoutCallback;
  let aborted = false;
  class FakeAbortController {
    constructor() {
      this.signal = {};
    }
    abort() {
      aborted = true;
    }
  }
  const fetchImpl = async (_endpoint, options) => {
    timeoutCallback();
    assert.equal(options.signal instanceof Object, true);
    throw new Error("aborted");
  };

  await assert.rejects(
    requestProductResult({
      endpoint: "/api/request",
      submission,
      fetchImpl,
      AbortControllerImpl: FakeAbortController,
      setTimeoutImpl: (callback, delay) => {
        assert.equal(delay, PRODUCT_REQUEST_TIMEOUT_MS);
        timeoutCallback = callback;
        return "timer";
      },
      clearTimeoutImpl: (timer) => assert.equal(timer, "timer"),
    }),
    (error) => error instanceof ProductRequestError && error.retryable === true,
  );
  assert.equal(aborted, true);
  assert.equal(submission.requestId, "web-timeout");
});

test("client fails closed if server returns a different request id", async () => {
  const submission = {request: "Hola", requestId: "web-original"};
  const fetchImpl = async () => response({
    payload: {
      request_id: "web-other",
      status: "completed",
      kind: "answer",
      message: "Respuesta",
    },
  });

  await assert.rejects(
    requestProductResult({endpoint: "/api/request", submission, fetchImpl}),
    (error) => error instanceof ProductRequestError && error.retryable === false,
  );
});
