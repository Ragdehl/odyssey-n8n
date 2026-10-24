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
