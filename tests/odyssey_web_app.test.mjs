import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

import {
  ProductRequestError,
  findRecoverableSubmission,
} from "../odyssey_web/client.js";

let fixtureNumber = 0;

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.disabled = false;
    this.hidden = false;
    this.parentNode = null;
    this.scrollHeight = 100;
    this.scrollTop = 0;
    this._listeners = new Map();
    this._textContent = "";
    this.classList = {
      add: (...names) => {
        this.className = [...new Set([...this.className.split(" "), ...names])]
          .filter(Boolean)
          .join(" ");
      },
    };
  }

  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent).join("");
  }

  append(...nodes) {
    for (const node of nodes) {
      if (node.parentNode) node.remove();
      node.parentNode = this;
      this.children.push(node);
    }
  }

  prepend(...nodes) {
    for (const node of [...nodes].reverse()) {
      if (node.parentNode) node.remove();
      node.parentNode = this;
      this.children.unshift(node);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this.append(...nodes);
  }

  remove() {
    if (!this.parentNode) return;
    const index = this.parentNode.children.indexOf(this);
    if (index >= 0) this.parentNode.children.splice(index, 1);
    this.parentNode = null;
  }

  querySelector(selector) {
    for (const child of this.children) {
      if (matches(child, selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  addEventListener(type, listener) {
    this._listeners.set(type, listener);
  }

  click() {
    this._listeners.get("click")?.({preventDefault() {}});
  }

  emit(type, event = {}) {
    this._listeners.get(type)?.(event);
  }

  setAttribute(name, value) {
    this[name] = value;
  }

  focus() {}
  showModal() {}
}

class FakeDocument {
  constructor() {
    this.documentElement = new FakeElement("html");
    this._elements = new Map();
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }

  querySelector(selector) {
    return this._elements.get(selector) ?? null;
  }

  dispatchEvent() {}
}

function matches(element, selector) {
  if (selector.startsWith(".")) return element.className.split(" ").includes(selector.slice(1));
  return element.tagName === selector;
}

function createPage() {
  const document = new FakeDocument();
  const elements = {
    form: new FakeElement("form"),
    input: new FakeElement("textarea"),
    send: new FakeElement("button"),
    conversation: new FakeElement("section"),
    sheet: new FakeElement("dialog"),
    detailTitle: new FakeElement("h2"),
    detailContent: new FakeElement("div"),
    chat: new FakeElement("section"),
    notes: new FakeElement("section"),
    chatTab: new FakeElement("button"),
    notesTab: new FakeElement("button"),
    brand: new FakeElement("div"),
  };
  for (const [selector, element] of [
    ["#odyssey-form", elements.form],
    ["#request-input", elements.input],
    ["#send-button", elements.send],
    ["#interaction", elements.conversation],
    ["#request-detail-sheet", elements.sheet],
    ["#request-detail-title", elements.detailTitle],
    ["#request-detail-content", elements.detailContent],
    ["#chat-surface", elements.chat],
    ["#notes-surface", elements.notes],
    ["#chat-tab", elements.chatTab],
    ["#notes-tab", elements.notesTab],
    [".brand", elements.brand],
  ]) {
    document._elements.set(selector, element);
  }
  document._elements.set('meta[name="odyssey-api-endpoint"]', {content: "/api/request"});
  document._elements.set('meta[name="odyssey-conversation-endpoint"]', {content: "/api/conversation"});
  document._elements.set('meta[name="odyssey-notes-endpoint"]', {content: "/api/notes"});
  return {document, elements};
}

async function mountApp({turns, olderTurns = [], requestProductResult}) {
  const {document, elements} = createPage();
  const persisted = [];
  let renderedWithoutRecovery = false;
  globalThis.document = document;
  globalThis.ODYSSEY_DEPLOYMENT = undefined;
  globalThis.__odysseyTestClient = {
    ProductRequestError,
    createSubmission: () => {
      throw new Error("submission is not exercised in this fixture");
    },
    findRecoverableSubmission,
    requestProductResult,
    requestConversation: async ({operation, payload}) => {
      if (operation === "main" && payload.before) {
        return {conversation_id: "main", turns: olderTurns, has_older: false, before: null};
      }
      if (operation === "main") return {
        conversation_id: "main", turns, has_older: olderTurns.length > 0,
        before: olderTurns.length > 0 ? "older-page" : null,
      };
      persisted.push(payload);
      return {};
    },
    renderProductResultWithContinuity: async ({result, renderResult, persistAssistantTurn}) => {
      renderedWithoutRecovery = elements.conversation.querySelector(".recovery-control") === null;
      renderResult(result);
      await persistAssistantTurn();
    },
  };
  globalThis.__odysseyTestNotes = {mountNotes() {}};
  const source = await readFile(new URL("../odyssey_web/app.js", import.meta.url), "utf8");
  const testable = source
    .replace(/import \{[\s\S]*?\} from "\.\/client\.js";/, "const {ProductRequestError, createSubmission, findRecoverableSubmission, requestProductResult, requestConversation, renderProductResultWithContinuity} = globalThis.__odysseyTestClient;")
    .replace('import {mountNotes} from "./notes.js";', "const {mountNotes} = globalThis.__odysseyTestNotes;")
    .replace("void (async () => {", "globalThis.__odysseyAppReady = (async () => {");
  const fixtureSource = `${testable}\n// fixture ${fixtureNumber += 1}`;
  await import(`data:text/javascript;base64,${Buffer.from(fixtureSource).toString("base64")}`);
  await globalThis.__odysseyAppReady;
  return {elements, persisted, renderedWithoutRecovery: () => renderedWithoutRecovery};
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

test("reload mounts one recovery control on its unmatched user turn and removes it before recovery result", async () => {
  let resolveResult;
  let requests = 0;
  const page = await mountApp({
    turns: [{request_id: "web-recover", role: "user", text: "Guarda este recuerdo"}],
    requestProductResult: () => {
      requests += 1;
      return new Promise((resolve) => { resolveResult = resolve; });
    },
  });

  const userTurn = page.elements.conversation.children[0];
  const recovery = userTurn.querySelector(".recovery-control");
  const action = recovery.querySelector(".recovery-action");
  assert.equal(recovery.parentNode, userTurn);
  assert.equal(requests, 0);
  action.click();
  await flush();
  assert.equal(action.textContent, "Recuperando…");
  assert.equal(action.disabled, true);

  resolveResult({request_id: "web-recover", status: "completed", kind: "acknowledgement", message: "Guardado."});
  await flush();

  assert.equal(page.renderedWithoutRecovery(), true);
  assert.equal(page.elements.conversation.querySelector(".recovery-control"), null);
  assert.equal(userTurn.querySelector(".recovery-control"), null);
  assert.deepEqual(page.elements.conversation.children.map((node) => node.className), [
    "message message-user",
    "message message-odyssey",
  ]);
  assert.equal(page.elements.conversation.children[1].textContent.includes("Guardado."), true);
  assert.equal(page.persisted.length, 1);
  assert.equal(page.persisted[0].request_id, "web-recover");
});

test("retryable recovery failure restores its bounded action without a global error message", async () => {
  const page = await mountApp({
    turns: [{request_id: "web-recover", role: "user", text: "Guarda este recuerdo"}],
    requestProductResult: async () => {
      throw new ProductRequestError("network failed", true);
    },
  });

  const userTurn = page.elements.conversation.children[0];
  const recovery = userTurn.querySelector(".recovery-control");
  const action = recovery.querySelector(".recovery-action");
  action.click();
  await flush();

  assert.equal(recovery.parentNode, userTurn);
  assert.equal(recovery.dataset.state, "retryable");
  assert.equal(action.textContent, "Recuperar resultado");
  assert.equal(action.disabled, false);
  assert.equal(page.elements.conversation.children.length, 1);
});

test("conversation reload renders the exact durable affected-note affordance", async () => {
  const page = await mountApp({
    turns: [
      {request_id: "web-write", role: "user", text: "Guarda esto"},
      {request_id: "web-write", role: "assistant", text: "La información se ha guardado.",
        note_result_snapshot: {
          version: 2, kind: "affected_notes", executed_at: "2026-09-21T10:00:00Z",
          note_ids: ["first", "second"], total: 2, truncated: false,
        }},
    ],
    requestProductResult: async () => { throw new Error("not exercised"); },
  });

  const affordance = page.elements.conversation.children[1].querySelector(".note-set-button");
  assert.equal(affordance.textContent, "Ver 2 notas");
  assert.equal(page.elements.conversation.children[1].textContent.includes("first"), false);
});

test("older conversation pagination preserves an affected-note affordance", async () => {
  const page = await mountApp({
    turns: [{request_id: "web-current", role: "user", text: "Actual"}],
    olderTurns: [{request_id: "web-old", role: "assistant", text: "Guardado.", note_result_snapshot: {
      version: 2, kind: "affected_notes", executed_at: "2026-09-21T10:00:00Z",
      note_ids: ["only"], total: 1, truncated: false,
    }}],
    requestProductResult: async () => { throw new Error("not exercised"); },
  });

  page.elements.conversation.scrollTop = 0;
  page.elements.conversation.emit("scroll");
  await flush();

  const affordance = page.elements.conversation.children[0].querySelector(".note-set-button");
  assert.equal(affordance.textContent, "Ver nota");
});
