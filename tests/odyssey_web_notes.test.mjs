import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

import {NotesRequestError} from "../odyssey_web/notes-client.js";

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
    this.disabled = false;
    this.hidden = false;
    this.parentNode = null;
    this.scrollHeight = 100;
    this.clientHeight = 100;
    this.scrollTop = 0;
    this.value = "";
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
    const values = [];
    for (const child of this.children) {
      if (matches(child, selector)) values.push(child);
      values.push(...(child.querySelectorAll?.(selector) ?? []));
    }
    return values;
  }
  addEventListener(type, listener) { this._listeners.set(type, listener); }
  emit(type, event = {}) { this._listeners.get(type)?.({preventDefault() {}, currentTarget: this, ...event}); }
  click() { this.emit("click"); }
  setAttribute(name, value) { this[name] = value; }
  focus() {}
  showModal() {}
  close() {}
  reset() { this.value = ""; }
}

class FakeDocument {
  constructor() { this._elements = new Map(); this._listeners = new Map(); this.events = []; }
  createElement(tagName) { return new FakeElement(tagName); }
  createElementNS(_namespace, tagName) { return new FakeElement(tagName); }
  createTextNode(value) { return new FakeText(value); }
  querySelector(selector) {
    const direct = this._elements.get(selector);
    if (direct) return direct;
    for (const element of this._elements.values()) {
      const nested = element.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
  addEventListener(type, listener) { this._listeners.set(type, listener); }
  emit(type, event = {}) { this._listeners.get(type)?.(event); }
  dispatchEvent(event) { this.events.push(event); this._listeners.get(event.type)?.(event); return true; }
}

function matches(element, selector) {
  if (selector.startsWith(".")) return (element.className ?? "").split(" ").includes(selector.slice(1));
  if (selector.startsWith("#")) return element.id === selector.slice(1);
  return element.tagName === selector;
}

function pageItem(id, name = id, type = "person") {
  return {id, name, type, updated_at: "2026-09-22T10:00:00Z", tags: [], properties: {}};
}

function page({mode = "feed", items = [pageItem("a", "Resultado A")], total = items.length, applied_filters = [], next_cursor = null} = {}) {
  return {mode, items, total, next_cursor, sort: "relevance", applied_filters, snapshot_offset: 0};
}

function detail(id, name = id, mutation = null, body_blocks = []) {
  return {
    kind: "detail",
    note: {id, name, type: "person", properties: {}, created_at: "2026-09-20", updated_at: "2026-09-22", tags: []},
    body_blocks,
    ...(mutation ? {mutation} : {}),
  };
}

function taskDetail({sessions = [], status = "pending"} = {}) {
  return {
    kind: "detail",
    note: {
      id: "task-odyssey", name: "Trabajar en Odyssey", type: "task", properties: {status},
      created_at: "2026-10-05T10:00:00+02:00", updated_at: "2026-10-05T10:00:00+02:00", tags: [],
    },
    body_blocks: [],
    mutation: {revision: 4, source_hash: "a".repeat(64)},
    work_sessions: sessions,
  };
}

function workSession({id = "session-one", ended_at = null, revision = 1, source = "b", activity = []} = {}) {
  return {
    id, task_id: "task-odyssey", started_at: "2026-10-05T18:00:00+02:00",
    ended_at, activity, mutation: {revision, source_hash: source.repeat(64)},
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function mountNotes({requestNotes, confirmImpl = () => true, sessionStorageImpl = null}) {
  const document = new FakeDocument();
  const root = new FakeElement("section");
  const elements = {
    search: new FakeElement("input"), searchForm: new FakeElement("form"), list: new FakeElement("section"),
    listView: new FakeElement("section"), detail: new FakeElement("section"), sort: new FakeElement("select"),
    status: new FakeElement("p"), chips: new FakeElement("div"), filters: new FakeElement("button"),
    filterSheet: new FakeElement("dialog"), filterForm: new FakeElement("form"), filterFields: new FakeElement("div"),
    filterClose: new FakeElement("button"), filterClear: new FakeElement("button"),
  };
  elements.detail.hidden = true;
  elements.sort.value = "relevance";
  const rootSelectors = [
    ["#notes-search", elements.search], ["#notes-search-form", elements.searchForm], ["#notes-list", elements.list],
    ["#notes-list-view", elements.listView], ["#note-detail", elements.detail], ["#notes-sort", elements.sort],
    ["#notes-status", elements.status], ["#notes-filter-chips", elements.chips], ["#notes-filters", elements.filters],
  ];
  const rootMap = new Map(rootSelectors);
  root.querySelector = (selector) => rootMap.get(selector) ?? null;
  for (const [selector, element] of [
    ["#notes-filter-sheet", elements.filterSheet], ["#notes-filter-form", elements.filterForm],
    ["#notes-filter-fields", elements.filterFields], ["#notes-filter-close", elements.filterClose],
    ["#notes-filter-clear", elements.filterClear],
  ]) document._elements.set(selector, element);
  globalThis.document = document;
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) { this.type = type; this.detail = init.detail; }
  };
  globalThis.__odysseyTestNotesClient = {NotesRequestError, requestNotes};
  const source = await readFile(new URL("../odyssey_web/notes.js", import.meta.url), "utf8");
  const testable = source.replace(
    'import {NotesRequestError, requestNotes} from "./notes-client.js";',
    "const {NotesRequestError, requestNotes} = globalThis.__odysseyTestNotesClient;",
  );
  const {mountNotes: mount} = await import(
    `data:text/javascript;base64,${Buffer.from(`${testable}\n// fixture ${fixtureNumber += 1}`).toString("base64")}`,
  );
  const controller = mount(root, {confirmImpl, sessionStorageImpl});
  await flush();
  return {controller, document, elements};
}

async function mountMutationNote({confirmImpl}) {
  const calls = [];
  const mutation = {
    revision: 7,
    source_hash: "a".repeat(64),
  };
  const bodyBlocks = [
    {kind: "list_item", deletable: true, fact_locator: "request-1:0", segments: [
      {text: "Ada conoce a "}, {text: "Axel", target_id: "axel", target_type: "person"},
      {text: " y "}, {text: "Denis", target_id: "denis", target_type: "person"}, {text: "."},
    ]},
    {kind: "list_item", segments: [{text: "Contenido de referencia visible una vez."}]},
  ];
  const mounted = await mountNotes({
    confirmImpl,
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return detail(payload.note_id, "Ada", mutation, bodyBlocks);
      if (operation === "backlinks") return {items: []};
      if (operation === "delete_fact" || operation === "delete_note") return {
        kind: "mutation", operation: operation === "delete_fact" ? "fact_deleted" : "note_deleted",
        note_id: "ada", history: {status: "COMMITTED"},
      };
      return page({items: [pageItem("ada", "Ada")]});
    },
  });
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  return {mounted, calls};
}


test("load more recovers a stale cursor by restarting the current feed", async () => {
  let queries = 0;
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation !== "query") return page();
      queries += 1;
      if (queries === 1) return page({items: [pageItem("old", "Antes")], total: 2, next_cursor: "old-cursor"});
      if (queries === 2) {
        assert.equal(payload.cursor, "old-cursor");
        throw new NotesRequestError("cursor obsoleto", "STALE_CURSOR");
      }
      assert.equal(payload.cursor, null);
      return page({items: [pageItem("new", "Nueva"), pageItem("old", "Antes")], total: 2});
    },
  });

  mounted.elements.list.querySelector(".notes-group-more").click();
  await flush();
  await flush();

  assert.equal(queries, 3);
  assert.equal(mounted.elements.list.textContent.includes("Nueva"), true);
  assert.equal(mounted.elements.list.querySelector(".notes-group-more"), null);
  assert.equal(mounted.elements.status.textContent, "2 notas");
});

test("generic open-note event opens the stable note ID through the existing detail path", async () => {
  const calls = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return detail(payload.note_id, "Cloe");
      return page();
    },
  });

  mounted.document.emit("odyssey:open-note", {detail: {note_id: "cloe"}});
  await flush();

  assert.deepEqual(calls.filter(({operation}) => operation === "detail"), [
    {operation: "detail", payload: {note_id: "cloe"}},
  ]);
  assert.equal(mounted.elements.detail.hidden, false);
  assert.equal(mounted.elements.detail.textContent.includes("Cloe"), true);
});

function capabilities() {
  return {types: [{id: "person", name: "Person", description: "A person with stable identity.", properties: []}], fields: []};
}

function groupedCapabilities() {
  return {
    types: [
      {id: "person", name: "Person", description: "A person with stable identity.", properties: []},
      {id: "task", name: "Task", description: "An actionable item.", properties: [{
        id: "status", description: "Current lifecycle state.", value_type: "string",
        required: true, filterable: true,
      }]},
    ],
    fields: [{
      id: "status", value_type: "string", operators: ["eq"], applies_to: ["task"],
      controlled_values: ["pending", "completed"], format: null,
    }],
  };
}

function groupElement(mounted, type) {
  return mounted.elements.list.querySelectorAll(".notes-type-group").find(
    (group) => group.dataset.type === type,
  );
}

test("normal Notes browsing loads bounded independent type groups and advances only one group", async () => {
  const calls = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return groupedCapabilities();
      const type = payload.filters.find((filter) => filter.field === "type").value;
      if (type === "person" && payload.cursor === null) return page({
        items: [pageItem("p1"), pageItem("p2"), pageItem("p3")], total: 4, next_cursor: "person-next",
      });
      if (type === "person") return page({items: [pageItem("p4")], total: 4});
      return page({items: [pageItem("t1", "Tarea", "task")], total: 1});
    },
  });

  const initial = calls.filter(({operation}) => operation === "query");
  assert.equal(initial.length, 2);
  assert.equal(initial.every(({payload}) => payload.page_size === 3), true);
  assert.deepEqual(initial.map(({payload}) => payload.filters.at(-1).value).sort(), ["person", "task"]);
  assert.equal(groupElement(mounted, "person").querySelector(".notes-type-count").textContent, "4");
  assert.equal(groupElement(mounted, "task").querySelector(".notes-type-count").textContent, "1");
  assert.equal(mounted.elements.list.textContent.includes("tipos de nota que Odyssey usa"), true);

  mounted.elements.list.emit("scroll");
  await flush();
  assert.equal(calls.filter(({operation}) => operation === "query").length, 2);
  groupElement(mounted, "person").querySelector(".notes-group-more").click();
  await flush();

  const continued = calls.filter(({operation}) => operation === "query").at(-1);
  assert.equal(continued.payload.cursor, "person-next");
  assert.equal(continued.payload.filters.at(-1).value, "person");
  assert.equal(groupElement(mounted, "person").querySelectorAll(".note-row").length, 4);
  assert.equal(groupElement(mounted, "task").querySelectorAll(".note-row").length, 1);
});

test("general controls refresh every group while Task status skips incompatible groups", async () => {
  const calls = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return groupedCapabilities();
      const type = payload.filters.find((filter) => filter.field === "type").value;
      return page({items: [pageItem(`${type}-1`, type, type)], total: 1});
    },
  });
  assert.equal(mounted.elements.filterFields.querySelector("#filter-type"), null);
  assert.notEqual(mounted.elements.filterFields.querySelector("#filter-status"), null);

  calls.length = 0;
  mounted.controller.state.filters = [{field: "tags", op: "contains", value: "casa"}];
  await mounted.controller.refresh();
  let queries = calls.filter(({operation}) => operation === "query");
  assert.equal(queries.length, 2);
  assert.equal(queries.every(({payload}) => payload.filters.some((filter) => filter.field === "tags")), true);

  calls.length = 0;
  mounted.controller.state.filters = [{field: "status", op: "eq", value: "pending"}];
  await mounted.controller.refresh();
  queries = calls.filter(({operation}) => operation === "query");
  assert.equal(queries.length, 1);
  assert.deepEqual(queries[0].payload.filters, [
    {field: "status", op: "eq", value: "pending"},
    {field: "type", op: "eq", value: "task"},
  ]);
  assert.equal(groupElement(mounted, "person"), undefined);
  assert.notEqual(groupElement(mounted, "task"), undefined);

  calls.length = 0;
  mounted.controller.state.filters = [];
  mounted.elements.sort.value = "updated_desc";
  mounted.elements.sort.emit("change");
  await flush();
  queries = calls.filter(({operation}) => operation === "query");
  assert.equal(queries.length, 2);
  assert.equal(queries.every(({payload}) => payload.sort === "updated_desc"), true);

  calls.length = 0;
  mounted.elements.search.value = "ana";
  mounted.elements.search.emit("input");
  await flush();
  queries = calls.filter(({operation}) => operation === "query");
  assert.equal(queries.length, 2);
  assert.equal(queries.every(({payload}) => payload.mode === "local" && payload.query === "ana"), true);

  calls.length = 0;
  mounted.controller.state.filters = [{field: "type", op: "eq", value: "person"}];
  await mounted.controller.refresh();
  queries = calls.filter(({operation}) => operation === "query");
  assert.equal(queries.length, 1);
  assert.equal(queries[0].payload.filters.at(-1).value, "person");
  assert.equal(mounted.elements.chips.textContent.includes("Tipo"), true);
});

test("collapse state is session-only and storage failures degrade safely", async () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const requestNotes = async ({operation, payload}) => {
    if (operation === "capabilities") return capabilities();
    return page({items: [pageItem(`note-${payload.filters.at(-1).value}`)]});
  };
  const first = await mountNotes({requestNotes, sessionStorageImpl: storage});
  groupElement(first, "person").querySelector(".notes-type-toggle").click();
  assert.equal(groupElement(first, "person").querySelector(".notes-type-group-body").hidden, true);
  assert.equal(values.get("odyssey.notes.collapsed-types.v1"), '["person"]');

  const second = await mountNotes({requestNotes, sessionStorageImpl: storage});
  assert.equal(groupElement(second, "person").querySelector(".notes-type-group-body").hidden, true);

  const unavailable = {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }};
  const fallback = await mountNotes({requestNotes, sessionStorageImpl: unavailable});
  groupElement(fallback, "person").querySelector(".notes-type-toggle").click();
  assert.equal(fallback.controller.state.collapsedTypes.has("person"), true);
});

test("intelligent Notes plans once, groups loaded results, and continues deterministically", async () => {
  const calls = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return groupedCapabilities();
      if (operation === "intelligent") return page({
        mode: "intelligent",
        items: [pageItem("p1"), pageItem("t1", "Tarea", "task")], total: 3,
        next_cursor: "intelligent-next",
      });
      if (payload.mode === "intelligent") return page({
        mode: "intelligent", items: [pageItem("p2")], total: 3,
      });
      return page({items: [], total: 0});
    },
  });
  mounted.elements.search.value = "cosas pendientes";
  mounted.elements.searchForm.emit("submit");
  await flush();

  assert.equal(calls.filter(({operation}) => operation === "intelligent").length, 1);
  assert.notEqual(groupElement(mounted, "person"), undefined);
  assert.notEqual(groupElement(mounted, "task"), undefined);
  mounted.elements.list.querySelector(".notes-more").click();
  await flush();

  assert.equal(calls.filter(({operation}) => operation === "intelligent").length, 1);
  const continuation = calls.filter(({operation, payload}) => operation === "query" && payload.mode === "intelligent");
  assert.equal(continuation.length, 1);
  assert.equal(continuation[0].payload.cursor, "intelligent-next");
  assert.equal(groupElement(mounted, "person").querySelectorAll(".note-row").length, 2);
});

test("historical grouping preserves stable-ID order and unavailable positions", async () => {
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return groupedCapabilities();
      if (payload.mode === "snapshot") return page({mode: "snapshot", items: [
        pageItem("p1"), pageItem("t1", "Tarea", "task"), pageItem("p2"),
      ], total: 4});
      return page({items: [], total: 0});
    },
  });
  mounted.document.emit("odyssey:open-note-snapshot", {detail: {
    version: 2, kind: "affected_notes", note_ids: ["p1", "t1", "p2", "gone"],
    total: 4, truncated: false,
  }});
  await flush();

  assert.deepEqual(
    mounted.elements.list.querySelectorAll(".note-row").map((row) => row.dataset.noteId),
    ["p1", "t1", "p2", "gone"],
  );
  assert.equal(mounted.elements.list.querySelector(".notes-group-more"), null);
  assert.equal(mounted.elements.status.querySelector(".notes-show-all").textContent, "Ver todas");
});

test("create-new-type card is presentation-only work in progress", async () => {
  const calls = [];
  const mounted = await mountNotes({requestNotes: async ({operation}) => {
    calls.push(operation);
    if (operation === "capabilities") return capabilities();
    return page();
  }});
  const before = calls.length;
  mounted.elements.list.querySelector(".notes-create-type-button").click();
  assert.equal(mounted.elements.list.querySelector(".notes-create-type-message").hidden, false);
  assert.equal(mounted.elements.list.textContent.includes("Próximamente"), true);
  assert.equal(calls.length, before);
});

function enterEditMode(mounted) {
  mounted.elements.detail.querySelector(".note-edit-toggle").click();
}

test("read mode renders linked facts once without destructive controls or raw Markdown", async () => {
  const {mounted} = await mountMutationNote({confirmImpl: () => true});

  assert.equal(mounted.elements.detail.querySelector(".note-edit-toggle").textContent, "Editar");
  assert.equal(mounted.elements.detail.querySelector(".note-delete-button"), null);
  assert.equal(mounted.elements.detail.querySelector(".note-fact-delete"), null);
  assert.equal(mounted.elements.detail.querySelector(".note-actions"), null);
  assert.equal(mounted.elements.detail.textContent.includes("[["), false);
  assert.equal(mounted.elements.detail.textContent.includes("request-1:0"), false);
  assert.equal(mounted.elements.detail.textContent.includes("Ada conoce a Axel y Denis."), true);
  assert.equal(mounted.elements.detail.textContent.split("Contenido de referencia visible una vez.").length, 2);
  assert.equal(mounted.elements.detail.querySelector(".note-body").querySelector("a").textContent, "Axel");
});

test("entering and leaving edit mode reveals only safe inline mutation controls", async () => {
  const {mounted} = await mountMutationNote({confirmImpl: () => true});
  enterEditMode(mounted);

  assert.equal(mounted.elements.detail.querySelector(".note-edit-toggle").textContent, "Hecho");
  assert.equal(mounted.elements.detail.querySelector(".note-delete-button").textContent, "Eliminar nota");
  const factDelete = mounted.elements.detail.querySelector(".note-fact-delete");
  assert.equal(factDelete.textContent, "Eliminar");
  assert.equal(factDelete.parentNode.textContent.includes("Axel"), true);
  assert.equal(factDelete.parentNode.textContent.includes("Denis"), true);
  assert.equal(mounted.elements.detail.textContent.includes("Contenido de referencia visible una vez.Eliminar"), false);

  mounted.elements.detail.querySelector(".note-edit-toggle").click();

  assert.equal(mounted.elements.detail.querySelector(".note-edit-toggle").textContent, "Editar");
  assert.equal(mounted.elements.detail.querySelector(".note-delete-button"), null);
  assert.equal(mounted.elements.detail.querySelector(".note-fact-delete"), null);
});

test("cancel fact deletion keeps the detail open and sends no mutation request", async () => {
  let confirmation = "";
  const {mounted, calls} = await mountMutationNote({confirmImpl: (message) => {
    confirmation = message;
    return false;
  }});
  const current = mounted.controller.state.current;
  enterEditMode(mounted);
  mounted.elements.detail.querySelector(".note-fact-delete").click();
  await flush();

  assert.equal(confirmation, "¿Eliminar esta información de Ada?");
  assert.equal(calls.filter(({operation}) => operation.startsWith("delete_")).length, 0);
  assert.strictEqual(mounted.controller.state.current, current);
  assert.equal(mounted.elements.detail.hidden, false);
  assert.equal(mounted.elements.detail.textContent.includes("Ada conoce a Axel y Denis."), true);
});

test("confirm fact deletion sends one bounded request with current stale-state tokens", async () => {
  const {mounted, calls} = await mountMutationNote({confirmImpl: () => true});
  enterEditMode(mounted);
  mounted.elements.detail.querySelector(".note-fact-delete").click();
  await flush();

  const mutations = calls.filter(({operation}) => operation.startsWith("delete_"));
  assert.equal(mutations.length, 1);
  assert.equal(mutations[0].operation, "delete_fact");
  assert.deepEqual(Object.keys(mutations[0].payload).sort(), [
    "expected_revision", "expected_source_hash", "fact_locator", "note_id", "request_id",
  ]);
  assert.equal(mutations[0].payload.note_id, "ada");
  assert.equal(mutations[0].payload.fact_locator, "request-1:0");
  assert.equal(mutations[0].payload.expected_revision, 7);
  assert.equal(mutations[0].payload.expected_source_hash, "a".repeat(64));
  assert.match(mutations[0].payload.request_id, /^notes-[a-f0-9]{32}$/);
  assert.strictEqual(mounted.controller.state.current.note.id, "ada");
  assert.equal(mounted.elements.detail.hidden, false);
  assert.equal(calls.filter(({operation}) => operation === "detail").length, 2);
});

test("cancel Note deletion keeps the detail open and sends no mutation request", async () => {
  let confirmation = "";
  const {mounted, calls} = await mountMutationNote({confirmImpl: (message) => {
    confirmation = message;
    return false;
  }});
  const current = mounted.controller.state.current;
  enterEditMode(mounted);
  mounted.elements.detail.querySelector(".note-delete-button").click();
  await flush();

  assert.equal(confirmation, "¿Eliminar la nota Ada?");
  assert.equal(calls.filter(({operation}) => operation.startsWith("delete_")).length, 0);
  assert.strictEqual(mounted.controller.state.current, current);
  assert.equal(mounted.elements.detail.hidden, false);
  assert.equal(mounted.elements.detail.textContent.includes("Ada"), true);
});

test("confirm Note deletion sends one bounded request with current stale-state tokens", async () => {
  const {mounted, calls} = await mountMutationNote({confirmImpl: () => true});
  enterEditMode(mounted);
  mounted.elements.detail.querySelector(".note-delete-button").click();
  await flush();

  const mutations = calls.filter(({operation}) => operation.startsWith("delete_"));
  assert.equal(mutations.length, 1);
  assert.equal(mutations[0].operation, "delete_note");
  assert.deepEqual(Object.keys(mutations[0].payload).sort(), [
    "expected_revision", "expected_source_hash", "note_id", "request_id",
  ]);
  assert.equal(mutations[0].payload.note_id, "ada");
  assert.equal(mutations[0].payload.expected_revision, 7);
  assert.equal(mutations[0].payload.expected_source_hash, "a".repeat(64));
  assert.match(mutations[0].payload.request_id, /^notes-[a-f0-9]{32}$/);
  assert.equal(mounted.controller.state.current, null);
  assert.equal(mounted.elements.detail.hidden, true);
});

test("affected snapshots expose Ver todas and return only Notes to the normal feed", async () => {
  const calls = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (payload.mode === "snapshot") return page({mode: "snapshot", items: [pageItem("marta", "Marta"), pageItem("elena", "Elena")], total: 2});
      return page();
    },
  });
  const snapshot = {version: 2, kind: "affected_notes", note_ids: ["marta", "elena"], total: 2, truncated: false};
  mounted.document.emit("odyssey:open-note-snapshot", {detail: snapshot});
  await flush();

  const all = mounted.elements.status.querySelector(".notes-show-all");
  assert.equal(mounted.elements.status.textContent.includes("2 notas afectadas"), true);
  assert.equal(all.textContent, "Ver todas");
  assert.equal(mounted.controller.state.snapshot, snapshot);
  assert.equal(mounted.elements.filters.disabled, true);
  assert.equal(mounted.elements.sort.disabled, true);

  all.click();
  await flush();

  assert.equal(mounted.controller.state.snapshot, null);
  assert.equal(mounted.controller.state.historical, false);
  assert.deepEqual(mounted.controller.state.filters, []);
  assert.equal(mounted.controller.state.query, "");
  assert.equal(mounted.controller.state.sort, "relevance");
  assert.equal(mounted.elements.filters.disabled, false);
  assert.equal(mounted.elements.sort.disabled, false);
  assert.equal(mounted.elements.list.textContent.includes("Resultado A"), true);
  assert.equal(calls.at(-1).payload.mode, "feed");

  mounted.document.emit("odyssey:open-note-snapshot", {detail: snapshot});
  await flush();
  assert.equal(mounted.controller.state.snapshot, snapshot);
  assert.equal(mounted.elements.list.textContent.includes("Marta"), true);
});

test("historical search snapshots retain rerun and expose Ver todas", async () => {
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (payload.mode === "snapshot") return page({mode: "snapshot", items: [pageItem("old", "Histórica")], total: 4});
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note-snapshot", {detail: {
    version: 1, query: "personas", filters: [], sort: "relevance", ranking_version: "v1",
    executed_at: "2026-09-22T10:00:00Z", note_ids: ["old"], total: 4, truncated: true,
  }});
  await flush();

  assert.equal(mounted.elements.status.querySelector(".notes-rerun").textContent, "Actualizar búsqueda");
  assert.equal(mounted.elements.status.querySelector(".notes-show-all").textContent, "Ver todas");
});

test("returning from an affected snapshot detail restores status, exit, and exact list", async () => {
  const snapshot = {version: 2, kind: "affected_notes", note_ids: ["marta", "elena"], total: 2, truncated: false};
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return detail(payload.note_id, payload.note_id === "marta" ? "Marta" : "Elena");
      if (operation === "backlinks") return {items: []};
      if (payload.mode === "snapshot") return page({mode: "snapshot", items: [pageItem("marta", "Marta"), pageItem("elena", "Elena")], total: 2});
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note-snapshot", {detail: snapshot});
  await flush();
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  mounted.elements.detail.querySelector("button").click();
  await flush();

  assert.equal(mounted.elements.status.textContent.includes("2 notas afectadas"), true);
  assert.equal(mounted.elements.status.querySelector(".notes-show-all").textContent, "Ver todas");
  assert.equal(mounted.elements.list.textContent.includes("MartaPersona · actualizada 9/22/2026"), true);
  assert.equal(mounted.elements.list.textContent.includes("ElenaPersona · actualizada 9/22/2026"), true);
  assert.equal(mounted.elements.filters.disabled, true);
  assert.equal(mounted.elements.sort.disabled, true);
});

test("returning from a historical snapshot detail restores rerun and exit controls", async () => {
  const snapshot = {
    version: 1, query: "personas", filters: [], sort: "relevance", ranking_version: "v1",
    executed_at: "2026-09-22T10:00:00Z", note_ids: ["old"], total: 4, truncated: true,
  };
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return detail(payload.note_id, "Histórica");
      if (operation === "backlinks") return {items: []};
      if (payload.mode === "snapshot") return page({mode: "snapshot", items: [pageItem("old", "Histórica")], total: 4});
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note-snapshot", {detail: snapshot});
  await flush();
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  mounted.elements.detail.querySelector("button").click();
  await flush();

  assert.equal(mounted.elements.status.textContent.includes("Resultado histórico · 1 de 4 notas"), true);
  assert.equal(mounted.elements.status.querySelector(".notes-rerun").textContent, "Actualizar búsqueda");
  assert.equal(mounted.elements.status.querySelector(".notes-show-all").textContent, "Ver todas");
  assert.equal(mounted.elements.filters.disabled, true);
  assert.equal(mounted.elements.sort.disabled, true);
});

test("returning from a normal note detail restores list status without reloading", async () => {
  let feedQueries = 0;
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "query" && payload.mode === "feed") {
        feedQueries += 1;
        return page({items: [pageItem("a", "Resultado A")], total: 1});
      }
      if (operation === "detail") return detail(payload.note_id, "Resultado A");
      if (operation === "backlinks") return {items: []};
      return page();
    },
  });
  const initialQueries = feedQueries;
  mounted.controller.state.query = "A";
  mounted.controller.state.filters = [{field: "type", op: "eq", value: "person"}];
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  mounted.elements.detail.querySelector("button").click();
  await flush();

  assert.equal(mounted.elements.status.textContent, "1 notas");
  assert.equal(mounted.controller.state.query, "A");
  assert.deepEqual(mounted.controller.state.filters, [{field: "type", op: "eq", value: "person"}]);
  assert.equal(feedQueries, initialQueries);
  assert.equal(mounted.elements.list.textContent.includes("Resultado A"), true);
});

test("an unsafe intelligent-filter response clears stale rows without installing its filters", async () => {
  let intelligentCalls = 0;
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "intelligent") {
        intelligentCalls += 1;
        return page({mode: "intelligent", items: [pageItem("unsafe", "Resultado inseguro")], total: 1,
          applied_filters: [{field: "unsupported", op: "eq", value: "x"}]});
      }
      return page();
    },
  });
  assert.equal(mounted.elements.list.textContent.includes("Resultado A"), true);
  mounted.elements.search.value = "Hijos de Lara";
  mounted.elements.searchForm.emit("submit");
  await flush();

  assert.equal(mounted.elements.status.textContent, "No se pueden mostrar filtros de esta búsqueda con seguridad.");
  assert.equal(mounted.elements.list.textContent.includes("Resultado A"), false);
  assert.equal(mounted.elements.list.textContent.includes("Resultado inseguro"), false);
  assert.deepEqual(mounted.controller.state.items, []);
  assert.deepEqual(mounted.controller.state.filters, []);
  assert.equal(mounted.elements.search.value, "Hijos de Lara");
  assert.equal(intelligentCalls, 1);

  mounted.elements.search.value = "Lara";
  mounted.elements.search.emit("input");
  await flush();
  assert.equal(mounted.controller.state.query, "Lara");
  assert.equal(intelligentCalls, 1);
});

test("Calendar Day inline links hand navigation to Calendar instead of opening managed Notes", async () => {
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return detail(payload.note_id, "Marta", null, [{
        kind: "heading", segments: [
          {text: "Added "},
          {text: "01-10-2026", target_id: "date:2026-10-01", target_type: "calendar_day"},
        ],
      }]);
      if (operation === "backlinks") return {kind: "backlinks", target_id: payload.note_id, items: [], total: 0, next_cursor: null};
      return page({items: [pageItem("marta", "Marta")]});
    },
  });
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  const dateLink = mounted.elements.detail.querySelector("a");
  assert.equal(dateLink.textContent.includes("01-10-2026"), true);
  assert.equal(dateLink.className, "note-inline-link");
  assert.equal(dateLink.querySelector(".note-type").className.includes("type-calendar_day"), true);
  dateLink.click();
  assert.equal(mounted.document.events.at(-1).type, "odyssey:open-calendar-day");
  assert.deepEqual(mounted.document.events.at(-1).detail, {date: "2026-10-01"});
});

test("inline links keep standard link text color while the target icon keeps semantic color", async () => {
  const mounted = await mountNotes({requestNotes: async ({operation, payload}) => {
    if (operation === "capabilities") return capabilities();
    if (operation === "detail") return detail(payload.note_id, "Ada", null, [{
      kind: "paragraph", segments: [{text: "Marta", target_id: "marta", target_type: "person"}],
    }]);
    if (operation === "backlinks") return {items: []};
    return page({items: [pageItem("ada", "Ada")]});
  }});
  mounted.elements.list.querySelector(".note-row").click();
  await flush();
  const link = mounted.elements.detail.querySelector("a");
  assert.equal(link.className, "note-inline-link");
  assert.equal(link.querySelector(".note-type").className.includes("type-person"), true);

  const css = await readFile(new URL("../odyssey_web/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.note-inline-link \{ color: #394d88;/);
  assert.match(css, /\.type-person, \.type-concept \{ color:/);
});

test("Notes list metadata does not override semantic type icon colors", async () => {
  const css = await readFile(new URL("../odyssey_web/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.type-person, \.type-concept \{ color:/);
  assert.match(css, /\.type-project, \.type-store \{ color:/);
  assert.match(css, /\.type-task, \.type-purchase \{ color:/);
  assert.match(css, /\.type-calendar_day \{ color:/);
  assert.match(css, /\.note-inline-link \.note-type \{/);
  assert.match(css, /\.note-row > span \{/);
  assert.doesNotMatch(css, /\.note-row span \{/);
});

test("Task Work Session start and stop use bounded stale-state tokens and update in place", async () => {
  const calls = [];
  let sessions = [];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail({sessions});
      if (operation === "backlinks") return {items: []};
      if (operation === "work_session_start") {
        sessions = [workSession()];
        return {kind: "mutation", operation: "work_session_started", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      if (operation === "work_session_stop") {
        sessions = [workSession({ended_at: "2026-10-05T18:45:00+02:00", revision: 2, source: "c"})];
        return {kind: "mutation", operation: "work_session_stopped", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();

  const start = mounted.elements.detail.querySelector(".work-session-start");
  assert.equal(start.textContent, "Empezar sesión");
  start.click();
  await flush();
  const startCall = calls.find(({operation}) => operation === "work_session_start");
  assert.deepEqual(Object.keys(startCall.payload).sort(), [
    "expected_revision", "expected_source_hash", "note_id", "request_id",
  ]);
  assert.equal(startCall.payload.note_id, "task-odyssey");
  assert.equal(startCall.payload.expected_revision, 4);
  assert.equal(startCall.payload.expected_source_hash, "a".repeat(64));
  assert.equal(calls.filter(({operation}) => operation === "detail").length, 1);

  const stop = mounted.elements.detail.querySelector(".work-session-stop");
  assert.equal(stop.textContent, "Terminar sesión");
  stop.click();
  await flush();
  const stopCall = calls.find(({operation}) => operation === "work_session_stop");
  assert.deepEqual(Object.keys(stopCall.payload).sort(), [
    "expected_revision", "expected_source_hash", "request_id", "session_id",
  ]);
  assert.equal(stopCall.payload.session_id, "session-one");
  assert.equal(stopCall.payload.expected_revision, 1);
  assert.equal(stopCall.payload.expected_source_hash, "b".repeat(64));
  assert.equal(calls.filter(({operation}) => operation === "detail").length, 1);
  assert.equal(mounted.elements.detail.textContent.includes("45 min"), true);
});


test("Task Work Session edit submits corrected local date/time without refetching the Task", async () => {
  const calls = [];
  let sessions = [workSession({ended_at: "2026-10-05T19:00:00+02:00"})];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail({sessions});
      if (operation === "backlinks") return {items: []};
      if (operation === "work_session_edit") {
        sessions = [{...sessions[0], started_at: payload.started_at, ended_at: payload.ended_at,
          mutation: {revision: 2, source_hash: "d".repeat(64)}}];
        return {kind: "mutation", operation: "work_session_edited", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  mounted.elements.detail.querySelector(".work-session-edit").click();
  const start = mounted.elements.detail.querySelector(".work-session-edit-start");
  const end = mounted.elements.detail.querySelector(".work-session-edit-end");
  start.value = "2026-10-05T17:30";
  end.value = "2026-10-05T18:15";
  mounted.elements.detail.querySelector(".work-session-save").click();
  await flush();

  const edit = calls.find(({operation}) => operation === "work_session_edit");
  assert.equal(edit.payload.session_id, "session-one");
  assert.equal(edit.payload.expected_revision, 1);
  assert.equal(edit.payload.expected_source_hash, "b".repeat(64));
  assert.equal(new Date(edit.payload.started_at).getTime(), new Date("2026-10-05T17:30").getTime());
  assert.equal(new Date(edit.payload.ended_at).getTime(), new Date("2026-10-05T18:15").getTime());
  assert.equal(calls.filter(({operation}) => operation === "detail").length, 1);
  assert.equal(mounted.elements.detail.textContent.includes("45 min"), true);
});


test("Task Work Session activity can be added, edited, and deleted without refetching the Task", async () => {
  const calls = [];
  let sessions = [workSession({ended_at: "2026-10-05T19:00:00+02:00"})];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail({sessions});
      if (operation === "backlinks") return {items: []};
      if (operation === "work_session_activity_add") {
        sessions = [workSession({
          ended_at: "2026-10-05T19:00:00+02:00", revision: 2, source: "c",
          activity: [{id: "activity-one", created_at: "2026-10-05T19:05:00+02:00", text: payload.text}],
        })];
        return {kind: "mutation", operation: "work_session_activity_added", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      if (operation === "work_session_activity_edit") {
        sessions = [workSession({
          ended_at: "2026-10-05T19:00:00+02:00", revision: 3, source: "d",
          activity: [{id: "activity-one", created_at: "2026-10-05T19:05:00+02:00", text: payload.text}],
        })];
        return {kind: "mutation", operation: "work_session_activity_edited", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      if (operation === "work_session_activity_delete") {
        sessions = [workSession({ended_at: "2026-10-05T19:00:00+02:00", revision: 4, source: "e"})];
        return {kind: "mutation", operation: "work_session_activity_deleted", note_id: "task-odyssey", history: {status: "COMMITTED"}, work_sessions: sessions};
      }
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  mounted.elements.detail.querySelector(".work-session-open").click();
  const form = mounted.elements.detail.querySelector(".work-session-activity-form");
  const textarea = form.querySelector("textarea");
  textarea.value = "He terminado los tests.";
  form.emit("submit");
  await flush();

  const add = calls.find(({operation}) => operation === "work_session_activity_add");
  assert.equal(add.payload.session_id, "session-one");
  assert.equal(add.payload.text, "He terminado los tests.");
  assert.equal(add.payload.expected_revision, 1);
  assert.equal(add.payload.expected_source_hash, "b".repeat(64));
  assert.equal(mounted.elements.detail.textContent.includes("He terminado los tests."), true);

  mounted.elements.detail.querySelector(".work-session-activity-actions").querySelector("button").click();
  const editInput = mounted.elements.detail.querySelector(".work-session-activity-edit-input");
  editInput.value = "He terminado todos los tests.";
  mounted.elements.detail.querySelector(".work-session-activity-actions").querySelector("button").click();
  await flush();
  const edit = calls.find(({operation}) => operation === "work_session_activity_edit");
  assert.equal(edit.payload.activity_id, "activity-one");
  assert.equal(edit.payload.text, "He terminado todos los tests.");
  assert.equal(edit.payload.expected_revision, 2);

  const activityRow = mounted.elements.detail.querySelector(".work-session-activity-row");
  const actions = activityRow.querySelector(".work-session-activity-actions");
  actions.children[1].click();
  await flush();
  const remove = calls.find(({operation}) => operation === "work_session_activity_delete");
  assert.equal(remove.payload.activity_id, "activity-one");
  assert.equal(remove.payload.expected_revision, 3);
  assert.equal(calls.filter(({operation}) => operation === "detail").length, 1);
  assert.equal(mounted.elements.detail.textContent.includes("Sin actividad registrada todavía."), true);
});


test("completed Task disables starting a new Work Session but keeps session history visible", async () => {
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail({
        status: "completed", sessions: [workSession({ended_at: "2026-10-05T19:00:00+02:00"})],
      });
      if (operation === "backlinks") return {items: []};
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  assert.equal(mounted.elements.detail.querySelector(".work-session-start").disabled, true);
  assert.equal(mounted.elements.detail.textContent.includes("1 h"), true);
});

test("Work Session disclosure defaults activity and active sessions open, keeps empty history closed, and preserves a manual close", async () => {
  const sessions = [
    workSession({id: "active"}),
    workSession({id: "with-activity", ended_at: "2026-10-05T19:00:00+02:00", activity: [{id: "a", created_at: "2026-10-05T19:00:00+02:00", text: "Avance"}]}),
    workSession({id: "empty", ended_at: "2026-10-05T20:00:00+02:00"}),
  ];
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail({sessions});
      if (operation === "backlinks") return {items: []};
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  assert.equal(mounted.elements.detail.textContent.includes("Avance"), true);
  assert.equal(mounted.elements.detail.textContent.includes("Sin actividad registrada todavía."), true);
  const opens = allByClass(mounted.elements.detail, "work-session-open");
  assert.equal(opens.map((item) => item.textContent).join(","), "Cerrar,Cerrar,Abrir");
  opens[1].click();
  await flush();
  assert.equal(allByClass(mounted.elements.detail, "work-session-open").map((item) => item.textContent).join(","), "Cerrar,Abrir,Abrir");
  allByClass(mounted.elements.detail, "work-session-open")[0].click();
  await flush();
  assert.equal(allByClass(mounted.elements.detail, "work-session-open").map((item) => item.textContent).join(","), "Abrir,Abrir,Abrir");
});

test("parent subtask checkbox fetches current child tokens for completion and reopen", async () => {
  const calls = [];
  let childStatus = "pending";
  const backlinks = () => ({items: [{source: {id: "child", name: "Hija", type: "task", properties: {status: childStatus}, tags: [], created_at: "x", updated_at: "x"}, snippets: [{block: {segments: [{text: "Tarea superior: [[Padre]]"}]}}]}]});
  const mounted = await mountNotes({requestNotes: async ({operation, payload}) => {
    calls.push({operation, payload});
    if (operation === "capabilities") return capabilities();
    if (operation === "detail") return payload.note_id === "child"
      ? {...taskDetail({status: childStatus}), note: {...taskDetail().note, id: "child", name: "Hija", properties: {status: childStatus}}, mutation: {revision: 8, source_hash: "c".repeat(64)}}
      : taskDetail();
    if (operation === "backlinks") return backlinks();
    if (operation === "task_status") { childStatus = payload.completed ? "completed" : "pending"; return {kind: "mutation", operation: payload.completed ? "task_completed" : "task_reopened", note_id: "child", history: {status: "COMMITTED"}, mutation: {revision: 9, source_hash: "d".repeat(64)}, status: childStatus, completed_at: null}; }
    return page();
  }});
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  mounted.elements.detail.querySelector(".note-subtask-toggle").click();
  await flush();
  assert.equal(calls.filter(({operation}) => operation === "detail").at(-1).payload.note_id, "child");
  assert.equal(calls.filter(({operation}) => operation === "task_status").at(-1).payload.completed, true);
  mounted.elements.detail.querySelector(".note-subtask-toggle").click();
  await flush();
  assert.equal(calls.filter(({operation}) => operation === "task_status").at(-1).payload.completed, false);
});

test("parent completion asks before sending task_status when subtasks remain open", async () => {
  const calls = [];
  const mounted = await mountNotes({confirmImpl: () => false, requestNotes: async ({operation, payload}) => {
    calls.push({operation, payload});
    if (operation === "capabilities") return capabilities();
    if (operation === "detail") return taskDetail();
    if (operation === "backlinks") return {items: [{source: {id: "child", name: "Abierta", type: "task", properties: {status: "pending"}, tags: [], created_at: "x", updated_at: "x"}, snippets: [{block: {segments: [{text: "Tarea superior: [[Padre]]"}]}}]}]};
    return page();
  }});
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  mounted.elements.detail.querySelector(".note-task-toggle").click();
  await flush();
  assert.equal(calls.some(({operation}) => operation === "task_status"), false);
});


test("parent completion confirms exact open-subtask count and mutates only the parent when accepted", async () => {
  const calls = [];
  const confirmations = [];
  const subtask = (id, name, status) => ({
    source: {id, name, type: "task", properties: {status}, tags: [], created_at: "x", updated_at: "x"},
    snippets: [{block: {segments: [{text: "Tarea superior: [[Padre]]"}]}}],
  });
  const mounted = await mountNotes({
    confirmImpl: (message) => { confirmations.push(message); return true; },
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail();
      if (operation === "backlinks") return {items: [
        subtask("open-one", "Abierta", "pending"),
        subtask("open-two", "En curso", "in_progress"),
        subtask("done", "Hecha", "completed"),
        subtask("cancelled", "Cancelada", "cancelled"),
      ]};
      if (operation === "task_status") return {
        kind: "mutation", operation: "task_completed", note_id: "task-odyssey",
        history: {status: "COMMITTED"}, mutation: {revision: 5, source_hash: "e".repeat(64)},
        status: "completed", completed_at: "2026-10-05T21:00:00+02:00",
      };
      return page();
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  mounted.elements.detail.querySelector(".note-task-toggle").click();
  await flush();

  assert.deepEqual(confirmations, ["Quedan 2 subtareas abiertas. ¿Completar la tarea de todos modos?"]);
  const lifecycleCalls = calls.filter(({operation}) => operation === "task_status");
  assert.equal(lifecycleCalls.length, 1);
  assert.equal(lifecycleCalls[0].payload.note_id, "task-odyssey");
  assert.equal(lifecycleCalls[0].payload.completed, true);
  assert.equal(lifecycleCalls.some(({payload}) => payload.note_id?.startsWith("open-")), false);
});


test("inline subtask creation sends one bounded parent mutation and refreshes the canonical backlink list", async () => {
  const calls = [];
  let created = false;
  const childBacklink = {
    source: {id: "child-new", name: "Preparar maletas", type: "task", properties: {status: "pending"}, tags: [], created_at: "x", updated_at: "x"},
    snippets: [{block: {segments: [{text: "Tarea superior: [[Trabajar en Odyssey]]"}]}}],
  };
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      calls.push({operation, payload});
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return taskDetail();
      if (operation === "backlinks") return {items: created ? [childBacklink] : []};
      if (operation === "task_subtask_create") {
        created = true;
        return {
          kind: "mutation", operation: "task_subtask_created", note_id: "child-new",
          history: {status: "COMMITTED"}, child: {id: "child-new", name: payload.title, status: "pending"},
        };
      }
      return created
        ? page({items: [pageItem("child-new", "Preparar maletas"), pageItem("task-odyssey", "Trabajar en Odyssey")], total: 2})
        : page({items: [pageItem("task-odyssey", "Trabajar en Odyssey")], total: 1, next_cursor: "old-cursor"});
    },
  });
  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-odyssey"}});
  await flush();
  const form = mounted.elements.detail.querySelector(".note-subtask-create-form");
  assert.ok(form);
  const input = form.querySelector("input");
  input.value = "  Preparar maletas  ";
  form.emit("submit");
  await flush();

  const create = calls.find(({operation}) => operation === "task_subtask_create");
  assert.ok(create);
  assert.deepEqual(Object.keys(create.payload).sort(), [
    "expected_revision", "expected_source_hash", "parent_note_id", "request_id", "title",
  ]);
  assert.equal(create.payload.parent_note_id, "task-odyssey");
  assert.equal(create.payload.title, "Preparar maletas");
  assert.equal(create.payload.expected_revision, 4);
  assert.equal(create.payload.expected_source_hash, "a".repeat(64));
  assert.equal(mounted.elements.detail.textContent.includes("Preparar maletas"), true);
  assert.equal(calls.filter(({operation}) => operation === "task_subtask_create").length, 1);

  mounted.elements.detail.querySelector(".note-view-header").children[0].click();
  await flush();
  assert.equal(mounted.elements.list.textContent.includes("Preparar maletas"), true);
  assert.equal(mounted.elements.status.textContent, "2 notas");
  const feedQueries = calls.filter(({operation}) => operation === "query");
  assert.equal(feedQueries.at(-1).payload.cursor, null);
});


function allByClass(root, className, found = []) {
  for (const child of root.children ?? []) {
    if ((child.className ?? "").split(" ").includes(className)) found.push(child);
    allByClass(child, className, found);
  }
  return found;
}


test("legacy Task checklist marker is hidden when it duplicates the Task action", async () => {
  const mounted = await mountNotes({
    requestNotes: async ({operation, payload}) => {
      if (operation === "capabilities") return capabilities();
      if (operation === "detail") return {
        kind: "detail",
        note: {
          id: payload.note_id, name: "pintar la pared", type: "task",
          properties: {status: "pending"}, created_at: "2026-10-05", updated_at: "2026-10-05", tags: [],
        },
        body_blocks: [{kind: "list_item", segments: [{text: "[ ] pintar la pared."}]}],
      };
      if (operation === "backlinks") return {items: []};
      return page();
    },
  });

  mounted.document.emit("odyssey:open-note", {detail: {note_id: "task-paint"}});
  await flush();

  const body = mounted.elements.detail.querySelector(".note-body");
  assert.ok(body);
  assert.equal(body.textContent.includes("pintar la pared."), true);
  assert.equal(body.textContent.includes("[ ]"), false);
});
