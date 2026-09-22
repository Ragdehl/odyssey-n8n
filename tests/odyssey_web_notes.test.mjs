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
  constructor() { this._elements = new Map(); this._listeners = new Map(); }
  createElement(tagName) { return new FakeElement(tagName); }
  createElementNS(_namespace, tagName) { return new FakeElement(tagName); }
  createTextNode(value) { return new FakeText(value); }
  querySelector(selector) { return this._elements.get(selector) ?? null; }
  addEventListener(type, listener) { this._listeners.set(type, listener); }
  emit(type, event = {}) { this._listeners.get(type)?.(event); }
}

function matches(element, selector) {
  if (selector.startsWith(".")) return (element.className ?? "").split(" ").includes(selector.slice(1));
  if (selector.startsWith("#")) return element.id === selector.slice(1);
  return element.tagName === selector;
}

function pageItem(id, name = id) {
  return {id, name, type: "person", updated_at: "2026-09-22T10:00:00Z", tags: [], properties: {}};
}

function page({mode = "feed", items = [pageItem("a", "Resultado A")], total = items.length, applied_filters = []} = {}) {
  return {mode, items, total, next_cursor: null, sort: "relevance", applied_filters, snapshot_offset: 0};
}

function detail(id, name = id) {
  return {
    kind: "detail",
    note: {id, name, type: "person", properties: {}, created_at: "2026-09-20", updated_at: "2026-09-22", tags: []},
    body_blocks: [],
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function mountNotes({requestNotes}) {
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
  globalThis.__odysseyTestNotesClient = {NotesRequestError, requestNotes};
  const source = await readFile(new URL("../odyssey_web/notes.js", import.meta.url), "utf8");
  const testable = source.replace(
    'import {NotesRequestError, requestNotes} from "./notes-client.js";',
    "const {NotesRequestError, requestNotes} = globalThis.__odysseyTestNotesClient;",
  );
  const {mountNotes: mount} = await import(
    `data:text/javascript;base64,${Buffer.from(`${testable}\n// fixture ${fixtureNumber += 1}`).toString("base64")}`,
  );
  const controller = mount(root);
  await flush();
  return {controller, document, elements};
}

function capabilities() {
  return {types: [{id: "person", name: "Persona"}], fields: []};
}

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
  mounted.elements.list.children[0].click();
  await flush();
  mounted.elements.detail.querySelector("button").click();
  await flush();

  assert.equal(mounted.elements.status.textContent.includes("2 notas afectadas"), true);
  assert.equal(mounted.elements.status.querySelector(".notes-show-all").textContent, "Ver todas");
  assert.equal(mounted.elements.list.textContent, "MartaPersona · actualizada 9/22/2026ElenaPersona · actualizada 9/22/2026");
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
  mounted.elements.list.children[0].click();
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
  mounted.elements.list.children[0].click();
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
