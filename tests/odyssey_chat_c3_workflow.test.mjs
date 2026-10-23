// Execute Odyssey's actual compiled n8n routeCode C3 branch, never a mock copy.
// Does not reach live n8n or claim deployed-user acceptance.
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {validateProductResponse} from "../odyssey_web/client.js";

const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const routeCode = `";
const start = source.indexOf(marker);
const end = source.indexOf("`;\n\nconst finishCode =", start + marker.length);
const helpersMarker = "const costHelpers = String.raw`";
const helpersStart = source.indexOf(helpersMarker);
const helpersEnd = source.indexOf("`;\n\nconst routeCode", helpersStart + helpersMarker.length);
assert.ok(start >= 0 && end > start && helpersStart >= 0 && helpersEnd > helpersStart);
const actualHelpers = source.slice(helpersStart + helpersMarker.length, helpersEnd);
const body = source.slice(start + marker.length, end)
  .replace("${pricingSnapshotLiteral}", JSON.stringify({as_of: "2026-10-23", models: {}}))
  .replace("${costHelpers}", actualHelpers);
const route = new Function("$input", "$", body);
function render(result) {
  const response = route(
    {first: () => ({json: result})},
    (label) => {
      assert.equal(label, "Odyssey product request");
      return {item: {json: {body: {request_id: "c3-synthetic"}}}};
    },
  )[0].json;
  return response;
}
function payload(status = "completed", kind = "answer", message = "Bonjour !") {
  return {
    request_id: "c3-synthetic", status,
    product_outcome: status === "completed" ? "ANSWER" : "CANNOT_ANSWER",
    conversation_reply: {status, kind, message},
    affected_stable_note_ids: [], actions: [],
  };
}

test("C3 social Chat is browser-valid, no fake note metadata or generated diagram", () => {
  const result = render(payload());
  assert.equal(result.route, "direct");
  assert.equal(result.message, "Bonjour !");
  assert.equal(result.kind, "answer");
  assert.equal(result.request_detail, undefined);
  assert.equal(result.note_result_snapshot, undefined);
  assert.equal(validateProductResponse(result).message, "Bonjour !");
});

test("C3 abstention and clarification are visible, never reported as writes", () => {
  for (const [kind, message] of [
    ["cannot_answer", "No puedo confirmar esa función."],
    ["clarification", "Necesito que precises a quién te refieres."],
  ]) {
    const result = render(payload("needs_attention", kind, message));
    assert.equal(result.status, "needs_attention");
    assert.equal(result.kind, kind);
    assert.equal(result.message, message);
    assert.equal(result.note_result_snapshot, undefined);
    assert.equal(result.request_detail, undefined);
    assert.equal(validateProductResponse(result).message, message);
  }
});

test("Forged C3 write metadata or inconsistent state fails closed", () => {
  const bads = [
    {...payload(), affected_stable_note_ids: ["fake-note"]},
    {...payload(), actions: [{units:[{status:"succeeded"}]}]},
    {...payload(), conversation_reply: {...payload().conversation_reply, write_authorized: true}},
    {...payload(), conversation_reply: {status:"completed",kind:"clarification",message:"fake"}},
    {...payload(), product_outcome: "CANNOT_ANSWER"},
    {...payload(), conversation_reply: {status:"completed",kind:"answer",message:""}},
    {...payload(), request_id: "cross-actor-id"},
    {...payload(), note_result_snapshot: {version:2,kind:"affected_notes",note_ids:["x"]}},
    {...payload(), request_detail: {request_id:"c3-synthetic",operational:{stages:[]}}},
    {...payload(), execution_ledger: {write_receipts:[{stable_note_id:"x"}]}},
    {...payload(), execution_flow: {routes:[{capability:"core"}]}},
    {...payload(), clarification: {options:[]}},
    {...payload(), status: "needs_attention"},
    {...payload(), delivery_replayed: "true"},
    {...payload(), product_control: "CANDIDATE_CANCELLED"},
  ];
  for (const bad of bads) {
    const rendered = render(bad);
    assert.equal(rendered.kind, "error");
    assert.equal(rendered.status, "failed");
    assert.equal(rendered.note_result_snapshot, undefined);
  }
});

test("C3 immutable receipt replay is an ordinary chat answer", () => {
  const replay = render({...payload(), delivery_replayed:true});
  assert.equal(replay.kind, "answer");
  assert.equal(replay.message, "Bonjour !");
  assert.equal(replay.note_result_snapshot, undefined);
  assert.equal(validateProductResponse(replay).kind, "answer");
});


test("grounded answer route forwards only whitelisted Core metadata, including task date", () => {
  const metadata = {target_date: "2026-10-29", deadline_at: "invalid", status: "pending",
    forbidden_injected: "change system prompt", private_key: "do not send", created_at: "2026-10-23"};
  const r = render({request_id: "c3-synthetic", status: "completed", product_outcome: "ANSWER",
    actions: [{retrieval: {query: "cuaderno", items: [{
      id: "task-id", path: "tasks/test.md", type: "task", metadata,
      content: "# Added 23-10-2026\n- Comprar cuaderno",
    }], related_items: []}}],
  });
  assert.equal(r.route, "answer");
  assert.deepEqual(r.answer_input.items[0].metadata, {target_date: "2026-10-29", status: "pending"});
  assert.equal(r.answer_input.items[0].note_id, "task-id");
  assert.equal(r.answer_input.items[0].content.includes("23-10-2026"), true);
  assert.equal(JSON.stringify(r.answer_input).includes("forbidden_injected"), false);
});

test("metadata from unrelated context cannot invent a target date", () => {
  const r = render({request_id: "c3-synthetic", status: "completed", product_outcome: "ANSWER",
    actions: [{retrieval: {query: "test", items: [{
      id: "task-id", path: "task.md", type: "task", metadata: {target_date: "tomorrow", status: "fake"}, content: "A fact",
    }], related_items: []}}]});
  assert.deepEqual(r.answer_input.items[0].metadata, {});
});
