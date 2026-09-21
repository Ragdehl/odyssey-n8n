/** In-memory presentation/state controller for the dependency-free Notes application view. */
import {NotesRequestError, requestNotes} from "./notes-client.js";

const TYPE_PRESENTATION = Object.freeze({
  concept: {label: "Concepto", paths: ["M12 3a6 6 0 0 0-3.8 10.6c.8.6 1.3 1.5 1.5 2.4h4.6c.2-.9.7-1.8 1.5-2.4A6 6 0 0 0 12 3Z", "M10 19h4M10.5 22h3"]},
  project: {label: "Proyecto", paths: ["m12 3 8 4.5-8 4.5L4 7.5 12 3Z", "m4 12.5 8 4.5 8-4.5", "m4 17 8 4.5 8-4.5"]},
  task: {label: "Tarea", paths: ["M5 4h14v16H5z", "m8 12 2.5 2.5L16 9"]},
  store: {label: "Tienda", paths: ["M4 10h16v10H4z", "M3 6h18l-1 4H4L3 6Z", "M8 20v-6h5v6"]},
  product: {label: "Producto", paths: ["m4 7 8-4 8 4v10l-8 4-8-4V7Z", "m4 7 8 4 8-4", "M12 11v10"]},
  purchase: {label: "Compra", paths: ["M6 3h12v18H6z", "M9 8h6M9 12h6M9 16h4", "M8 3v3m8-3v3"]},
  recipe: {label: "Receta", paths: ["M4 12h16", "M6 12a6 6 0 0 0 12 0", "M8 5v4m4-5v5m4-4v4"]},
  document: {label: "Documento", paths: ["M7 3h7l4 4v14H7z", "M14 3v5h4", "M10 12h5M10 16h5"]},
  person: {label: "Persona", paths: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M5 21a7 7 0 0 1 14 0"]},
  journal_entry: {label: "Entrada de diario", paths: ["M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 1V4Z", "M8 8h7M8 12h7M8 16h5"]},
});
const GENERAL_FIELDS = new Set(["type", "tags", "created_at", "updated_at"]);

/** Mount the read-only Notes application while retaining its state while the view is inactive. */
export function mountNotes(root, {endpoint = "/api/notes"} = {}) {
  const state = {
    query: "", filters: [], sort: "relevance", items: [], cursor: null, loading: false,
    current: null, back: [], forward: [], feedScroll: 0, historical: false, mode: "feed",
    snapshot: null, capabilities: {types: [], fields: []},
  };
  const search = root.querySelector("#notes-search");
  const searchForm = root.querySelector("#notes-search-form");
  const list = root.querySelector("#notes-list");
  const listView = root.querySelector("#notes-list-view");
  const detail = root.querySelector("#note-detail");
  const searchDock = root.querySelector("#notes-search-form");
  const sort = root.querySelector("#notes-sort");
  const status = root.querySelector("#notes-status");
  const chips = root.querySelector("#notes-filter-chips");
  const filterButton = root.querySelector("#notes-filters");
  const filterSheet = document.querySelector("#notes-filter-sheet");
  const filterForm = document.querySelector("#notes-filter-form");
  const filterFields = document.querySelector("#notes-filter-fields");

  function fieldFormat(field) {
    return state.capabilities.fields.find((candidate) => candidate.id === field)?.format ?? null;
  }

  async function load({reset = false, mode = state.mode, snapshotIds = state.snapshot?.note_ids ?? [], throwOnError = false} = {}) {
    if (state.loading || (!reset && !state.cursor)) return;
    state.loading = true;
    status.textContent = "Cargando…";
    try {
      const page = await requestNotes({endpoint, operation: "query", payload: {
        mode, query: state.query, filters: state.filters, sort: state.sort,
        cursor: reset ? null : state.cursor, snapshot_ids: snapshotIds,
      }});
      if (reset) state.items = [];
      if (page.mode === "snapshot" && state.snapshot) {
        const available = new Map(page.items.map((item) => [item.id, item]));
        const offset = page.snapshot_offset ?? 0;
        const ids = state.snapshot.note_ids.slice(offset, offset + 40);
        state.items.push(...ids.map((id) => available.get(id) ?? {id, unavailable: true}));
      } else {
        state.items.push(...page.items);
      }
      state.cursor = page.next_cursor;
      state.historical = page.mode === "snapshot";
      state.mode = page.mode;
      renderList();
      renderStatus(page.total);
    } catch (error) {
      if (error instanceof NotesRequestError && error.code === "STALE_CURSOR") {
        state.cursor = null;
        status.textContent = "Las notas cambiaron. Actualiza la búsqueda.";
      } else {
        status.textContent = "No se han podido cargar las notas.";
      }
      if (throwOnError) throw error;
    } finally {
      state.loading = false;
    }
  }

  async function loadCapabilities() {
    try {
      state.capabilities = await requestNotes({endpoint, operation: "capabilities"});
      updateControlAvailability();
    } catch {
      filterButton.disabled = true;
    }
  }

  function renderStatus(total) {
    if (!state.historical || !state.snapshot) {
      status.textContent = total ? `${total} notas` : "No hay notas";
      return;
    }
    const count = state.snapshot.truncated
      ? `${state.snapshot.note_ids.length} de ${state.snapshot.total}`
      : state.snapshot.total;
    if (state.snapshot.kind === "affected_notes") {
      status.textContent = `${count} notas afectadas`;
      return;
    }
    status.replaceChildren(document.createTextNode(`Resultado histórico · ${count} notas`));
    const rerun = button("Actualizar búsqueda", () => void rerunHistorical());
    rerun.className = "notes-rerun";
    status.append(document.createTextNode(" · "), rerun);
  }

  function renderList() {
    list.replaceChildren(...state.items.map((note) => (
      note.unavailable ? unavailableRow(note.id) : noteRow(note, () => void open(note.id))
    )));
    if (state.cursor) {
      const more = button("Cargar más", () => void load());
      more.className = "notes-more";
      list.append(more);
    }
    renderFilterChips();
    updateControlAvailability();
  }

  function updateControlAvailability() {
    sort.disabled = state.historical;
    filterButton.disabled = state.historical || !state.capabilities.types.length;
  }

  function renderFilterChips() {
    chips.replaceChildren(...state.filters.map((filter, index) => {
      const value = filterValueLabel(filter);
      if (state.historical) {
        const chip = document.createElement("span");
        chip.className = "notes-filter-chip";
        chip.textContent = `${filterLabel(filter.field)}: ${value}`;
        return chip;
      }
      const chip = button(`${filterLabel(filter.field)}: ${value} ×`, () => {
        state.filters.splice(index, 1);
        void refreshCurrentList();
      });
      chip.className = "notes-filter-chip";
      chip.setAttribute("aria-label", `Eliminar filtro ${filterLabel(filter.field)}: ${value}`);
      return chip;
    }));
  }

  async function refreshCurrentList() {
    state.current = null;
    showList();
    await load({reset: true, mode: state.query.trim() ? "local" : "feed"});
  }

  async function runIntelligentSearch({throwOnError = false} = {}) {
    if (state.loading) return;
    state.loading = true;
    status.textContent = "Buscando…";
    const query = state.query;
    const explicitFilters = uniqueFilters(state.filters);
    try {
      const page = await requestNotes({endpoint, operation: "intelligent", payload: {
        query, filters: explicitFilters,
      }});
      if (!filtersAreRepresentable(page.applied_filters)) {
        throw new NotesRequestError("Odyssey devolvió filtros que no se pueden editar con seguridad.");
      }
      state.filters = uniqueFilters(page.applied_filters);
      state.items = page.items;
      state.cursor = page.next_cursor;
      state.current = null;
      state.historical = false;
      state.snapshot = null;
      state.mode = page.mode;
      state.sort = page.sort;
      sort.value = page.sort;
      showList();
      renderList();
      renderStatus(page.total);
    } catch (error) {
      status.textContent = error instanceof NotesRequestError && error.message.includes("filtros")
        ? "No se pueden mostrar filtros de esta búsqueda con seguridad."
        : "No se ha podido completar la búsqueda inteligente.";
      if (throwOnError) throw error;
    } finally {
      state.loading = false;
    }
  }

  function filtersAreRepresentable(filters) {
    const selectedType = filters.find((filter) => filter.field === "type" && filter.op === "eq")?.value;
    return filters.every((filter) => {
      if (filter.field === "type") return filter.op === "eq" && state.capabilities.types.some((type) => type.id === filter.value);
      if (filter.field === "tags") return filter.op === "contains" && typeof filter.value === "string";
      if (["created_at", "updated_at"].includes(filter.field)) return ["gte", "lt", "lte"].includes(filter.op) && typeof filter.value === "string";
      const field = state.capabilities.fields.find((candidate) => candidate.id === filter.field);
      if (!field || !field.operators.includes(filter.op) || !field.applies_to.includes(selectedType)) return false;
      if (field.value_type === "date") return ["gte", "lt", "lte"].includes(filter.op) && typeof filter.value === "string";
      if (field.value_type === "integer") return ["gte", "lte"].includes(filter.op) && Number.isInteger(filter.value);
      if (field.value_type === "array[string]") return filter.op === "contains" && typeof filter.value === "string";
      return field.value_type === "string" && filter.op === "eq" && typeof filter.value === "string";
    });
  }

  async function rerunHistorical() {
    if (!state.snapshot || state.snapshot.kind === "affected_notes") return;
    const saved = state.snapshot;
    const historicalState = {
      items: state.items,
      cursor: state.cursor,
      current: state.current,
      back: state.back,
      forward: state.forward,
      feedScroll: state.feedScroll,
      mode: state.mode,
      sort: state.sort,
    };
    state.query = saved.query;
    state.filters = saved.filters;
    state.historical = false;
    state.snapshot = null;
    search.value = state.query;
    try {
      await runIntelligentSearch({throwOnError: true});
    } catch {
      state.items = historicalState.items;
      state.cursor = historicalState.cursor;
      state.current = historicalState.current;
      state.back = historicalState.back;
      state.forward = historicalState.forward;
      state.feedScroll = historicalState.feedScroll;
      state.mode = historicalState.mode;
      state.sort = historicalState.sort;
      state.historical = true;
      state.snapshot = saved;
      search.value = saved.query;
      sort.value = saved.sort;
      showList();
      renderList();
      status.textContent = "No se pueden reutilizar estos filtros históricos.";
    }
  }

  async function open(id, {history = true} = {}) {
    try {
      const value = await requestNotes({endpoint, operation: "detail", payload: {note_id: id}});
      if (history && state.current) {
        state.back.push(state.current.note.id);
        state.forward = [];
      }
      state.current = value;
      state.feedScroll = list.scrollTop;
      status.textContent = "";
      renderDetail();
    } catch {
      status.textContent = "No se ha podido abrir la nota.";
    }
  }

  function showList() {
    detail.hidden = true;
    listView.hidden = false;
    searchDock.hidden = false;
    list.scrollTop = state.feedScroll;
  }

  function renderDetail() {
    const value = state.current;
    if (!value) return;
    detail.hidden = false;
    listView.hidden = true;
    searchDock.hidden = true;
    const header = document.createElement("header");
    header.className = "note-view-header";
    const back = button("‹ Notas", () => {
      state.current = null;
      state.back = [];
      state.forward = [];
      showList();
    });
    back.setAttribute("aria-label", "Volver a resultados de notas");
    const title = document.createElement("h2");
    title.append(typeBadge(value.note.type), document.createTextNode(value.note.name));
    header.append(back, title);
    const controls = document.createElement("p");
    controls.className = "note-history";
    if (state.back.length || state.forward.length) {
      if (state.back.length) {
        controls.append(button("←", () => {
          const id = state.back.pop();
          if (id) {
            state.forward.push(value.note.id);
            void open(id, {history: false});
          }
        }));
      }
      if (state.forward.length) {
        controls.append(button("→", () => {
          const id = state.forward.pop();
          if (id) {
            state.back.push(value.note.id);
            void open(id, {history: false});
          }
        }));
      }
    }
    const properties = document.createElement("dl");
    properties.className = "note-properties";
    for (const [key, raw] of Object.entries(value.note.properties).slice(0, 6)) {
      property(properties, key, raw);
    }
    property(properties, "Creada", readableDate(value.note.created_at));
    property(properties, "Actualizada", readableDate(value.note.updated_at));
    const tags = document.createElement("p");
    tags.className = "note-tags";
    tags.textContent = value.note.tags.map((tag) => `#${tag}`).join(" ");
    const body = document.createElement("article");
    body.className = "note-body";
    renderBody(body, value.body_blocks, open);
    const backlinks = document.createElement("section");
    backlinks.className = "note-backlinks";
    const backlinksHeading = document.createElement("h3");
    backlinksHeading.textContent = "Enlazada desde";
    backlinks.append(backlinksHeading);
    void appendBacklinks(backlinks, value.note.id);
    detail.replaceChildren(header, controls, properties, tags, body, backlinks);
  }

  async function appendBacklinks(target, id) {
    try {
      const value = await requestNotes({endpoint, operation: "backlinks", payload: {note_id: id}});
      if (!value.items.length) {
        target.append(document.createTextNode("Sin enlaces entrantes."));
        return;
      }
      for (const item of value.items) {
        const row = button("", () => void open(item.source.id));
        row.className = "backlink";
        row.setAttribute("aria-label", `Abrir ${typeLabel(item.source.type)} ${item.source.name}`);
        row.append(typeIcon(item.source.type), document.createTextNode(`${item.source.name} · ${item.occurrences}`));
        target.append(row);
        for (const snippet of item.snippets) {
          const occurrence = document.createElement("section");
          occurrence.className = "backlink-occurrence";
          if (snippet.heading) {
            const heading = document.createElement("p");
            heading.className = "backlink-heading";
            appendBodySegments(heading, humanizeBacklinkHeading(snippet.heading), open);
            occurrence.append(heading);
          }
          const context = document.createElement("p");
          context.className = "backlink-context";
          appendBodySegments(context, snippet.block.segments, open);
          occurrence.append(context);
          target.append(occurrence);
        }
        if (item.snippets_truncated) {
          const more = document.createElement("p");
          more.className = "backlink-more";
          more.textContent = `Se muestran ${item.snippets.length} de ${item.occurrences} menciones.`;
          target.append(more);
        }
      }
    } catch {
      target.append(document.createTextNode("No se han podido cargar los enlaces entrantes."));
    }
  }

  function openFilterSheet() {
    if (!filterSheet || !filterForm || !filterFields) return;
    syncFilterForm();
    filterSheet.showModal();
  }

  function syncFilterForm() {
    filterForm.reset();
    const type = state.filters.find((filter) => filter.field === "type" && filter.op === "eq");
    const tags = state.filters.filter((filter) => filter.field === "tags" && filter.op === "contains");
    setFormValue("filter-type", type?.value ?? "");
    setFormValue("filter-tags", tags.map((filter) => filter.value).join(", "));
    syncRange("created_at", "filter-created");
    syncRange("updated_at", "filter-updated");
    syncTypeSpecificFields(typeof type?.value === "string" ? type.value : "");
  }

  function syncRange(field, prefix) {
    const lower = state.filters.find((filter) => filter.field === field && filter.op === "gte");
    const upper = state.filters.find((filter) => filter.field === field && ["lt", "lte"].includes(filter.op));
    const dateTime = fieldFormat(field) === "date-time";
    setFormValue(`${prefix}-from`, displayRangeValue(lower?.value, dateTime));
    setFormValue(`${prefix}-to`, upper?.op === "lt" && !dateTime ? previousDatePart(upper?.value) : displayRangeValue(upper?.value, dateTime));
  }

  function renderFilterFields() {
    filterFields.replaceChildren(
      selectField("filter-type", "Tipo de nota", state.capabilities.types),
      textField("filter-tags", "Etiquetas", "Una o varias etiquetas separadas por comas"),
      rangeField("filter-created", lifecycleLabel("created_at"), "created_at", fieldFormat("created_at") === "date-time" ? "datetime-local" : "date"),
      rangeField("filter-updated", lifecycleLabel("updated_at"), "updated_at", fieldFormat("updated_at") === "date-time" ? "datetime-local" : "date"),
      extraFieldsContainer(),
    );
    filterFields.querySelector("#filter-type")?.addEventListener("change", (event) => {
      renderTypeSpecificFields(event.currentTarget.value);
    });
  }

  function extraFieldsContainer() {
    const container = document.createElement("section");
    container.id = "notes-type-specific-filters";
    container.className = "notes-type-specific-filters";
    return container;
  }

  function renderTypeSpecificFields(noteType) {
    const container = filterFields?.querySelector("#notes-type-specific-filters");
    if (!container) return;
    container.replaceChildren();
    const fields = state.capabilities.fields.filter((field) => (
      !GENERAL_FIELDS.has(field.id) && field.applies_to.includes(noteType)
    ));
    if (!fields.length) {
      if (noteType) {
        const message = document.createElement("p");
        message.className = "notes-type-specific-empty";
        message.textContent = "Este tipo no tiene propiedades específicas.";
        container.append(message);
      }
      return;
    }
    const heading = document.createElement("h3");
    heading.textContent = "Propiedades de este tipo";
    container.append(heading);
    for (const field of fields) {
      if (field.value_type === "date") {
        container.append(rangeField(`filter-${field.id}`, filterLabel(field.id), field.id));
      } else if (field.value_type === "integer") {
        container.append(numberRangeField(`filter-${field.id}`, filterLabel(field.id), field.id));
      } else if (field.value_type === "array[string]" && field.operators.includes("contains")) {
        container.append(textField(`filter-${field.id}`, filterLabel(field.id), "Valores separados por comas", field.id));
      } else if (field.value_type === "string" && field.operators.includes("eq")) {
        container.append(textField(`filter-${field.id}`, filterLabel(field.id), "Coincidencia exacta", field.id));
      }
    }
  }

  function syncTypeSpecificFields(noteType) {
    renderTypeSpecificFields(noteType);
    for (const field of state.capabilities.fields) {
      if (GENERAL_FIELDS.has(field.id) || !field.applies_to.includes(noteType)) continue;
      const prefix = `filter-${field.id}`;
      if (field.value_type === "date") {
        syncRange(field.id, prefix);
      } else if (field.value_type === "integer") {
        const lower = state.filters.find((filter) => filter.field === field.id && filter.op === "gte");
        const upper = state.filters.find((filter) => filter.field === field.id && filter.op === "lte");
        setFormValue(`${prefix}-from`, lower?.value ?? "");
        setFormValue(`${prefix}-to`, upper?.value ?? "");
      } else if (field.value_type === "array[string]") {
        setFormValue(prefix, state.filters.filter((filter) => filter.field === field.id && filter.op === "contains").map((filter) => filter.value).join(", "));
      } else if (field.value_type === "string") {
        setFormValue(prefix, state.filters.find((filter) => filter.field === field.id && filter.op === "eq")?.value ?? "");
      }
    }
  }

  function applyFilters() {
    const next = [];
    const type = formValue("filter-type");
    if (type) next.push({field: "type", op: "eq", value: type});
    for (const tag of splitValues(formValue("filter-tags"))) next.push({field: "tags", op: "contains", value: tag});
    appendDateRange(next, "created_at", "filter-created");
    appendDateRange(next, "updated_at", "filter-updated");
    for (const field of state.capabilities.fields) {
      if (GENERAL_FIELDS.has(field.id) || !field.applies_to.includes(type)) continue;
      const prefix = `filter-${field.id}`;
      if (field.value_type === "date") {
        appendDateRange(next, field.id, prefix);
      } else if (field.value_type === "integer") {
        appendNumberRange(next, field.id, prefix);
      } else if (field.value_type === "array[string]" && field.operators.includes("contains")) {
        for (const value of splitValues(formValue(prefix))) next.push({field: field.id, op: "contains", value});
      } else if (field.value_type === "string" && field.operators.includes("eq")) {
        const value = formValue(prefix);
        if (value) next.push({field: field.id, op: "eq", value});
      }
    }
    state.filters = next;
    filterSheet?.close();
    void refreshCurrentList();
  }

  function appendDateRange(target, field, prefix) {
    const from = formValue(`${prefix}-from`);
    const to = formValue(`${prefix}-to`);
    const dateTime = fieldFormat(field) === "date-time";
    if (from) target.push({field, op: "gte", value: dateTime ? timezoneAwareDateTime(from) : from});
    if (to) target.push({field, op: dateTime ? "lte" : "lt", value: dateTime ? timezoneAwareDateTime(to) : nextDate(to)});
  }

  function appendNumberRange(target, field, prefix) {
    const from = formValue(`${prefix}-from`);
    const to = formValue(`${prefix}-to`);
    if (from !== "") target.push({field, op: "gte", value: Number(from)});
    if (to !== "") target.push({field, op: "lte", value: Number(to)});
  }

  function searchLocal() {
    state.query = search.value;
    state.current = null;
    state.historical = false;
    state.snapshot = null;
    showList();
    void load({reset: true, mode: state.query.trim() ? "local" : "feed"});
  }

  search.addEventListener("input", searchLocal);
  searchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    state.query = search.value;
    void runIntelligentSearch();
  });
  sort.addEventListener("change", () => {
    state.sort = sort.value;
    void refreshCurrentList();
  });
  filterButton?.addEventListener("click", openFilterSheet);
  document.querySelector("#notes-filter-close")?.addEventListener("click", () => filterSheet?.close());
  document.querySelector("#notes-filter-clear")?.addEventListener("click", () => {
    state.filters = [];
    filterForm?.reset();
    filterFields?.querySelector("#notes-type-specific-filters")?.replaceChildren();
    filterSheet?.close();
    void refreshCurrentList();
  });
  filterForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    applyFilters();
  });
  document.addEventListener("odyssey:open-note-snapshot", (event) => {
    const snapshot = event.detail;
    if (!snapshot || !Array.isArray(snapshot.note_ids)) return;
    const isAffected = snapshot.kind === "affected_notes";
    state.query = isAffected ? "" : snapshot.query;
    state.filters = isAffected ? [] : snapshot.filters;
    state.sort = isAffected ? "relevance" : snapshot.sort;
    state.historical = true;
    state.snapshot = snapshot;
    state.current = null;
    showList();
    sort.value = state.sort;
    search.value = state.query;
    void load({reset: true, mode: "snapshot", snapshotIds: snapshot.note_ids});
  });
  list.addEventListener("scroll", () => {
    if (list.scrollTop + list.clientHeight >= list.scrollHeight - 80) void load();
  });
  void (async () => {
    await loadCapabilities();
    renderFilterFields();
    await load({reset: true});
  })();
  return {state, refresh: () => refreshCurrentList()};
}

function noteRow(note, action) {
  const row = button("", action);
  row.className = "note-row";
  const title = document.createElement("strong");
  title.append(typeBadge(note.type), document.createTextNode(note.name));
  const meta = document.createElement("span");
  meta.textContent = `${typeLabel(note.type)} · actualizada ${readableDate(note.updated_at)}`;
  row.append(title, meta);
  return row;
}
function unavailableRow(id) {
  const row = document.createElement("div");
  row.className = "note-row note-unavailable";
  const title = document.createElement("strong");
  title.textContent = "Nota ya no disponible";
  const meta = document.createElement("span");
  meta.textContent = "Resultado histórico";
  row.append(title, meta);
  row.dataset.noteId = id;
  return row;
}
function renderBody(parent, blocks, open) {
  if (!blocks.length) {
    const empty = document.createElement("p");
    empty.className = "note-empty-body";
    empty.textContent = "Todavía no hay información adicional.";
    parent.append(empty);
    return;
  }
  let list = null;
  for (const block of blocks) {
    if (block.kind === "list_item") {
      if (!list) {
        list = document.createElement("ul");
        parent.append(list);
      }
      const item = document.createElement("li");
      appendBodySegments(item, block.segments, open);
      list.append(item);
      continue;
    }
    list = null;
    const element = document.createElement(block.kind === "heading" ? "h3" : "p");
    appendBodySegments(element, block.segments, open);
    parent.append(element);
  }
}
function appendBodySegments(parent, segments, open) {
  for (const segment of segments) {
    if (!segment.target_id) {
      parent.append(document.createTextNode(segment.text));
      continue;
    }
    const link = document.createElement("a");
    link.className = `note-inline-link type-${segment.target_type}`;
    link.href = `#note-${encodeURIComponent(segment.target_id)}`;
    link.setAttribute("aria-label", `${typeLabel(segment.target_type)}: ${segment.text}`);
    link.append(typeIcon(segment.target_type), document.createTextNode(segment.text));
    link.addEventListener("click", (event) => {
      event.preventDefault();
      void open(segment.target_id);
    });
    parent.append(link);
  }
}
function humanizeBacklinkHeading(segments) {
  const raw = segments.map((segment) => segment.text).join("");
  const match = /^Added (\d{2})-(\d{2})-(\d{4})$/.exec(raw);
  return match ? [{text: `${match[1]}/${match[2]}/${match[3]}`}] : segments;
}
function typeBadge(type) {
  const badge = document.createElement("span");
  badge.className = `note-type type-${type}`;
  badge.append(typeIcon(type));
  badge.setAttribute("aria-label", typeLabel(type));
  return badge;
}
function typeIcon(type) {
  const presentation = TYPE_PRESENTATION[type] ?? {paths: ["M5 5h14v14H5z", "M8 8h8M8 12h8M8 16h5"]};
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  for (const pathData of presentation.paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    icon.append(path);
  }
  return icon;
}
function typeLabel(type) { return TYPE_PRESENTATION[type]?.label ?? type.replaceAll("_", " "); }
function property(parent, key, value) {
  const term = document.createElement("dt");
  term.textContent = key.replaceAll("_", " ");
  const description = document.createElement("dd");
  description.textContent = Array.isArray(value) ? value.join(", ") : String(value);
  parent.append(term, description);
}
function button(label, action) {
  const value = document.createElement("button");
  value.type = "button";
  value.textContent = label;
  value.addEventListener("click", action);
  return value;
}
function selectField(id, label, options) {
  const wrapper = document.createElement("label");
  wrapper.className = "filter-field";
  wrapper.textContent = label;
  const select = document.createElement("select");
  select.id = id;
  select.name = id;
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Todos";
  select.append(blank);
  for (const option of options) {
    const item = document.createElement("option");
    item.value = option.id;
    item.textContent = option.name;
    select.append(item);
  }
  wrapper.append(select);
  return wrapper;
}
function textField(id, label, hint = "", field = "") {
  const wrapper = document.createElement("label");
  wrapper.className = "filter-field";
  wrapper.textContent = label;
  const input = document.createElement("input");
  input.id = id;
  input.name = id;
  input.type = "text";
  input.placeholder = hint;
  if (field) input.dataset.field = field;
  wrapper.append(input);
  return wrapper;
}
function rangeField(prefix, label, field = "", inputType = "date") {
  const group = document.createElement("fieldset");
  group.className = "filter-range";
  const legend = document.createElement("legend");
  legend.textContent = label;
  group.append(legend, dateInput(`${prefix}-from`, "Desde", field, inputType), dateInput(`${prefix}-to`, "Hasta", field, inputType));
  return group;
}
function dateInput(id, label, field, inputType = "date") {
  const wrapper = document.createElement("label");
  wrapper.textContent = label;
  const input = document.createElement("input");
  input.id = id;
  input.name = id;
  input.type = inputType;
  if (field) input.dataset.field = field;
  wrapper.append(input);
  return wrapper;
}
function numberRangeField(prefix, label, field) {
  const group = document.createElement("fieldset");
  group.className = "filter-range";
  const legend = document.createElement("legend");
  legend.textContent = label;
  group.append(legend);
  for (const [suffix, text] of [["from", "Mínimo"], ["to", "Máximo"]]) {
    const wrapper = document.createElement("label");
    wrapper.textContent = text;
    const input = document.createElement("input");
    input.id = `${prefix}-${suffix}`;
    input.name = input.id;
    input.type = "number";
    input.dataset.field = field;
    wrapper.append(input);
    group.append(wrapper);
  }
  return group;
}
function filterLabel(field) {
  return ({type: "Tipo", tags: "Etiqueta", created_at: "Creada", updated_at: "Actualizada", entry_date: "Fecha de la entrada"})[field] ?? field.replaceAll("_", " ");
}
function filterValueLabel(filter) {
  if (filter.field === "type" && typeof filter.value === "string") return typeLabel(filter.value);
  return Array.isArray(filter.value) ? filter.value.join(", ") : String(filter.value);
}
function uniqueFilters(filters) {
  const seen = new Set();
  return filters.filter((filter) => {
    const key = JSON.stringify([filter.field, filter.op, filter.value]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function lifecycleLabel(field) { return `${filterLabel(field)} · hora local`; }
function formValue(id) { return document.querySelector(`#${id}`)?.value?.trim() ?? ""; }
function setFormValue(id, value) { const input = document.querySelector(`#${id}`); if (input) input.value = value; }
function splitValues(value) { return value.split(",").map((item) => item.trim()).filter(Boolean); }
function nextDate(value) { const date = new Date(`${value}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + 1); return date.toISOString().slice(0, 10); }
function datePart(value) { return typeof value === "string" ? value.slice(0, 10) : ""; }
function previousDatePart(value) { if (typeof value !== "string" || value.length < 10) return ""; const date = new Date(`${value.slice(0, 10)}T00:00:00Z`); date.setUTCDate(date.getUTCDate() - 1); return date.toISOString().slice(0, 10); }
function displayRangeValue(value, dateTime) { return dateTime ? localDateTimePart(value) : datePart(value); }
function localDateTimePart(value) { if (typeof value !== "string") return ""; const date = new Date(value); if (Number.isNaN(date.valueOf())) return ""; const part = (number) => String(number).padStart(2, "0"); return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())}T${part(date.getHours())}:${part(date.getMinutes())}`; }
function timezoneAwareDateTime(value) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? "" : date.toISOString(); }
function readableDate(value) { const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString(); }
