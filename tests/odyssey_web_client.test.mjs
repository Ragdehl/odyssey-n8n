import assert from "node:assert/strict";
import test from "node:test";

import {
  ProductRequestError,
  PRODUCT_REQUEST_TIMEOUT_MS,
  createRequestId,
  createSubmission,
  renderProductResultWithContinuity,
  requestConversation,
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

test("a missing secure identifier source fails closed", () => {
  assert.throws(() => createRequestId(null), ProductRequestError);
});

test("main-conversation transport accepts only an object response", async () => {
  let captured;
  const loaded = await requestConversation({
    operation: "load_main",
    payload: {conversation_id: "main"},
    fetchImpl: async (endpoint, options) => {
      captured = {endpoint, options};
      return response({payload: {conversation_id: "main", turns: []}});
    },
  });

  assert.equal(captured.endpoint, "/api/conversation");
  assert.deepEqual(JSON.parse(captured.options.body), {
    conversation_id: "main",
    operation: "load_main",
  });
  assert.equal(loaded.conversation_id, "main");
  await assert.rejects(
    requestConversation({operation: "load_main", fetchImpl: async () => response({payload: []})}),
    ProductRequestError,
  );
});

test("a successful product result renders once when assistant continuity persists", async () => {
  const rendered = [];
  let persisted = 0;
  let warned = 0;
  const result = {request_id: "web-success", message: "Marta vive en Lyon."};

  await renderProductResultWithContinuity({
    result,
    renderResult: (value) => rendered.push(value),
    persistAssistantTurn: async () => { persisted += 1; },
    warnContinuity: () => { warned += 1; },
  });

  assert.deepEqual(rendered, [result]);
  assert.equal(persisted, 1);
  assert.equal(warned, 0);
});

test("a continuity persistence failure keeps the valid product result visible", async () => {
  const rendered = [];
  let warned = 0;
  const result = {request_id: "web-continuity", message: "Marta vive en Lyon."};

  await renderProductResultWithContinuity({
    result,
    renderResult: (value) => rendered.push(value),
    persistAssistantTurn: async () => { throw new Error("conversation unavailable"); },
    warnContinuity: () => { warned += 1; },
  });

  assert.deepEqual(rendered, [result]);
  assert.equal(warned, 1);
});

test("closed planner clarification is a normal bounded product result", () => {
  const result = validateProductResponse({
    request_id: "web-clarify",
    status: "needs_attention",
    kind: "clarification",
    message: "No he podido interpretar la solicitud.",
  });

  assert.equal(result.status, "needs_attention");
  assert.equal(result.kind, "clarification");
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

test("request detail accepts estimated cost with a dated pricing basis", () => {
  const result = validateProductResponse({
    request_id: "web-cost",
    status: "completed",
    kind: "answer",
    message: "Hecho.",
    request_detail: {
      request_id: "web-cost",
      operational: {total_duration_ms: 10, stages: []},
      estimated_cost: {status: "estimated", amount_usd: 0.000123, pricing_basis: "2026-09-07"},
    },
  });
  assert.equal(result.request_detail.estimated_cost.amount_usd, 0.000123);
  assert.throws(() => validateProductResponse({
    request_id: "web-cost",
    status: "completed",
    kind: "answer",
    message: "Hecho.",
    request_detail: {
      request_id: "web-cost",
      operational: {total_duration_ms: 10, stages: []},
      estimated_cost: {status: "estimated", amount_usd: 0, pricing_basis: "unknown"},
    },
  }), ProductRequestError);
});

test("request detail retains only validated bounded operational evidence", () => {
  const result = validateProductResponse({
    request_id: "web-detail",
    status: "completed",
    kind: "acknowledgement",
    message: "Hecho.",
    request_detail: {
      request_id: "web-detail",
      operational: {
        total_duration_ms: null,
        stages: [{
          name: "planner",
          outcome: "completed",
          duration_ms: 12,
          model: "gpt-5.6-luna",
          reasoning_effort: "low",
          error_category: null,
          usage: {input_tokens: 3, output_tokens: 2},
          provider_calls: [{
            name: "provider",
            outcome: "completed",
            duration_ms: null,
            model: null,
            reasoning_effort: null,
            error_category: null,
            provider_calls: [],
          }],
        }],
      },
      changes: {
        affected_stable_note_ids: ["note-1", 4],
        units: [{status: "updated", operation: "update", stable_note_id: "note-1"}],
      },
      estimated_cost: {status: "unavailable", pricing_basis: "2026-09-07"},
    },
  });

  assert.deepEqual(result.request_detail.changes.affected_stable_note_ids, ["note-1"]);
  assert.equal(result.request_detail.operational.stages[0].usage.output_tokens, 2);
  assert.equal(result.request_detail.estimated_cost.amount_usd, null);
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

test("main-conversation transport remains correlated before history reload completes", async () => {
  const submission = createSubmission("Hola", fakeCrypto, "main");
  let captured;
  const fetchImpl = async (_endpoint, options) => {
    captured = options;
    return response({
      payload: {
        request_id: submission.requestId,
        status: "completed",
        kind: "acknowledgement",
        message: "Hecho.",
      },
    });
  };

  await requestProductResult({endpoint: "/api/request", submission, fetchImpl});

  assert.equal(JSON.parse(captured.body).conversation_id, "main");
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
