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
    this._listeners = new Map();
    this.events = [];
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }

  querySelector(selector) {
    return this._elements.get(selector) ?? null;
  }

  addEventListener(type, listener) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(listener);
  }

  dispatchEvent(event) {
    this.events.push(event);
    for (const listener of this._listeners.get(event.type) ?? []) listener(event);
    return true;
  }
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
    calendar: new FakeElement("section"),
    chatHomeTab: new FakeElement("button"),
    chatTab: new FakeElement("button"),
    notesTab: new FakeElement("button"),
    notesHomeTab: new FakeElement("button"),
    calendarTab: new FakeElement("button"),
    calendarHomeTab: new FakeElement("button"),
    notesCalendarTab: new FakeElement("button"),
    calendarChatTab: new FakeElement("button"),
    calendarNotesTab: new FakeElement("button"),
    brand: new FakeElement("div"),
    clarificationStatus: new FakeElement("p"),
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
    ["#calendar-surface", elements.calendar],
    ["#chat-home-tab", elements.chatHomeTab],
    ["#chat-tab", elements.chatTab],
    ["#notes-tab", elements.notesTab],
    ["#notes-home-tab", elements.notesHomeTab],
    ["#calendar-tab", elements.calendarTab],
    ["#calendar-home-tab", elements.calendarHomeTab],
    ["#notes-calendar-tab", elements.notesCalendarTab],
    ["#calendar-chat-tab", elements.calendarChatTab],
    ["#calendar-notes-tab", elements.calendarNotesTab],
    [".brand", elements.brand],
    ["#clarification-status", elements.clarificationStatus],
  ]) {
    document._elements.set(selector, element);
  }
  document._elements.set('meta[name="odyssey-api-endpoint"]', {content: "/api/request"});
  document._elements.set('meta[name="odyssey-conversation-endpoint"]', {content: "/api/conversation"});
  document._elements.set('meta[name="odyssey-notes-endpoint"]', {content: "/api/notes"});
  document._elements.set('meta[name="odyssey-calendar-endpoint"]', {content: "/api/calendar"});
  return {document, elements};
}

async function mountApp({turns, olderTurns = [], requestProductResult, createSubmission}) {
  const {document, elements} = createPage();
  const persisted = [];
  let renderedWithoutRecovery = false;
  let notesHomeCalls = 0;
  let calendarHomeCalls = 0;
  globalThis.document = document;
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
  };
  globalThis.ODYSSEY_DEPLOYMENT = undefined;
  globalThis.__odysseyTestClient = {
    ProductRequestError,
    createSubmission: createSubmission ?? (() => {
      throw new Error("submission is not exercised in this fixture");
    }),
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
  globalThis.__odysseyTestIcons = {
    setActionIcon(control, _name, label) {
      const svg = new FakeElement("svg");
      control.replaceChildren(svg);
      control.setAttribute("aria-label", label);
      control.setAttribute("title", label);
      return control;
    },
    actionButton(_name, label, action, classes = "") {
      const control = new FakeElement("button");
      control.className = `icon-action ${classes}`.trim();
      control.setAttribute("aria-label", label);
      control.setAttribute("title", label);
      control.append(new FakeElement("svg"));
      control.addEventListener("click", action);
      return control;
    },
  };
  globalThis.__odysseyTestNotes = {...globalThis.__odysseyTestIcons, mountNotes() { return {showList() { notesHomeCalls += 1; }}; }};
  globalThis.__odysseyTestCalendar = {mountCalendar() { return {showMonth() { calendarHomeCalls += 1; }}; }};
  const source = await readFile(new URL("../odyssey_web/app.js", import.meta.url), "utf8");
  const testable = source
    .replace(/import \{[\s\S]*?\} from "\.\/client\.js";/, "const {ProductRequestError, createSubmission, findRecoverableSubmission, requestProductResult, requestConversation, renderProductResultWithContinuity} = globalThis.__odysseyTestClient;")
    .replace('import {actionButton, mountNotes, setActionIcon} from "./notes.js";', "const {actionButton, mountNotes, setActionIcon} = globalThis.__odysseyTestNotes;")
    .replace('import {mountCalendar} from "./calendar.js";', "const {mountCalendar} = globalThis.__odysseyTestCalendar;")
    .replace("void (async () => {", "globalThis.__odysseyAppReady = (async () => {");
  const fixtureSource = `${testable}\n// fixture ${fixtureNumber += 1}`;
  await import(`data:text/javascript;base64,${Buffer.from(fixtureSource).toString("base64")}`);
  await globalThis.__odysseyAppReady;
  return {
    document, elements, persisted,
    renderedWithoutRecovery: () => renderedWithoutRecovery,
    notesHomeCalls: () => notesHomeCalls,
    calendarHomeCalls: () => calendarHomeCalls,
  };
}

function conversationMessages(conversation) {
  return conversation.children.filter((child) => child.className.split(" ").includes("message"));
}

function conversationDates(conversation) {
  return conversation.children.filter((child) => child.className === "conversation-date");
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

  const userTurn = conversationMessages(page.elements.conversation)[0];
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
  assert.deepEqual(conversationMessages(page.elements.conversation).map((node) => node.className), [
    "message message-user",
    "message message-odyssey",
  ]);
  assert.equal(conversationMessages(page.elements.conversation)[1].textContent.includes("Guardado."), true);
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

  const userTurn = conversationMessages(page.elements.conversation)[0];
  const recovery = userTurn.querySelector(".recovery-control");
  const action = recovery.querySelector(".recovery-action");
  action.click();
  await flush();

  assert.equal(recovery.parentNode, userTurn);
  assert.equal(recovery.dataset.state, "retryable");
  assert.equal(action.textContent, "Recuperar resultado");
  assert.equal(action.disabled, false);
  assert.equal(conversationMessages(page.elements.conversation).length, 1);
});

test("clarification renders grounded controls while leaving the composer usable", async () => {
  let resolveResult;
  const submissions = [];
  const page = await mountApp({
    turns: [{request_id: "web-rich", role: "user", text: "Guarda esto"}],
    createSubmission: (request) => ({request, requestId: `choice-${request}`}),
    requestProductResult: ({submission}) => {
      submissions.push(submission.request);
      return new Promise((resolve) => { resolveResult = resolve; });
    },
  });
  page.elements.conversation.querySelector(".recovery-action").click();
  await flush();
  resolveResult({
    request_id: "web-rich", status: "needs_attention", kind: "clarification",
    message: "Aclara la identidad.", clarification: {
      request_id: "web-rich", requested_reference: "mi hijo mayor",
      explanation: "No puedo identificar con seguridad a “mi hijo mayor”. He encontrado estas posibilidades en tus notas.",
      options: [
        {id: "cloe", label: "Cloe", note_type: "person", evidence: "Mis hijos son Cloe y Bruno."},
        {id: "bruno", label: "Bruno", note_type: "person", evidence: "Mis hijos son Cloe y Bruno."},
      ],
    },
  });
  await flush();

  const card = page.elements.conversation.querySelector(".message-clarification");
  assert.equal(card.querySelector(".clarification-options").children.length, 2);
  assert.equal(page.elements.clarificationStatus.hidden, false);
  assert.equal(page.elements.input.disabled, false);
  card.querySelector(".clarification-option").querySelector("button").click();
  assert.deepEqual(submissions, ["Guarda esto", "He elegido a Cloe."]);
  const visibleChoice = page.elements.conversation.children.at(-2);
  assert.equal(visibleChoice.querySelector(".message-text").textContent, "He elegido a Cloe.");
  const inspect = card.querySelector(".clarification-option").querySelector(".clarification-controls").children[1];
  inspect.click();
  assert.equal(page.elements.notes.hidden, false);
  assert.equal(page.document.events.at(-1).detail.note_id, "cloe");
  card.querySelector(".clarification-cancel").click();
  assert.deepEqual(submissions, ["Guarda esto", "He elegido a Cloe.", "cancel"]);
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

  const affordance = conversationMessages(page.elements.conversation)[1].querySelector(".note-set-button");
  assert.equal(affordance["aria-label"], "Ver 2 notas");
  assert.equal(affordance.querySelector(".note-set-count").textContent, "2");
  assert.equal(conversationMessages(page.elements.conversation)[1].textContent.includes("first"), false);
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

  const affordance = conversationMessages(page.elements.conversation)[0].querySelector(".note-set-button");
  assert.equal(affordance["aria-label"], "Ver nota");
  assert.equal(affordance.querySelector(".note-set-count"), null);
});

test("chat groups messages by local day, shows compact times, omits sender labels, and uses an icon send control", async () => {
  const atLocalTime = (daysAgo, hour, minute) => {
    const value = new Date();
    value.setDate(value.getDate() - daysAgo);
    value.setHours(hour, minute, 0, 0);
    return value.toISOString();
  };
  const old = atLocalTime(20, 9, 5);
  const weekday = atLocalTime(3, 10, 10);
  const yesterday = atLocalTime(1, 11, 20);
  const today = atLocalTime(0, 14, 45);
  const expectedWeekday = new Intl.DateTimeFormat("es-ES", {weekday: "long"}).format(new Date(weekday));
  const expectedOld = new Intl.DateTimeFormat("es-ES", {day: "numeric", month: "long", year: "numeric"}).format(new Date(old));

  const page = await mountApp({
    turns: [
      {request_id: "old", role: "user", text: "Antiguo", created_at: old},
      {request_id: "week", role: "assistant", text: "Semana", created_at: weekday},
      {request_id: "y1", role: "user", text: "Ayer uno", created_at: yesterday},
      {request_id: "y2", role: "assistant", text: "Ayer dos", created_at: yesterday},
      {request_id: "today", role: "user", text: "Hoy", created_at: today},
    ],
    requestProductResult: async () => { throw new Error("not exercised"); },
  });

  const dates = conversationDates(page.elements.conversation);
  assert.deepEqual(dates.map((item) => item.textContent), [
    expectedOld,
    expectedWeekday.charAt(0).toUpperCase() + expectedWeekday.slice(1),
    "Ayer",
    "Hoy",
  ]);
  const messages = conversationMessages(page.elements.conversation);
  assert.equal(messages.length, 5);
  assert.equal(messages.every((message) => message.querySelector(".eyebrow") === null), true);
  assert.equal(messages.at(-1).querySelector(".message-time").textContent, "14:45");
  assert.equal(page.elements.send.textContent, "");
  assert.equal(page.elements.send["aria-label"], "Enviar");
  assert.notEqual(page.elements.send.querySelector("svg"), null);
});

test("fixed app icons keep one navigation order and reset Notes/Calendar to their home surfaces", async () => {
  const page = await mountApp({
    turns: [],
    requestProductResult: async () => { throw new Error("not exercised"); },
  });

  page.elements.calendarTab.click();
  assert.equal(page.elements.calendar.hidden, false);
  assert.equal(page.calendarHomeCalls(), 1);
  assert.equal(page.elements.calendarTab["aria-current"], "page");
  assert.equal(page.elements.chatHomeTab["aria-current"], "false");

  page.elements.calendarNotesTab.click();
  assert.equal(page.elements.notes.hidden, false);
  assert.equal(page.notesHomeCalls(), 1);
  assert.equal(page.elements.notesHomeTab["aria-current"], "page");

  page.elements.chatTab.click();
  assert.equal(page.elements.chat.hidden, false);
  assert.equal(page.elements.chatHomeTab["aria-current"], "page");
});

test("Calendar and Notes events switch only the visible application surface", async () => {
  const page = await mountApp({
    turns: [],
    requestProductResult: async () => { throw new Error("not exercised"); },
  });
  assert.equal(page.elements.chat.hidden, false);
  assert.equal(page.elements.notes.hidden, true);
  assert.equal(page.elements.calendar.hidden, true);

  page.document.dispatchEvent(new CustomEvent("odyssey:open-calendar-day", {detail: {date: "2026-10-01"}}));
  assert.equal(page.elements.chat.hidden, true);
  assert.equal(page.elements.notes.hidden, true);
  assert.equal(page.elements.calendar.hidden, false);

  page.document.dispatchEvent(new CustomEvent("odyssey:open-note", {detail: {note_id: "marta"}}));
  assert.equal(page.elements.chat.hidden, true);
  assert.equal(page.elements.notes.hidden, false);
  assert.equal(page.elements.calendar.hidden, true);
});
