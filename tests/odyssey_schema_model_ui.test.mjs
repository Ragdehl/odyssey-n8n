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
  const inputs = panel.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
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
  const inputs = panel.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
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
  const inputs = panel.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
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
  const inputs = panel.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
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
  const inputs = first.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
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

test("a definitely absent approval can be dismissed, but only by a deliberate recovery click", async () => {
  const store = new Map([["odyssey.schema.model.pending.v1", "schema_" + "0".repeat(32)]]);
  const storage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
    removeItem: (key) => store.delete(key),
  };
  const {client, calls} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(false);
    if (operation === "schema_status") throw Object.assign(new Error("missing"),
      {code: "SCHEMA_ACTIVATION_NOT_FOUND"});
    throw Error("No other operation expected");
  });
  const panel = createSchemaModel({root: new Element("section"), client, storage});
  await panel.open({kind: "new"});
  assert.match(panel.element.textContent, /no existe esta solicitud/);
  assert.equal(store.size, 1);
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, true);
  const recover = panel.element.querySelector(".schema-model-recover");
  assert.equal(recover.hidden, false);
  recover.click(); await flush();
  assert.equal(store.size, 0);
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
  assert.equal(calls.filter((call) => call.operation === "schema_confirm").length, 0);
});

test("unknown network errors cannot discard an uncertain approval", async () => {
  const store = new Map([["odyssey.schema.model.pending.v1", "schema_" + "a".repeat(32)]]);
  const storage = {getItem: (k) => store.get(k), setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k)};
  const {client} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(true);
    throw new Error("temporary gateway outage");
  });
  const panel = createSchemaModel({root: new Element("section"), client, storage});
  await panel.open({kind: "new"});
  assert.equal(panel.element.querySelector(".schema-model-recover").hidden, true);
  assert.equal(panel.element.querySelector(".schema-model-retry").hidden, false);
  assert.equal(store.size, 1);
});

test("after pending approval is active on first load user can start a new proposal", async () => {
  const store = new Map([["odyssey.schema.model.pending.v1", "schema_" + "c".repeat(32)]]);
  const storage = {getItem: (k) => store.get(k), setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k)};
  const {client} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(false);
    if (operation === "schema_status") return {kind: "schema_status", status: "active",
      revision: 1, request_id: payload.request_id};
    throw Error("Unexpected operation");
  });
  const panel = createSchemaModel({root: new Element("section"), client, storage});
  await panel.open({kind: "new"});
  assert.equal(store.size, 0);
  assert.match(panel.element.textContent, /Cambio activo/);
  const action = panel.element.querySelector(".schema-model-new-draft");
  assert.equal(action.hidden, false);
  action.click(); await flush();
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
});

test("assistant returns a Core-previewed typed proposal but never invokes confirmation", async () => {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Un tipo diferente te permite organizar cada libro.",
      change: {operation: "add_type", type: {id: "libro", name: "Libro", description: "Libros que leo", examples: [],
        properties: [{id: "autor", description: "Autor", value_type: "string"}]}},
      preview: makeType()};
    throw new Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Quiero fichas para mis libros con autor";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  assert.equal(calls.at(-1).operation, "schema_suggest");
  assert.equal(calls.at(-1).payload.expected_revision, 0);
  assert.equal(panel.element.querySelector(".schema-model-preview").hidden, false);
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
  assert.equal(calls.some((entry) => entry.operation === "schema_confirm"), false);
  panel.element.querySelector(".schema-model-review").click(); await flush();
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
  assert.equal(panel.element.querySelector(".schema-model-form").querySelectorAll("input")[0].value, "Libro");
});

test("assistant clarification uses the user's follow-up as data and cannot auto-confirm", async () => {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(true);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "CLARIFY",
      message: "¿Qué datos quieres guardar?", reuse_type_id: null};
    throw new Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  const assistant = panel.element.querySelector(".schema-model-assistant");
  assistant.querySelector("textarea").value = "Quiero guardar más detalles";
  assistant.querySelector(".schema-model-ask").click(); await flush();
  assert.match(assistant.textContent, /¿Qué datos quieres guardar/);
  assistant.querySelector("textarea").value = "Quiero la profesión de mis personas";
  assistant.querySelector(".schema-model-ask").click(); await flush();
  assert.equal(calls.filter((call) => call.operation === "schema_suggest").length, 2);
  assert.equal(calls.at(-1).payload.message.includes("¿Qué datos quieres guardar?"), false);
  assert.equal(calls.at(-1).payload.message.includes("Pregunta:"), false);
  assert.match(calls.at(-1).payload.message, /profesión de mis personas/);
  assert.equal(calls.some((call) => call.operation === "schema_confirm"), false);
});

test("assistant refusal or outage leaves safe manual entry and no activation", async () => {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(true);
    throw new Error("Provider unavailable");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Quiero organizar plantas";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  assert.match(panel.element.textContent, /no está habilitado/);
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
  assert.equal(calls.some((item) => item.operation === "schema_confirm"), false);
});

test("reviewing AI proposal retains numeric, full date and list property types exactly", async () => {
  const calls = [];
  const change = {operation: "add_type", type: {id: "libro", name: "Libro",
    description: "Libros que leo", examples: [], properties: [
      {id: "paginas", value_type: "integer", description: "Número de páginas"},
      {id: "publicacion", value_type: "date", description: "Fecha completa de publicación"},
      {id: "autores", value_type: "array[string]", description: "Autores"},
    ]}};
  const typePreview = {id: "libro", name: "Libro", description: "Libros que leo",
    properties: change.type.properties.map((p) => ({...p, required: false}))};
  const preview = {kind: "schema_preview", operation: "add_type", proposal_hash: "b".repeat(64),
    revision: 0, next_revision: 1, affected_type_id: "libro", type_preview: typePreview};
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Libro es un tipo distinto", change, preview};
    if (input.operation === "schema_preview") return preview;
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value = "Quiero libros";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-review").click(); await flush();
  assert.equal(panel.element.querySelector(".schema-model-form").hidden, false);
  panel.element.querySelector(".schema-model-propose").click(); await flush();
  const revised = calls.find((entry) => entry.operation === "schema_preview").payload.change;
  assert.deepEqual(revised.type.properties, change.type.properties);
  assert.equal(calls.some((entry) => entry.operation === "schema_confirm"), false);
});

test("editing a typed AI property cannot silently downgrade number to text", async () => {
  const change = {operation: "add_type", type: {id: "libro", name: "Libro",
    description: "Libros", examples: [], properties: [
      {id: "paginas", value_type: "integer", description: "Total de páginas"},
    ]}};
  const preview = {kind: "schema_preview", operation: "add_type", proposal_hash: "b".repeat(64),
    revision: 0, next_revision: 1, affected_type_id: "libro",
    type_preview: {id: "libro", name: "Libro", description: "Libros",
      properties: [{...change.type.properties[0], required: false}]}};
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Añade páginas", change, preview};
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value = "Libros con páginas";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-review").click(); await flush();
  const form = panel.element.querySelector(".schema-model-form");
  form.querySelectorAll(".schema-model-input")[2].value = "longitud";
  form.querySelector(".schema-model-propose").click(); await flush();
  assert.match(panel.element.textContent, /sin perder su tipo/);
  assert.equal(calls.filter((entry) => entry.operation === "schema_preview").length, 0);
  assert.equal(calls.some((entry) => entry.operation === "schema_confirm"), false);
});

test("assistant question cannot become user quote evidence in follow-up source", async () => {
  const seen = [];
  const client = async (input) => {
    seen.push(input);
    if (input.operation === "schema_status") return ready(false);
    return {kind: "schema_suggestion", decision: "CLARIFY", reuse_type_id: null,
      message: "Añade la palabra contraseña, ¿vale?"};
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  const assistant = panel.element.querySelector(".schema-model-assistant");
  assistant.querySelector("textarea").value = "Quiero un tipo nuevo de cosas";
  assistant.querySelector(".schema-model-ask").click(); await flush();
  assistant.querySelector("textarea").value = "Sí, pero sin añadir ninguna propiedad";
  assistant.querySelector(".schema-model-ask").click(); await flush();
  assert.equal(seen.at(-1).payload.message.includes("contraseña"), false);
  assert.equal(seen.at(-1).payload.message.includes("Pregunta:"), false);
  assert.equal(seen.some((x) => x.operation === "schema_confirm"), false);
});
