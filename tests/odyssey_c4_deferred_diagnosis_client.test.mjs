import test from "node:test";
import assert from "node:assert/strict";
import {validatedDeferredDiagnosis, pollDeferredDiagnosis} from "../odyssey_web/deferred_diagnosis.js";

const id = "c4-deferred-test";
const stage = "candidate.source_boundary_review";
const view = {version: 1, label: "Core · revisión de la división", icon: "core"};
const ledger = {stages: [{name: stage, outcome: "failed", route_index: null, stage_view: view}]};
const diagnosis = {
  evidence_stage: stage, next_step: "CHECK_SYSTEM", reason_code: "SOURCE_UNVERIFIED",
  route_index: null, stage_view: view, status: "needs_attention",
  verified_stage_only: true, write_evidence: "UNKNOWN",
};
const ready = {version: 1, request_id: id, status: "completed", diagnosis};

test("deferred C4 attaches only an evidence-bound typed explanation", () => {
  const message = validatedDeferredDiagnosis(ready, id, "needs_attention", ledger);
  assert.match(message, /Core · revisión de la división/);
  assert.match(message, /No se ha podido confirmar si hubo cambios/);
  assert.doesNotMatch(message, /ya he guardado/);
});

test("wrong actor, route, write state and untrusted model prose are refused", () => {
  const invalid = [
    {...ready, request_id: "someone-else"},
    {...ready, diagnosis: {...diagnosis, route_index: 1}},
    {...ready, diagnosis: {...diagnosis, evidence_stage: "core.identity_resolution"}},
    {...ready, diagnosis: {...diagnosis, explanation: "Ya he guardado todos tus archivos"}},
    {...ready, diagnosis: {...diagnosis, next_step: "ASK_USER"}},
    {...ready, diagnosis: {...diagnosis, stage_view: {...view, label: "Datos guardados"}}},
    {...ready, diagnosis: {...diagnosis, stage_view: {...view, label: "<script>"}}},
  ];
  for (const item of invalid) {
    assert.equal(validatedDeferredDiagnosis(item, id, "needs_attention", ledger), null);
  }
  assert.equal(validatedDeferredDiagnosis(ready, id, "completed", ledger), null);
  assert.equal(validatedDeferredDiagnosis(ready, id, "needs_attention", {}), null);
});

test("poll never invokes replay and stops on completed or unavailable", async () => {
  let calls = 0;
  const messages = [];
  await pollDeferredDiagnosis({
    request: async () => (++calls === 1
      ? {version: 1, request_id: id, status: "pending"} : ready),
    requestId: id, originalStatus: "needs_attention", ledger,
    delay: async () => {}, onResult: message => messages.push(message),
  });
  assert.equal(calls, 2);
  assert.equal(messages.length, 1);
  calls = 0;
  await pollDeferredDiagnosis({
    request: async () => { calls++; return {version: 1, request_id: id, status: "unavailable"}; },
    requestId: id, originalStatus: "needs_attention", ledger,
    delay: async () => {}, onResult: () => assert.fail("unexpected advice"),
  });
  assert.equal(calls, 1);
});
