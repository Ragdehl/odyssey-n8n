import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

import {
  CalendarRequestError,
  requestCalendar as realRequestCalendar,
  validateCalendarResponse,
} from "../odyssey_web/calendar-client.js";
import {typeBadge, typeLabel} from "../odyssey_web/notes.js";

let fixtureNumber = 0;

class FakeText {
  constructor(value) { this.textContent = String(value); this.parentNode = null; }
  remove() { this.parentNode?.removeChild(this); }
}

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.hidden = false;
    this.parentNode = null;
    this._listeners = new Map();
    this._textContent = "";
  }
  set textContent(value) { this._textContent = String(value); this.children = []; }
  get textContent() { return this._textContent + this.children.map((child) => child.textContent).join(""); }
  append(...nodes) {
    for (const node of nodes) {
      if (node.parentNode) node.remove();
      node.parentNode = this;
      this.children.push(node);
    }
  }
  replaceChildren(...nodes) { this._textContent = ""; this.children = []; this.append(...nodes); }
  removeChild(node) {
    const index = this.children.indexOf(node);
    if (index >= 0) this.children.splice(index, 1);
    node.parentNode = null;
  }
  remove() { this.parentNode?.removeChild(this); }
  querySelector(selector) {
    for (const child of this.children) {
      if (matches(child, selector)) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
  querySelectorAll(selector) {
    const result = [];
    for (const child of this.children) {
      if (matches(child, selector)) result.push(child);
      result.push(...(child.querySelectorAll?.(selector) ?? []));
    }
    return result;
  }
  addEventListener(type, listener) { this._listeners.set(type, listener); }
  emit(type, event = {}) { this._listeners.get(type)?.({preventDefault() {}, currentTarget: this, ...event}); }
  click() { this.emit("click"); }
  setAttribute(name, value) { this[name] = value; }
}

class FakeDocument {
  constructor() { this._listeners = new Map(); this.events = []; }
  createElement(tagName) { return new FakeElement(tagName); }
  createElementNS(_namespace, tagName) { return new FakeElement(tagName); }
  createTextNode(value) { return new FakeText(value); }
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
  if (selector.startsWith(".")) return (element.className ?? "").split(" ").includes(selector.slice(1));
  if (selector.startsWith("#")) return element.id === selector.slice(1);
  return element.tagName === selector;
}

function summary(id, name, type = "person") {
  return {
    id, name, type, tags: [], created_at: "2026-10-01T08:00:00+02:00",
    updated_at: "2026-10-01T08:00:00+02:00", properties: {},
  };
}

function block(text) { return {kind: "list_item", segments: [{text}]}; }
function linkedBlock(prefix, text, targetId, targetType) {
  return {kind: "list_item", segments: [{text: prefix}, {text, target_id: targetId, target_type: targetType}]};
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return {promise, resolve, reject};
}

async function mountCalendar(requestCalendar, requestNotes = async () => { throw new Error("unexpected Notes mutation"); }) {
  const document = new FakeDocument();
  const root = new FakeElement("section");
  const elements = {
    monthView: new FakeElement("section"), dayView: new FakeElement("article"),
    title: new FakeElement("h2"), grid: new FakeElement("div"), status: new FakeElement("p"),
    today: new FakeElement("button"), previous: new FakeElement("button"), next: new FakeElement("button"),
  };
  elements.dayView.hidden = true;
  const map = new Map([
    ["#calendar-month-view", elements.monthView], ["#calendar-day-view", elements.dayView],
    ["#calendar-month-title", elements.title], ["#calendar-grid", elements.grid],
    ["#calendar-status", elements.status], ["#calendar-today", elements.today],
    ["#calendar-prev", elements.previous], ["#calendar-next", elements.next],
  ]);
  root.querySelector = (selector) => map.get(selector) ?? null;
  globalThis.document = document;
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
  };
  globalThis.__odysseyTestCalendarClient = {CalendarRequestError, requestCalendar};
  globalThis.__odysseyTestNotesClient = {
    NotesRequestError: class NotesRequestError extends Error {},
    requestNotes,
  };
  globalThis.__odysseyTestNotePresentation = {typeBadge, typeLabel};
  const source = await readFile(new URL("../odyssey_web/calendar.js", import.meta.url), "utf8");
  const testable = source
    .replace(
      'import {CalendarRequestError, requestCalendar} from "./calendar-client.js";',
      "const {CalendarRequestError, requestCalendar} = globalThis.__odysseyTestCalendarClient;",
    )
    .replace(
      'import {NotesRequestError, requestNotes} from "./notes-client.js";',
      "const {NotesRequestError, requestNotes} = globalThis.__odysseyTestNotesClient;",
    )
    .replace(
      'import {typeBadge, typeLabel} from "./notes.js";',
      "const {typeBadge, typeLabel} = globalThis.__odysseyTestNotePresentation;",
    );
  const {mountCalendar: mount} = await import(
    `data:text/javascript;base64,${Buffer.from(`${testable}\n// fixture ${fixtureNumber += 1}`).toString("base64")}`,
  );
  const controller = mount(root);
  await flush();
  return {controller, document, elements};
}

test("Calendar client sends only the bounded same-origin operation and validates month/day unions", async () => {
  const requests = [];
  const fetchImpl = async (_endpoint, options) => {
    requests.push(options);
    return {
      ok: true,
      async json() {
        return {
          kind: "calendar_month", month: "2026-10", days: [{
            date: "2026-10-01", materialized: false, has_content: false,
            journal_count: 0, captured_fact_count: 0, reference_count: 0, task_count: 0,
            preview_total: 1,
            previews: [{kind: "capture", source_type: "person", label: "Marta", text: "Empezó en Airbus."}],
          }],
        };
      },
    };
  };
  const value = await realRequestCalendar({operation: "month", payload: {month: "2026-10"}, fetchImpl});
  assert.equal(value.kind, "calendar_month");
  assert.deepEqual(value.days[0].previews, [
    {kind: "capture", source_type: "person", label: "Marta", text: "Empezó en Airbus."},
  ]);
  assert.equal(value.days[0].preview_total, 1);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].credentials, "same-origin");
  assert.deepEqual(JSON.parse(requests[0].body), {operation: "month", month: "2026-10"});

  const day = validateCalendarResponse({
    kind: "calendar_day", date: "2026-10-01", materialized: false, content: [],
    journals: [{source: summary("journal-1", "Diario", "journal_entry"), content: [block("Texto del diario.")]}],
    captures: [], references: [], tasks: [],
  });
  assert.equal(day.journals[0].source.type, "journal_entry");
  assert.equal(day.journals[0].content[0].segments[0].text, "Texto del diario.");
  assert.throws(() => validateCalendarResponse({
    kind: "calendar_month", month: "2026-10", days: [{
      date: "2026-10-01", materialized: false, has_content: false,
      journal_count: 0, captured_fact_count: 0, reference_count: 0, task_count: 0,
      preview_total: 5, previews: Array.from({length: 5}, () => ({kind: "journal", source_type: "journal_entry", label: "Diario"})),
    }],
  }), CalendarRequestError);
  assert.throws(() => validateCalendarResponse({
    kind: "calendar_month", month: "2026-10", days: [{
      date: "2026-10-01", materialized: false, has_content: false,
      journal_count: 0, captured_fact_count: 0, reference_count: 0, task_count: 0,
      preview_total: 1, previews: [{kind: "unknown", source_type: "person", label: "Marta"}],
    }],
  }), CalendarRequestError);
  assert.throws(() => validateCalendarResponse({
    kind: "calendar_month", month: "2026-10", days: [{
      date: "2026-10-01", materialized: false, has_content: false,
      journal_count: 0, captured_fact_count: 0, reference_count: 0, task_count: 0,
      preview_total: 1, previews: [{kind: "capture", source_type: "person", label: "Marta", text: "x".repeat(121)}],
    }],
  }), CalendarRequestError);
  assert.throws(() => validateCalendarResponse({kind: "calendar_day", date: "bad"}), CalendarRequestError);
});

test("month to Day to related Note is a bounded Calendar UI end-to-end flow", async () => {
  const calls = [];
  const month = {
    kind: "calendar_month", month: "2026-10", days: [
      {
        date: "2026-10-01", materialized: true, has_content: true,
        journal_count: 1, captured_fact_count: 2, reference_count: 1, task_count: 0,
        preview_total: 5,
        previews: [
          {kind: "day_content", source_type: "calendar_day", label: "1 octubre", text: "Compré una bici."},
          {kind: "journal", source_type: "journal_entry", label: "Diario", text: "Buen día."},
          {kind: "capture", source_type: "person", label: "Marta", text: "Empezó en Airbus."},
          {kind: "task", source_type: "task", label: "Llamar al banco"},
        ],
      },
      {date: "2026-10-02", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []},
    ],
  };
  const day = {
    kind: "calendar_day", date: "2026-10-01", materialized: true,
    content: [block("Compré una bici.")],
    journals: [{
      source: summary("journal-1", "Diario del jueves", "journal_entry"),
      content: [block("Hoy fue un buen día."), linkedBlock("Hablé con ", "Marta", "marta", "person")],
    }],
    captures: [{source: summary("marta", "Marta"), facts: [linkedBlock("Empezó en ", "Airbus", "airbus", "project"), block("Confirmó el horario.")]}],
    references: [{source: summary("trip", "Viaje", "project"), blocks: [block("La reserva corresponde al 1 de octubre.")]}], tasks: [],
  };
  const mounted = await mountCalendar(async ({operation, payload}) => {
    calls.push({operation, payload});
    return operation === "month" ? month : day;
  });

  assert.equal(calls[0].operation, "month");
  const cells = mounted.elements.grid.querySelectorAll(".calendar-day-cell");
  assert.equal(cells.length, 2);
  assert.equal(cells[0].dataset.date, "2026-10-01");
  const previews = cells[0].querySelectorAll(".calendar-month-preview");
  assert.equal(previews.length, 4);
  assert.equal(previews[0].textContent.includes("Compré una bici."), true);
  assert.equal(previews[0].textContent.includes("1 octubre"), false);
  assert.equal(previews[2].textContent.includes("Marta"), false);
  assert.equal(previews[2].textContent.includes("Empezó en Airbus."), true);
  assert.equal(previews[3].textContent.includes("Llamar al banco"), true);
  assert.equal(cells[0].querySelectorAll(".calendar-indicator").length, 0);
  assert.equal(cells[0].querySelector(".calendar-day-overflow").textContent, "+1");
  assert.ok(cells[0].querySelector(".note-type"));

  cells[0].click();
  await flush();

  assert.deepEqual(calls.at(-1), {operation: "day", payload: {date: "2026-10-01"}});
  assert.equal(calls.filter((call) => call.operation === "month").length, 1);
  assert.equal(mounted.elements.monthView.hidden, true);
  assert.equal(mounted.elements.dayView.hidden, false);
  assert.equal(mounted.elements.dayView.textContent.includes("Contenido del día"), true);
  assert.equal(mounted.elements.dayView.textContent.includes("Compré una bici."), true);
  assert.equal(mounted.elements.dayView.textContent.includes("Diario"), true);
  assert.equal(mounted.elements.dayView.textContent.includes("Hoy fue un buen día."), true);
  assert.equal(mounted.elements.dayView.textContent.split("Diario del jueves").length - 1, 1);
  assert.equal(mounted.elements.dayView.textContent.includes("Capturado este día"), true);
  assert.equal(mounted.elements.dayView.textContent.includes("Referencias a este día"), true);

  const diary = mounted.elements.dayView.querySelectorAll(".calendar-note-link")
    .find((item) => item.textContent === "Diario del jueves");
  assert.ok(diary?.querySelector(".note-type"));
  const inlineLink = mounted.elements.dayView.querySelector(".calendar-inline-link");
  assert.ok(inlineLink?.querySelector(".note-type"));

  const marta = mounted.elements.dayView.querySelectorAll(".calendar-note-link")
    .find((item) => item.textContent === "Marta");
  assert.ok(marta);
  assert.ok(marta.querySelector(".note-type"));
  marta.click();
  assert.equal(mounted.document.events.at(-1).type, "odyssey:open-note");
  assert.deepEqual(mounted.document.events.at(-1).detail, {note_id: "marta"});
});

test("Day navigation opens the previous and next natural dates without returning to month", async () => {
  const calls = [];
  const mounted = await mountCalendar(async ({operation, payload}) => {
    calls.push({operation, payload});
    if (operation === "month") {
      return {kind: "calendar_month", month: "2026-10", days: [{date: "2026-10-01", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []}]};
    }
    return {kind: "calendar_day", date: payload.date, materialized: false, content: [], journals: [], captures: [], references: [], tasks: []};
  });

  mounted.elements.grid.querySelector(".calendar-day-cell").click();
  await flush();
  mounted.elements.dayView.querySelector(".calendar-day-previous").click();
  await flush();
  assert.deepEqual(calls.at(-1), {operation: "day", payload: {date: "2026-09-30"}});
  assert.equal(mounted.elements.dayView.hidden, false);

  mounted.elements.dayView.querySelector(".calendar-day-next").click();
  await flush();
  assert.deepEqual(calls.at(-1), {operation: "day", payload: {date: "2026-10-01"}});
});

test("returning to month clears a stale Day error after failed date navigation", async () => {
  const mounted = await mountCalendar(async ({operation, payload}) => {
    if (operation === "month") return {
      kind: "calendar_month", month: "2026-10", days: [
        {date: "2026-10-01", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []},
      ],
    };
    if (payload.date === "2026-09-30") throw new CalendarRequestError("broken Day");
    return {kind: "calendar_day", date: payload.date, materialized: false, content: [], journals: [], captures: [], references: [], tasks: []};
  });

  mounted.elements.grid.querySelector(".calendar-day-cell").click();
  await flush();
  mounted.elements.dayView.querySelector(".calendar-day-previous").click();
  await flush();
  assert.equal(mounted.elements.status.textContent, "No se ha podido abrir este día.");

  mounted.elements.dayView.querySelector(".calendar-day-header").querySelector("button").click();
  await flush();
  assert.equal(mounted.elements.status.textContent, "");
  assert.equal(mounted.elements.monthView.hidden, false);
});

test("an empty virtual Day opens without materializing content in the browser", async () => {
  const mounted = await mountCalendar(async ({operation, payload}) => operation === "month"
    ? {kind: "calendar_month", month: payload.month, days: [{date: "2026-10-02", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []}]}
    : {kind: "calendar_day", date: payload.date, materialized: false, content: [], journals: [], captures: [], references: [], tasks: []});

  mounted.elements.grid.querySelector(".calendar-day-cell").click();
  await flush();
  assert.equal(mounted.elements.dayView.textContent.includes("No hay información asociada a este día."), true);
});

test("duplicate in-flight Day navigation shares one request", async () => {
  const pending = deferred();
  const calls = [];
  const mounted = await mountCalendar(async ({operation, payload}) => {
    calls.push({operation, payload});
    if (operation === "month") return {
      kind: "calendar_month", month: "2026-10", days: [
        {date: "2026-10-01", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []},
      ],
    };
    return pending.promise;
  });

  const first = mounted.controller.openDay("2026-09-25");
  const second = mounted.controller.openDay("2026-09-25");
  await flush();
  assert.equal(calls.filter((call) => call.operation === "day").length, 1);

  pending.resolve({kind: "calendar_day", date: "2026-09-25", materialized: false, content: [], journals: [], captures: [], references: [], tasks: []});
  await Promise.all([first, second]);
  assert.equal(mounted.controller.state.dayValue.date, "2026-09-25");
  assert.equal(mounted.elements.status.textContent, "");
});

test("only the newest Day request may update the visible state", async () => {
  const pending25 = deferred();
  const pending24 = deferred();
  const mounted = await mountCalendar(async ({operation, payload}) => {
    if (operation === "month") return {
      kind: "calendar_month", month: "2026-10", days: [
        {date: "2026-10-01", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, preview_total: 0, previews: []},
      ],
    };
    if (payload.date === "2026-09-25") return pending25.promise;
    if (payload.date === "2026-09-24") return pending24.promise;
    throw new Error("unexpected date");
  });

  const first = mounted.controller.openDay("2026-09-25");
  const second = mounted.controller.openDay("2026-09-24");
  pending24.resolve({kind: "calendar_day", date: "2026-09-24", materialized: false, content: [], journals: [], captures: [], references: [], tasks: []});
  await second;
  assert.equal(mounted.controller.state.dayValue.date, "2026-09-24");
  assert.equal(mounted.elements.status.textContent, "");

  pending25.reject(new CalendarRequestError("stale failure"));
  await first;
  assert.equal(mounted.controller.state.dayValue.date, "2026-09-24");
  assert.equal(mounted.elements.status.textContent, "");
});


test("Calendar Task checkbox uses the bounded Notes lifecycle mutation and updates in place", async () => {
  const noteCalls = [];
  const task = {
    source: {
      ...summary("task-bank", "Llamar al banco", "task"),
      properties: {status: "pending", target_date: "2026-10-09"},
    },
    roles: ["target"],
    mutation: {revision: 2, source_hash: "a".repeat(64)},
  };
  const mounted = await mountCalendar(
    async ({operation, payload}) => operation === "month"
      ? {kind: "calendar_month", month: payload.month, days: [{date: "2026-10-09", materialized: false, has_content: false, journal_count: 0, captured_fact_count: 0, reference_count: 0, task_count: 1, preview_total: 0, previews: []}]}
      : {kind: "calendar_day", date: payload.date, materialized: false, content: [], journals: [], captures: [], references: [], tasks: [task]},
    async ({operation, payload}) => {
      noteCalls.push({operation, payload});
      return {
        kind: "mutation", operation: "task_completed", note_id: "task-bank",
        history: {status: "COMMITTED"}, status: "completed",
        completed_at: "2026-10-05T11:40:00+02:00",
        mutation: {revision: 3, source_hash: "b".repeat(64)},
      };
    },
  );

  mounted.elements.grid.querySelector(".calendar-day-cell").click();
  await flush();
  const toggle = mounted.elements.dayView.querySelector(".calendar-task-toggle");
  assert.ok(toggle);
  assert.equal(toggle.textContent, "☐");
  toggle.click();
  await flush();

  assert.equal(noteCalls.length, 1);
  assert.equal(noteCalls[0].operation, "task_status");
  assert.equal(noteCalls[0].payload.note_id, "task-bank");
  assert.equal(noteCalls[0].payload.completed, true);
  assert.equal(noteCalls[0].payload.expected_revision, 2);
  assert.equal(noteCalls[0].payload.expected_source_hash, "a".repeat(64));
  const updated = mounted.elements.dayView.querySelector(".calendar-task-toggle");
  assert.equal(updated.textContent, "☑");
  assert.equal(updated["aria-checked"], "true");
  assert.equal(mounted.controller.state.monthValue, null);
  assert.equal(mounted.elements.status.textContent, "Tarea completada.");
});
