import test from "node:test";
import assert from "node:assert/strict";
import {createSchemaModel} from "../odyssey_web/schema-model.js";

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.className = "";
    this.children = [];
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this._text = "";
    this.handlers = new Map();
  }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map((node) => node.textContent).join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ""; this.children = children; }
  addEventListener(event, handler) { this.handlers.set(event, handler); }
  setAttribute(name, value) { this[name] = value; }
  focus() { this.focused = true; }
  click() { this.handlers.get("click")?.(); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  querySelectorAll(selector) {
    const matches = (node) => selector.startsWith(".")
      ? (node.className ?? "").split(" ").includes(selector.slice(1))
      : node.tagName === selector;
    return this.children.flatMap((child) => [
      ...(matches(child) ? [child] : []), ...(child.querySelectorAll?.(selector) ?? []),
    ]);
  }
}

globalThis.document = {createElement: (tag) => new Element(tag)};
globalThis.crypto ??= {randomUUID: () => "00000000-0000-4000-8000-000000000001"};

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
}

const makeType = (name = "Libro") => ({
  kind: "schema_preview", operation: "add_type", proposal_hash: "a".repeat(64),
  revision: 0, next_revision: 1, affected_type_id: "libro",
  type_preview: {id: "libro", name, description: "Libros que leo",
    properties: [{id: "autor", description: "autor", value_type: "string", required: false}]},
});

const ready = (canConfirm = false) => ({kind: "schema_status", status: "ready",
  revision: 0, can_confirm: canConfirm});

function makeClient(responder) {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    return responder(input);
  };
  return {client, calls};
}

test("disconnected editor shows an honest unavailable state, no proposal or publication", async () => {
  const {client, calls} = makeClient(() => {throw new Error("feature disabled");});
  const root = new Element("section");
  const panel = createSchemaModel({root, client});
  await panel.open({kind: "new"});
  assert.equal(panel.element.hidden, false);
  assert.match(panel.element.textContent, /aún no está disponible/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].operation, "schema_status");
  panel.close();
  assert.equal(panel.element.hidden, true);
});

test("new type asks human questions, previews through Notes, and never auto-confirms", async () => {
  const {client, calls} = makeClient((call) => {
    if (call.operation === "schema_status") return ready(false);
    if (call.operation === "schema_preview") return makeType();
    throw new Error("Unexpected write");
  });
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
  const inputs = panel.element.querySelectorAll(".schema-model-input");
  inputs[0].value = "Libro";
  inputs[1].value = "Libros que leo";
  inputs[2].value = "autor";
  panel.element.querySelector(".schema-model-propose").click();
  await flush();
  const preview = calls.find((call) => call.operation === "schema_preview");
  assert.deepEqual(preview.payload.change, {operation: "add_type", type: {
    id: "libro", name: "Libro", description: "Libros que leo", examples: [],
    properties: [{id: "autor", value_type: "string", description: "autor"}],
  }});
  assert.equal(panel.element.querySelector(".schema-model-preview").hidden, false);
  assert.match(panel.element.textContent, /La aprobación y el análisis de las notas anteriores aún no están habilitados/);
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
  panel.element.querySelector(".schema-model-confirm").click();
  await flush();
  assert.equal(calls.filter((x) => x.operation === "schema_confirm").length, 0);
});

test("typed existing type property previews before one click, then only polls original request", async () => {
  const {client, calls} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(true);
    if (operation === "schema_preview") return {
      ...makeType("Persona"), operation: "add_property", affected_type_id: "person",
      type_preview: {id: "person", name: "Persona", description: "Persona",
        properties: [{id: "oficio", description: "Profesión actual", value_type: "string", required: false}]},
    };
    if (operation === "schema_confirm") return {kind: "schema_confirm", status: "queued",
      request_id: payload.request_id, revision: 0, next_revision: 1};
    if (operation === "schema_status") return {kind: "schema_status", status: "active",
      request_id: payload.request_id, revision: 1};
    throw new Error("Unexpected operation");
  });
  let activeCount = 0;
  const panel = createSchemaModel({root: new Element("section"), client,
    onActive: () => {activeCount += 1;}});
  await panel.open({kind: "add-property", type: {id: "person", name: "Persona"}});
  const inputs = panel.element.querySelectorAll(".schema-model-input");
  inputs[0].value = "Oficio";
  inputs[1].value = "Profesión actual";
  inputs[2].value = "string";
  panel.element.querySelector(".schema-model-propose").click();
  await flush();
  assert.deepEqual(calls.find((call) => call.operation === "schema_preview").payload.change, {
    operation: "add_property", type_id: "person",
    property: {id: "oficio", description: "Profesión actual", value_type: "string"},
  });
  const confirm = panel.element.querySelector(".schema-model-confirm");
  assert.equal(confirm.disabled, false);
  confirm.click();
  await flush();
  assert.equal(calls.filter((call) => call.operation === "schema_confirm").length, 1);
  confirm.click();
  await flush();
  assert.equal(calls.filter((call) => call.operation === "schema_confirm").length, 1);
  assert.equal(panel.element.querySelector(".schema-model-retry").hidden, false);
  panel.element.querySelector(".schema-model-retry").click();
  await flush();
  assert.equal(activeCount, 1);
  assert.match(panel.element.textContent, /Cambio activo/);
  assert.equal(panel.element.querySelector(".schema-model-retry").hidden, true);
});

test("a failed ACK never automatically resubmits the approval", async () => {
  let confirmations = 0;
  const {client} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(true);
    if (operation === "schema_preview") return makeType();
    if (operation === "schema_confirm") {confirmations += 1; throw new Error("lost response");}
    if (operation === "schema_status") return {kind: "schema_status", status: "queued",
      request_id: payload.request_id, revision: 0, next_revision: 1};
    throw new Error("Unexpected call");
  });
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  const inputs = panel.element.querySelectorAll(".schema-model-input");
  inputs[0].value = "Libro"; inputs[1].value = "Libros que leo";
  panel.element.querySelector(".schema-model-propose").click(); await flush();
  const action = panel.element.querySelector(".schema-model-confirm");
  action.click(); await flush();
  action.click(); await flush();
  assert.equal(confirmations, 1);
  assert.match(panel.element.textContent, /No la repitas/);
  panel.element.querySelector(".schema-model-retry").click(); await flush();
  assert.equal(confirmations, 1);
});

test("closing the panel invalidates a late untrusted preview response", async () => {
  let release;
  const {client} = makeClient(({operation}) => operation === "schema_status" ? ready() :
    new Promise((resolve) => {release = resolve;}));
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  const inputs = panel.element.querySelectorAll(".schema-model-input");
  inputs[0].value = "Libro"; inputs[1].value = "Libros que leo";
  panel.element.querySelector(".schema-model-propose").click(); await flush();
  panel.close();
  release(makeType()); await flush();
  assert.equal(panel.element.hidden, true);
  assert.equal(panel.element.querySelector(".schema-model-preview").hidden, true);
});

test("pending approval survives Notes reload and uses actor-scoped status instead of a second confirm", async () => {
  const store = new Map();
  const storage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
    removeItem: (key) => store.delete(key),
  };
  let activated = false;
  const {client, calls} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(true);
    if (operation === "schema_preview") return makeType();
    if (operation === "schema_confirm") return {kind: "schema_confirm", status: "queued",
      request_id: payload.request_id, revision: 0, next_revision: 1};
    if (operation === "schema_status") return {kind: "schema_status",
      status: activated ? "active" : "queued", request_id: payload.request_id,
      revision: activated ? 1 : 0, ...(!activated ? {next_revision: 1} : {})};
    throw Error("Unexpected operation");
  });
  const first = createSchemaModel({root: new Element("section"), client, storage});
  await first.open({kind: "new"});
  const inputs = first.element.querySelectorAll(".schema-model-input");
  inputs[0].value = "Libro"; inputs[1].value = "Libros que leo";
  first.element.querySelector(".schema-model-propose").click(); await flush();
  first.element.querySelector(".schema-model-confirm").click(); await flush();
  assert.equal(store.size, 1);
  const second = createSchemaModel({root: new Element("section"), client, storage});
  await second.open({kind: "new"});
  assert.match(second.element.textContent, /sigue activando/);
  assert.equal(second.element.querySelector(".schema-model-form").hidden, true);
  assert.equal(calls.filter((item) => item.operation === "schema_confirm").length, 1);
  activated = true;
  second.element.querySelector(".schema-model-retry").click(); await flush();
  assert.equal(store.size, 0);
  assert.match(second.element.textContent, /Cambio activo/);
});
