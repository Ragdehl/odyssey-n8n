import test from "node:test";
import assert from "node:assert/strict";
import {NotesRequestError, requestNotes, validateSchemaOperationResponse} from "../odyssey_web/notes-client.js";

const type = {id: "libro", name: "Libro", description: "Libros que leo",
  properties: [{id: "autor", description: "Quién lo escribió", value_type: "string",
    required: false, filterable: true}]};
const preview = {revision: 0, next_revision: 1, proposal_hash: "a".repeat(64),
  operation: "add_type", affected_type_id: "libro", type_preview: type};

test("schema model client validates and projects read-only proposals", () => {
  const parsed = validateSchemaOperationResponse("schema_preview", preview);
  assert.equal(parsed.kind, "schema_preview");
  assert.equal(parsed.type_preview.name, "Libro");
  assert.deepEqual(parsed.type_preview.properties, [{id: "autor", description: "Quién lo escribió",
    value_type: "string", required: false}]);
  assert.equal("filterable" in parsed.type_preview.properties[0], false);
});

test("schema model client rejects forged or incomplete schema responses", () => {
  const bad = [
    {...preview, proposal_hash: "invalid"},
    {...preview, next_revision: 3},
    {...preview, kind: "mutation"},
    {...preview, type_preview: {...type, name: ""}},
    {...preview, type_preview: {...type, properties: [{...type.properties[0], required: "yes"}]}},
    {...preview, type_preview: {...type, id: "other"}},
    {...preview, operation: "delete_type"},
  ];
  for (const item of bad) assert.throws(
    () => validateSchemaOperationResponse("schema_preview", item), NotesRequestError);
  for (const item of [
    {status: "ready", revision: 0},
    {status: "ready", revision: 0, can_confirm: "yes"},
    {status: "queued", request_id: "foo", revision: 0, next_revision: 3},
    {status: "active", request_id: "foo", revision: 1, actor_id: "someone"},
  ]) assert.throws(() => validateSchemaOperationResponse("schema_status", item), NotesRequestError);
});

test("schema transport is same-origin and never treats an error as confirmation", async () => {
  const calls = [];
  const fakeFetch = async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => preview};
  };
  const result = await requestNotes({endpoint: "/api/notes", operation: "schema_preview",
    payload: {expected_revision: 0, change: {operation: "add_type"}}, fetchImpl: fakeFetch});
  assert.equal(result.kind, "schema_preview");
  assert.equal(calls[0].url, "/api/notes");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(JSON.parse(calls[0].options.body).operation, "schema_preview");
  await assert.rejects(requestNotes({operation: "schema_confirm", payload: {},
    fetchImpl: async () => ({ok: false, json: async () => ({error: "invalid notes request"})})}),
  NotesRequestError);
});

test("activation client accepts one exact queued/active status and rejects write-shaped extras", () => {
  assert.equal(validateSchemaOperationResponse("schema_confirm", {
    status: "queued", request_id: "schema_1234", revision: 0, next_revision: 1,
  }).kind, "schema_confirm");
  assert.equal(validateSchemaOperationResponse("schema_status", {
    status: "ready", revision: 0, can_confirm: false,
  }).can_confirm, false);
  assert.throws(() => validateSchemaOperationResponse("schema_confirm", {
    status: "queued", request_id: "schema_1234", revision: 0,
    next_revision: 1, physical_write: true,
  }), NotesRequestError);
});

test("untrusted schema suggestion must match a validated canonical preview", () => {
  const suggested = {kind: "schema_suggestion", decision: "PROPOSE", message: "Crea un tipo Libro",
    change: {operation: "add_type", type: {id: "libro"}}, preview};
  assert.equal(validateSchemaOperationResponse("schema_suggest", suggested).decision, "PROPOSE");
  const wrong = [
    {...suggested, actor_id: "forged"},
    {...suggested, decision: "CONFIRM"},
    {...suggested, change: {operation: "add_type", type: {id: "another"}}},
    {...suggested, preview: {...preview, proposal_hash: "bad"}},
    {...suggested, message: "a".repeat(501)},
    {...suggested, change: {operation: "delete_type", type_id: "person"}},
    {...suggested, approved: true},
  ];
  for (const item of wrong) assert.throws(
    () => validateSchemaOperationResponse("schema_suggest", item), NotesRequestError);
  assert.equal(validateSchemaOperationResponse("schema_suggest", {
    kind: "schema_suggestion", decision: "CLARIFY", message: "¿Qué datos?", reuse_type_id: null,
  }).decision, "CLARIFY");
  assert.throws(() => validateSchemaOperationResponse("schema_suggest", {
    kind: "schema_suggestion", decision: "REUSE", message: "Reutiliza", reuse_type_id: "../notes",
  }), NotesRequestError);
});

test("final schema review response is advisory, hash-bound, and never carries approval", () => {
  const result = {kind: "schema_review", proposal_hash: "a".repeat(64),
    verdict: "CHECK", message: "Comprueba el tipo de dato.", issues: ["Recuento expresado como texto."]};
  assert.deepEqual(validateSchemaOperationResponse("schema_review", result), result);
  const wrong = [
    {...result, approved: true},
    {...result, change: {operation: "add_type"}},
    {...result, proposal_hash: "stale"},
    {...result, verdict: "PUBLISH"},
    {...result, issues: []},
    {...result, issues: Array(4).fill("demasiados")},
    {...result, message: ""},
    {...result, issues: ["a".repeat(301)]},
    {...result, verdict: "READY", issues: ["Incoherente"]},
  ];
  for (const item of wrong) assert.throws(
    () => validateSchemaOperationResponse("schema_review", item), NotesRequestError);
  assert.equal(validateSchemaOperationResponse("schema_review", {...result,
    verdict: "READY", issues: []}).verdict, "READY");
});

test("schema_backfill HTTP transport accepts exact signed-campaign public counters", async () => {
  const receipt = {
    kind: "schema_backfill", status: "in_progress", segment: 11, finished: false,
    total: 11000, pending: 500, interpreting: 0, writing: 0, updated: 10500,
    no_evidence: 0, ambiguous: 0, stale: 0, already_present: 0, deferred: 0,
  };
  const reply = await requestNotes({
    operation: "schema_backfill",
    payload: {target_type_id: "person", property_id: "profesion",
      expected_revision: 1, action: "status"},
    fetchImpl: async () => ({ok: true, json: async () => receipt}),
  });
  assert.deepEqual(reply, receipt);
  await assert.rejects(
    requestNotes({operation: "schema_backfill", payload: {},
      fetchImpl: async () => ({ok: true, json: async () =>
        ({...receipt, mutable_approved: true})})}),
    NotesRequestError);
});
