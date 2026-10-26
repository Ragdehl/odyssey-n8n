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
  assert.equal(store.size, 2); // pending request + actor-checked scan target
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

test("renaming a typed AI property preserves its explicitly selected numeric type", async () => {
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
    if (input.operation === "schema_preview") return preview;
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value = "Libros con páginas";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-review").click(); await flush();
  const form = panel.element.querySelector(".schema-model-form");
  form.querySelector(".schema-model-property-row").querySelector(".schema-model-input").value = "longitud";
  form.querySelector(".schema-model-propose").click(); await flush();
  const edited = calls.find((entry) => entry.operation === "schema_preview").payload.change;
  assert.deepEqual(edited.type.properties, [{id: "longitud", value_type: "integer",
    description: "Total de páginas"}]);
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

test("removing an unwanted typed property from AI draft is allowed without silently rewriting survivors", async () => {
  const proposed = {operation: "add_type", type: {id: "libro", name: "Libro",
    description: "Libros", examples: [], properties: [
      {id: "paginas", value_type: "integer", description: "Número de páginas"},
      {id: "titulo", value_type: "string", description: "Título original"},
      {id: "autores", value_type: "array[string]", description: "Lista de autores"},
    ]}};
  const preview = {kind: "schema_preview", operation: "add_type", revision: 0,
    next_revision: 1, proposal_hash: "d".repeat(64), affected_type_id: "libro",
    type_preview: {id: "libro", name: "Libro", description: "Libros",
      properties: proposed.type.properties.map((property) => ({...property, required: false}))}};
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Organiza libros", change: proposed, preview};
    if (input.operation === "schema_preview") return preview;
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value = "Libros";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-review").click(); await flush();
  const form = panel.element.querySelector(".schema-model-form");
  form.querySelectorAll(".schema-model-property-remove")[0].click();
  form.querySelector(".schema-model-propose").click(); await flush();
  const updated = calls.find((item) => item.operation === "schema_preview").payload.change;
  assert.deepEqual(updated.type.properties, [proposed.type.properties[1], proposed.type.properties[2]]);
  assert.equal(calls.some((item) => item.operation === "schema_confirm"), false);
});

test("type preview explicitly discloses that description cannot enforce exclusions", async () => {
  const calls = [];
  const client = async (input) => {
    calls.push(input);
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "La descripción excluirá todas las notas de oficina automáticamente.",
      change: {operation: "add_type", type: {id: "planta", name: "Planta",
        description: "Solo las plantas personales", examples: [], properties: []}},
      preview: {kind: "schema_preview", operation: "add_type", revision: 0,
        next_revision: 1, proposal_hash: "e".repeat(64), affected_type_id: "planta",
        type_preview: {id: "planta", name: "Planta", description: "Solo las plantas personales",
          properties: []}}};
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Solo plantas personales";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  assert.match(panel.element.querySelector(".schema-model-impact").textContent, /no aplica exclusiones automáticas/);
  assert.match(panel.element.querySelector(".schema-model-impact").textContent, /ni filtra menciones antiguas/);
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
  assert.equal(calls.some((item) => item.operation === "schema_confirm"), false);
});

test("property preview discloses whole-type impact, never a selective subset", async () => {
  const client = async (input) => {
    if (input.operation === "schema_status") return ready(false);
    if (input.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Añade ISBN al tipo Documento.",
      change: {operation: "add_property", type_id: "document", property: {
        id: "isbn", value_type: "string", description: "ISBN"}},
      preview: {kind: "schema_preview", operation: "add_property", revision: 0,
        next_revision: 1, proposal_hash: "a".repeat(64), affected_type_id: "document",
        type_preview: {id: "document", name: "Documento", description: "Un documento",
          properties: [{id: "isbn", value_type: "string", description: "ISBN", required: false}]}}};
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Quiero ISBN de mis libros guardados";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  const note = panel.element.querySelector(".schema-model-impact").textContent;
  assert.match(note, /todas las notas de tipo «Documento»/);
  assert.match(note, /no solo a los ejemplos mencionados/);
  assert.match(note, /exactamente el adecuado/);
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
});

test("human can edit every proposed property, add and remove rows, then Core reviews edited structure", async () => {
  const draft = {operation: "add_type", type: {id: "juego", name: "Juego", description: "Mis juegos",
    examples: [], properties: [
      {id: "jugadores", description: "Número de jugadores", value_type: "string"},
      {id: "autor", description: "Autor", value_type: "string"},
    ]}};
  const original = {kind: "schema_preview", operation: "add_type", revision: 0, next_revision: 1,
    affected_type_id: "juego", proposal_hash: "a".repeat(64), type_preview: {
      id: "juego", name: "Juego", description: "Mis juegos", properties: draft.type.properties.map(
        (property) => ({...property, required: false}))}};
  const calls = [];
  const client = async (req) => {
    calls.push(req);
    if (req.operation === "schema_status") return ready(false);
    if (req.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Propongo Juego", change: draft, preview: original};
    if (req.operation === "schema_preview") return {...original, proposal_hash: "b".repeat(64)};
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Quiero juegos con número de jugadores";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-review").click(); await flush();
  const form = panel.element.querySelector(".schema-model-form");
  form.querySelectorAll(".schema-model-input")[0].value = "Juego de mesa";
  form.querySelectorAll(".schema-model-input")[1].value = "Juegos que tengo";
  const rows = form.querySelectorAll(".schema-model-property-row");
  rows[0].querySelectorAll(".schema-model-input")[0].value = "Número de jugadores";
  rows[0].querySelectorAll(".schema-model-input")[1].value = "Cantidad de jugadores";
  rows[0].querySelector(".schema-model-property-type").value = "integer";
  rows[1].querySelector(".schema-model-property-remove").click();
  form.querySelector(".schema-model-property-add").click();
  const added = form.querySelectorAll(".schema-model-property-row").at(-1);
  added.querySelectorAll(".schema-model-input")[0].value = "Edad recomendada";
  added.querySelectorAll(".schema-model-input")[1].value = "Edad mínima en años";
  added.querySelector(".schema-model-property-type").value = "integer";
  form.querySelector(".schema-model-propose").click(); await flush();
  const edited = calls.find((req) => req.operation === "schema_preview").payload.change;
  assert.equal(edited.type.name, "Juego de mesa");
  assert.equal(edited.type.description, "Juegos que tengo");
  assert.deepEqual(edited.type.properties, [
    {id: "numero_de_jugadores", description: "Cantidad de jugadores", value_type: "integer"},
    {id: "edad_recomendada", description: "Edad mínima en años", value_type: "integer"},
  ]);
  assert.equal(calls.filter((req) => req.operation === "schema_suggest").length, 1);
  assert.equal(calls.some((req) => req.operation === "schema_confirm"), false);
});

test("final AI review is advisory but required for an AI-origin proposal, and bound to exact hash", async () => {
  const draft = {operation: "add_type", type: {id: "libro", name: "Libro", description: "Mis libros",
    examples: [], properties: []}};
  const preview = {kind: "schema_preview", operation: "add_type", revision: 0, next_revision: 1,
    affected_type_id: "libro", proposal_hash: "c".repeat(64),
    type_preview: {id: "libro", name: "Libro", description: "Mis libros", properties: []}};
  const calls = [];
  const client = async (req) => {
    calls.push(req);
    if (req.operation === "schema_status") return ready(true);
    if (req.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Fichas de libros", change: draft, preview};
    if (req.operation === "schema_review") return {kind: "schema_review",
      proposal_hash: req.payload.proposal_hash, verdict: "CHECK",
      message: "Revisa antes de aprobar.", issues: ["No hay filtro automático de libros laborales."]};
    if (req.operation === "schema_confirm") return {kind: "schema_confirm", status: "queued",
      request_id: req.payload.request_id, revision: 0, next_revision: 1};
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value =
    "Quiero organizar mis libros";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  const confirm = panel.element.querySelector(".schema-model-confirm");
  assert.equal(confirm.disabled, true);
  confirm.click(); await flush();
  assert.equal(calls.filter((r) => r.operation === "schema_confirm").length, 0);
  panel.element.querySelector(".schema-model-ai-review").click(); await flush();
  const review = calls.find((r) => r.operation === "schema_review");
  assert.equal(review.payload.message, "Quiero organizar mis libros");
  assert.equal(review.payload.proposal_hash, preview.proposal_hash);
  assert.deepEqual(review.payload.change, draft);
  assert.match(panel.element.textContent, /No hay filtro automático/);
  assert.equal(confirm.disabled, false);
  confirm.click(); await flush();
  assert.equal(calls.filter((r) => r.operation === "schema_confirm").length, 1);
});

test("a stale or mismatched final review cannot enable human confirmation", async () => {
  const draft = {operation: "add_type", type: {id: "libro", name: "Libro", description: "Mis libros",
    examples: [], properties: []}};
  const preview = {kind: "schema_preview", operation: "add_type", revision: 0, next_revision: 1,
    affected_type_id: "libro", proposal_hash: "d".repeat(64),
    type_preview: {id: "libro", name: "Libro", description: "Mis libros", properties: []}};
  let release;
  const client = async (req) => {
    if (req.operation === "schema_status") return ready(true);
    if (req.operation === "schema_suggest") return {kind: "schema_suggestion", decision: "PROPOSE",
      message: "Fichas", change: draft, preview};
    if (req.operation === "schema_review") return new Promise((resolve) => {release = resolve;});
    throw Error("Unexpected operation");
  };
  const panel = createSchemaModel({root: new Element("section"), client});
  await panel.open({kind: "new"});
  panel.element.querySelector(".schema-model-assistant").querySelector("textarea").value = "Libros";
  panel.element.querySelector(".schema-model-ask").click(); await flush();
  panel.element.querySelector(".schema-model-ai-review").click(); await flush();
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
  release({kind: "schema_review", proposal_hash: "f".repeat(64), verdict: "READY",
    message: "Todo correcto", issues: []}); await flush();
  assert.equal(panel.element.querySelector(".schema-model-confirm").disabled, true);
  assert.equal(panel.element.querySelector(".schema-model-final-review").textContent.includes("Todo correcto"), false);
});

test("activated user property starts read-only scan without another click", async () => {
  const {client,calls} = makeClient(({operation, payload}) => {
    if (operation === "schema_status" && !payload) return ready(true);
    if (operation === "schema_status") return {kind:"schema_status",status:"active",
      request_id:payload.request_id, revision:1};
    if (operation === "schema_preview") return {
      ...makeType("Persona"),operation:"add_property",affected_type_id:"person",
      type_preview:{id:"person", name:"Persona",description:"Persona",
        properties:[{id:"oficio",description:"Profesión",value_type:"string",required:false}]},
    };
    if (operation === "schema_confirm") return {kind:"schema_confirm",status:"queued",
      request_id:payload.request_id,revision:0,next_revision:1};
    if (operation === "schema_scan") return payload.action === "status"
      ? {kind:"schema_scan", status:"not_started"}
      : {kind:"schema_scan", status:"complete",scanned_paths:3,
        eligible_notes:2,skipped_existing_values:0,legacy_sources:0};
    throw Error("unexpected action "+operation);
  });
  const model = createSchemaModel({root:new Element("section"),client});
  await model.open({kind:"add-property", type:{id:"person",name:"Persona"}});
  await flush();
  assert.equal(model.element.querySelector(".schema-model-scan").hidden,false);
  const fields = model.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
  fields[0].value = "Oficio"; fields[1].value = "Profesión";
  fields[2].value = "string";
  model.element.querySelector(".schema-model-propose").click();
  await flush();
  model.element.querySelector(".schema-model-confirm").click();
  await flush();
  model.element.querySelector(".schema-model-retry").click();
  await flush();
  const latest = calls.filter(x=>x.operation==="schema_scan");
  assert.equal(latest.at(-1).payload.scan_kind,"backfill_property");
  assert.equal(latest.at(-1).payload.property_id,"oficio");
  assert.equal(latest.at(-1).payload.expected_revision,1);
  assert.deepEqual(latest.map(x=>x.payload.action).slice(-2),["status","advance"]);
  assert.equal(model.element.querySelector(".schema-model-scan-advance").hidden,true);
});

test("queued approval hides the previous-type scan and polls original request to auto-enrich", async () => {
  const timers = [];
  let polls = 0;
  const backfill = (status, updated = 0, pending = 0, deferred = 0) => ({
    kind:"schema_backfill", status, total:updated+pending+deferred,
    pending, interpreting:0, writing:0, updated, no_evidence:0,
    ambiguous:0, stale:0, already_present:0, deferred,
  });
  const {client, calls} = makeClient(({operation,payload}) => {
    if (operation==="schema_status" && !payload) return ready(true);
    if (operation==="schema_preview") return {
      ...makeType("Persona"),operation:"add_property",affected_type_id:"person",
      type_preview:{id:"person",name:"Persona",description:"Persona",
        properties:[{id:"profesion",description:"Profesión",value_type:"string",required:false}]},
    };
    if (operation==="schema_confirm") return {kind:"schema_confirm",status:"queued",
      request_id:payload.request_id,revision:0,next_revision:1};
    if (operation==="schema_status") {
      polls++;
      return polls===1
        ? {kind:"schema_status",status:"queued",request_id:payload.request_id,revision:0,next_revision:1}
        : {kind:"schema_status",status:"active",request_id:payload.request_id,revision:1};
    }
    if (operation==="schema_scan") return payload.action==="status"
      ? {kind:"schema_scan",status:"not_started"}
      : {kind:"schema_scan",status:"complete",scanned_paths:3,eligible_notes:1,
        skipped_existing_values:0,legacy_sources:0};
    if (operation==="schema_backfill") {
      if (payload.action==="status") return {kind:"schema_backfill",status:"not_started"};
      if (payload.action==="stage") return backfill("in_progress",0,1);
      return backfill("awaiting_ai",0,0,1);
    }
    throw new Error("unexpected operation "+operation);
  });
  const store = new Map();
  const storage = {getItem:key=>store.get(key)??null,
    setItem:(key,value)=>store.set(key,value),removeItem:key=>store.delete(key)};
  const panel=createSchemaModel({root:new Element("section"),client,storage,
    schedule:(fn,ms)=>{assert.equal(ms,3000);timers.push(fn);}});
  await panel.open({kind:"add-property",type:{id:"person",name:"Persona"}});
  await flush();
  assert.equal(panel.element.querySelector(".schema-model-scan").hidden,false);
  const inputs=panel.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
  inputs[0].value="Profesión";inputs[1].value="Profesión";inputs[2].value="string";
  panel.element.querySelector(".schema-model-propose").click();await flush();
  panel.element.querySelector(".schema-model-confirm").click();await flush();
  assert.equal(panel.element.querySelector(".schema-model-scan").hidden,true,
    "Old discover-type panel must not impersonate new-model activation");
  assert.equal(calls.some(c=>c.operation==="schema_scan" &&
    c.payload?.scan_kind==="backfill_property"),false);
  assert.equal(timers.length,1,"First status poll is scheduled without a second approval");
  timers.shift()();await flush();
  assert.equal(timers.length,1,"Queued activation must retry status, not schema_confirm");
  assert.equal(calls.filter(c=>c.operation==="schema_confirm").length,1);
  assert.equal(panel.element.querySelector(".schema-model-scan").hidden,true);
  timers.shift()();
  for(let i=0;i<40;i++) await Promise.resolve();
  const scanCalls=calls.filter(c=>c.operation==="schema_scan"&&
    c.payload.scan_kind==="backfill_property");
  assert.deepEqual(scanCalls.map(c=>c.payload.action),["status","advance"]);
  assert.equal(scanCalls[0].payload.property_id,"profesion");
  assert.deepEqual(calls.filter(c=>c.operation==="schema_backfill").map(c=>c.payload.action),
    ["status","stage","advance"]);
  assert.match(panel.element.querySelector(".schema-model-enrichment-status").textContent,
    /1 pendientes de IA/);
  assert.equal(panel.element.querySelector(".schema-model-scan").hidden,false);
  assert.equal(calls.filter(c=>c.operation==="schema_confirm").length,1);
  assert.equal(store.size,0,"A confirmed, actor-scoped activation clears local pending state");
});

test("recovering a pending approval after reload retains its bounded backfill target", async()=>{
  const store=new Map();
  const storage={getItem:key=>store.get(key)??null,
    setItem:(key,value)=>store.set(key,value),removeItem:key=>store.delete(key)};
  const calls=[];
  let phase="queued";
  const client=async ({operation,payload})=>{
    calls.push({operation,payload});
    if(operation==="schema_status"&&!payload)return ready(true);
    if(operation==="schema_preview")return {
      ...makeType("Persona"),operation:"add_property",affected_type_id:"person",
      type_preview:{id:"person",name:"Persona",description:"Persona",
        properties:[{id:"idioma",description:"Idioma",value_type:"string",required:false}]},
    };
    if(operation==="schema_confirm")return {
      kind:"schema_confirm",status:"queued",request_id:payload.request_id,revision:0,next_revision:1};
    if(operation==="schema_status")return phase==="queued"
      ? {kind:"schema_status",status:"queued",request_id:payload.request_id,revision:0,next_revision:1}
      : {kind:"schema_status",status:"active",request_id:payload.request_id,revision:1};
    if(operation==="schema_scan")return {kind:"schema_scan",status:"complete",
      scanned_paths:1,eligible_notes:1,skipped_existing_values:0,legacy_sources:0};
    if(operation==="schema_backfill")return {
      kind:"schema_backfill",status:"awaiting_ai",total:1,pending:0,interpreting:0,
      writing:0,updated:0,no_evidence:0,ambiguous:0,stale:0,already_present:0,deferred:1};
    throw Error("Unexpected "+operation);
  };
  const inert=()=>{};
  const before=createSchemaModel({root:new Element("section"),client,storage,schedule:inert});
  await before.open({kind:"add-property",type:{id:"person",name:"Persona"}});
  const inputs=before.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
  inputs[0].value="Idioma";inputs[1].value="Idioma";inputs[2].value="string";
  before.element.querySelector(".schema-model-propose").click();await flush();
  before.element.querySelector(".schema-model-confirm").click();await flush();
  assert.equal(store.size,2);
  before.close();
  phase="active";
  const reopened=createSchemaModel({root:new Element("section"),client,storage,schedule:inert});
  await reopened.open({kind:"add-property",type:{id:"person",name:"Persona"}});
  for(let i=0;i<30;i++)await Promise.resolve();
  assert.equal(store.size,0);
  assert.equal(calls.filter(c=>c.operation==="schema_confirm").length,1);
  const scan=calls.findLast(c=>c.operation==="schema_scan"&&
    c.payload.scan_kind==="backfill_property");
  assert.deepEqual(scan.payload,{scan_kind:"backfill_property",target_type_id:"person",
    property_id:"idioma",expected_revision:1,action:"status"});
  assert.ok(calls.some(c=>c.operation==="schema_backfill"),"Resume pending property processing");
});

test("automatic activation checks stop on close and never repeat confirmation", async()=>{
  const queue=[];
  const calls=[];
  const client=async({operation,payload})=>{
    calls.push({operation,payload});
    if(operation==="schema_status"&&!payload)return ready(true);
    if(operation==="schema_preview")return makeType();
    if(operation==="schema_confirm")return {
      kind:"schema_confirm",status:"queued",request_id:payload.request_id,
      revision:0,next_revision:1,
    };
    if(operation==="schema_status")return {
      kind:"schema_status",status:"queued",request_id:payload.request_id,
      revision:0,next_revision:1,
    };
    throw new Error("unexpected "+operation);
  };
  const model=createSchemaModel({root:new Element("section"),client,
    schedule:(fn)=>queue.push(fn)});
  await model.open({kind:"new"});
  const inputs=model.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
  inputs[0].value="Libro";inputs[1].value="Libros";
  model.element.querySelector(".schema-model-propose").click();await flush();
  model.element.querySelector(".schema-model-confirm").click();await flush();
  assert.equal(queue.length,1);
  for(let index=0;index<3;index++){
    queue.shift()();await flush();
    assert.equal(queue.length,1);
  }
  model.close();
  queue.shift()();await flush();
  assert.equal(queue.length,0);
  assert.equal(calls.filter(x=>x.operation==="schema_confirm").length,1);
  assert.equal(calls.filter(x=>x.operation==="schema_status"&&x.payload).length,3);
});

test("corrupt stored scan target cannot turn a legitimate status into arbitrary enrichment", async()=>{
  const id="schema_"+"a".repeat(32);
  const storageData=new Map([
    ["odyssey.schema.model.pending.v1",id],
    ["odyssey.schema.model.pending-scan.v1",JSON.stringify({
      scanKind:"backfill_property",typeId:"person",propertyId:"../../other",
      revision:1,requestId:id,
    })],
  ]);
  const storage={getItem:k=>storageData.get(k)??null,
    removeItem:k=>storageData.delete(k),setItem:(k,v)=>storageData.set(k,v)};
  const calls=[];
  const client=async ({operation,payload})=>{
    calls.push({operation,payload});
    if(operation==="schema_status"&&!payload)return ready(true);
    if(operation==="schema_status")return {
      kind:"schema_status",status:"active",request_id:payload.request_id,revision:1};
    throw new Error("Forbidden scan");
  };
  const model=createSchemaModel({root:new Element("section"),client,storage});
  await model.open({kind:"new"});await flush();
  assert.equal(calls.filter(x=>x.operation==="schema_scan").length,0);
  assert.equal(calls.filter(x=>x.operation==="schema_backfill").length,0);
  assert.equal(storageData.size,0);
});

test("cold DEV boot beyond 24 status checks still auto-activates without duplicate approval", async()=>{
  const timers=[];
  const calls=[];
  let checks=0;
  const client=async ({operation,payload})=>{
    calls.push({operation,payload});
    if(operation==="schema_status"&&!payload)return ready(true);
    if(operation==="schema_preview")return {
      ...makeType("Persona"),operation:"add_property",affected_type_id:"person",
      type_preview:{id:"person",name:"Persona",description:"Persona",
        properties:[{id:"profesion",description:"Profesión",value_type:"string",required:false}]},
    };
    if(operation==="schema_confirm")return {kind:"schema_confirm",status:"queued",
      request_id:payload.request_id,revision:0,next_revision:1};
    if(operation==="schema_status"){
      checks++;
      // 45 polls take > 2 minutes at one poll per 3 seconds. Some failures
      // represent the runtime restart; others are legitimate queued receipts.
      if(checks>=11&&checks<=30)throw Error("DEV runtime booting");
      return checks<46
        ? {kind:"schema_status",status:"queued",request_id:payload.request_id,
          revision:0,next_revision:1}
        : {kind:"schema_status",status:"active",request_id:payload.request_id,revision:1};
    }
    if(operation==="schema_scan")return payload.action==="status"
      ? {kind:"schema_scan",status:"not_started"}
      : {kind:"schema_scan",status:"complete",scanned_paths:1,
        eligible_notes:1,skipped_existing_values:0,legacy_sources:0};
    if(operation==="schema_backfill")return {
      kind:"schema_backfill",status:"awaiting_ai",total:1,pending:0,
      interpreting:0,writing:0,updated:0,no_evidence:0,
      ambiguous:0,stale:0,already_present:0,deferred:1,
    };
    throw Error("Unexpected operation "+operation);
  };
  const model=createSchemaModel({root:new Element("section"),client,
    schedule:(fn,ms)=>{assert.equal(ms,3000);timers.push(fn);}});
  await model.open({kind:"add-property",type:{id:"person",name:"Persona"}});
  const inputs=model.element.querySelector(".schema-model-form").querySelectorAll(".schema-model-input");
  inputs[0].value="Profesión";inputs[1].value="Profesión actual";
  inputs[2].value="string";
  model.element.querySelector(".schema-model-propose").click();await flush();
  model.element.querySelector(".schema-model-confirm").click();await flush();
  for(let n=0;n<46;n++){
    assert.equal(timers.length,1,"Polling remains scheduled while visible");
    timers.shift()();
    for(let j=0;j<16;j++)await Promise.resolve();
  }
  for(let i=0;i<40;i++)await Promise.resolve();
  assert.equal(checks,46);
  assert.equal(calls.filter(x=>x.operation==="schema_confirm").length,1);
  assert.ok(calls.some(x=>x.operation==="schema_scan"&&x.payload.action==="advance"));
  assert.ok(calls.some(x=>x.operation==="schema_backfill"));
  assert.equal(model.element.querySelector(".schema-model-retry").hidden,true);
  assert.equal(timers.length,0);
});
