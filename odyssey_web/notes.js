/** In-memory presentation/state controller for the dependency-free Notes surface. */
import {NotesRequestError, requestNotes} from "./notes-client.js";

const TYPE_TOKENS = Object.freeze({concept: "◈", person: "●", project: "◆", task: "✓", document: "▤", journal_entry: "◐"});

/** Mount a read-only Notes surface that preserves its controller state while hidden. */
export function mountNotes(root, {endpoint = "/api/notes"} = {}) {
  const state = {query: "", filters: [], sort: "relevance", items: [], cursor: null, loading: false, current: null, back: [], forward: [], feedScroll: 0, historical: false};
  const search = root.querySelector("#notes-search");
  const list = root.querySelector("#notes-list");
  const detail = root.querySelector("#note-detail");
  const sort = root.querySelector("#notes-sort");
  const status = root.querySelector("#notes-status");

  async function load({reset = false, mode = "feed"} = {}) {
    if (state.loading || (!reset && !state.cursor)) return;
    state.loading = true;
    status.textContent = "Cargando…";
    try {
      const page = await requestNotes({endpoint, operation: "query", payload: {mode, query: state.query, filters: state.filters, sort: state.sort, cursor: reset ? null : state.cursor}});
      if (reset) state.items = [];
      state.items.push(...page.items);
      state.cursor = page.next_cursor;
      state.historical = page.mode === "snapshot";
      renderList();
      status.textContent = page.total ? `${page.total} notas` : "No hay notas";
    } catch (error) {
      if (error instanceof NotesRequestError && error.code === "STALE_CURSOR") { state.cursor = null; status.textContent = "Las notas cambiaron. Actualiza la búsqueda."; }
      else status.textContent = "No se han podido cargar las notas.";
    } finally { state.loading = false; }
  }
  function renderList() {
    list.replaceChildren(...state.items.map((note) => noteRow(note, () => open(note.id))));
    if (state.cursor) { const more = button("Cargar más", () => void load()); more.className = "notes-more"; list.append(more); }
  }
  async function open(id, {history = true} = {}) {
    try {
      const value = await requestNotes({endpoint, operation: "detail", payload: {note_id: id}});
      if (history && state.current) { state.back.push(state.current.note.id); state.forward = []; }
      state.current = value;
      state.feedScroll = list.scrollTop;
      renderDetail();
    } catch { status.textContent = "La nota ya no está disponible."; }
  }
  function renderDetail() {
    const value = state.current; if (!value) return;
    detail.hidden = false; list.hidden = true;
    const header = document.createElement("header"); header.className = "note-view-header";
    const back = button("‹", () => { detail.hidden = true; list.hidden = false; list.scrollTop = state.feedScroll; }); back.setAttribute("aria-label", "Volver a resultados");
    const title = document.createElement("h2"); title.append(typeBadge(value.note.type), document.createTextNode(value.note.name)); header.append(back, title);
    const controls = document.createElement("p"); controls.className = "note-history";
    const prev = button("←", () => { const id = state.back.pop(); if (id) { state.forward.push(value.note.id); void open(id, {history: false}); } }); prev.disabled = !state.back.length;
    const next = button("→", () => { const id = state.forward.pop(); if (id) { state.back.push(value.note.id); void open(id, {history: false}); } }); next.disabled = !state.forward.length; controls.append(prev, next);
    const properties = document.createElement("dl"); properties.className = "note-properties";
    const fields = Object.entries(value.note.properties); for (const [key, raw] of fields.slice(0, 6)) property(properties, key, raw);
    property(properties, "Creada", readableDate(value.note.created_at)); property(properties, "Actualizada", readableDate(value.note.updated_at));
    const tags = document.createElement("p"); tags.className = "note-tags"; tags.textContent = value.note.tags.map((tag) => `#${tag}`).join(" ");
    const body = document.createElement("article"); body.className = "note-body"; for (const line of value.body.split(/\n{2,}/)) { const paragraph = document.createElement("p"); paragraph.textContent = line; body.append(paragraph); }
    const links = document.createElement("section"); links.className = "note-links"; if (value.links.length) { const h = document.createElement("h3"); h.textContent = "Enlaces"; links.append(h); for (const link of value.links) { const linkButton = button(`${TYPE_TOKENS[link.target_type] ?? "○"} ${link.label}`, () => void open(link.target_id)); linkButton.className = "note-link"; links.append(linkButton); } }
    const backlinks = document.createElement("section"); backlinks.className = "note-backlinks"; const h = document.createElement("h3"); h.textContent = "Enlazada desde"; backlinks.append(h); void appendBacklinks(backlinks, value.note.id);
    detail.replaceChildren(header, controls, properties, tags, body, links, backlinks);
  }
  async function appendBacklinks(target, id) { try { const value = await requestNotes({endpoint, operation: "backlinks", payload: {note_id: id}}); if (!value.items.length) { target.append(document.createTextNode("Sin enlaces entrantes.")); return; } for (const item of value.items) { const row = button(`${item.source.name} · ${item.occurrences}`, () => void open(item.source.id)); row.className = "backlink"; target.append(row); const context = document.createElement("p"); context.className = "backlink-context"; context.textContent = item.context; target.append(context); } } catch { target.append(document.createTextNode("No se han podido cargar los enlaces entrantes.")); } }
  function searchLocal() { state.query = search.value; state.current = null; detail.hidden = true; list.hidden = false; void load({reset: true, mode: state.query.trim() ? "local" : "feed"}); }
  search.addEventListener("input", searchLocal);
  root.querySelector("#notes-intelligent")?.addEventListener("click", () => { state.query = search.value; void load({reset: true, mode: "intelligent"}); });
  sort.addEventListener("change", () => { state.sort = sort.value; void load({reset: true, mode: state.query.trim() ? "local" : "feed"}); });
  list.addEventListener("scroll", () => { if (list.scrollTop + list.clientHeight >= list.scrollHeight - 80) void load(); });
  void load({reset: true});
  return {state, refresh: () => load({reset: true, mode: state.query.trim() ? "local" : "feed"})};
}
function noteRow(note, action) { const row = button("", action); row.className = "note-row"; const title = document.createElement("strong"); title.append(typeBadge(note.type), document.createTextNode(note.name)); const meta = document.createElement("span"); meta.textContent = `Actualizada ${readableDate(note.updated_at)}`; row.append(title, meta); return row; }
function typeBadge(type) { const badge = document.createElement("span"); badge.className = "note-type type-" + type; badge.textContent = TYPE_TOKENS[type] ?? "○"; badge.setAttribute("aria-label", type); return badge; }
function property(parent, key, value) { const term = document.createElement("dt"); term.textContent = key.replaceAll("_", " "); const description = document.createElement("dd"); description.textContent = Array.isArray(value) ? value.join(", ") : String(value); parent.append(term, description); }
function button(label, action) { const value = document.createElement("button"); value.type = "button"; value.textContent = label; value.addEventListener("click", action); return value; }
function readableDate(value) { const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString(); }
