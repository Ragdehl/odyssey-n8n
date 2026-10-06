/** In-memory presentation/state controller for the dependency-free Notes application view. */
import {NotesRequestError, requestNotes} from "./notes-client.js";

const ACTION_ICONS = Object.freeze({
  chat: ["M21 12a8 8 0 0 1-8 8H7l-4 2 1.3-4.2A8 8 0 1 1 21 12Z"],
  notes: ["M6 3h9l3 3v15H6z", "M14 3v5h4", "M9 12h6M9 16h6"],
  calendar: ["M5 5h14v14H5z", "M8 3v4M16 3v4M5 9h14", "M9 13h2v2H9z"],
  edit: ["M4 20l4.5-1 10-10-3.5-3.5-10 10L4 20Z", "m13.5-15.5 3.5 3.5"],
  delete: ["M5 7h14", "M9 7V4h6v3", "M8 10v8M12 10v8M16 10v8", "M6 7l1 14h10l1-14"],
  add: ["M12 5v14M5 12h14"],
  play: ["M8 5v14l11-7L8 5Z"],
  stop: ["M7 7h10v10H7z"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  chevronUp: ["m7 14 5-5 5 5"],
  chevronDown: ["m7 10 5 5 5-5"],
  check: ["m5 12 4 4L19 6"],
  close: ["M7 7l10 10M17 7 7 17"],
  more: ["M5 12h.01M12 12h.01M19 12h.01"],
  openNote: ["M6 3h9l3 3v15H6z", "M14 3v5h4", "M10 15h7", "m14 12 3 3-3 3"],
  send: ["M4 4l17 8-17 8 3-8-3-8Z", "M7 12h14"],
});

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
  calendar_day: {label: "Día de calendario", paths: ["M5 4h14v16H5z", "M8 2v4m8-4v4M5 9h14", "M9 13h2v2H9z"]},
});
const TYPE_DESCRIPTIONS_ES = Object.freeze({
  concept: "Tema, idea o concepto identificable que puede acumular información y relacionarse con otras notas.",
  project: "Proyecto o ámbito de trabajo orientado a un objetivo que puede acumular información y tareas.",
  task: "Compromiso o acción gestionada por Tareas, con estado, planificación temporal y contexto relacionado.",
  document: "Documento o archivo que merece representarse como un elemento de conocimiento independiente.",
  person: "Persona con una identidad reutilizable que puede relacionarse con tus notas y conocimientos.",
  journal_entry: "Entrada de diario antigua conservada por compatibilidad. Las nuevas entradas cotidianas se guardan en el día correspondiente del Calendario.",
});
const PROPERTY_DESCRIPTIONS_ES = Object.freeze({
  "journal_entry.entry_date": "Fecha a la que pertenece la entrada de diario antigua.",
  "task.status": "Estado actual de la tarea.",
  "task.target_date": "Día en el que quieres abordar la tarea; no es una fecha límite.",
  "task.planned_start_at": "Fecha y hora exactas previstas para empezar a trabajar en la tarea.",
  "task.planned_end_at": "Fecha y hora exactas previstas para terminar el trabajo planificado.",
  "task.deadline_at": "Fecha límite estricta de la tarea, con o sin hora exacta.",
  "task.completed_at": "Fecha y hora exactas en las que la tarea se marcó como completada.",
});
const GENERAL_FIELDS = new Set(["type", "tags", "created_at", "updated_at"]);
const GROUP_PAGE_SIZE = 3;
const COLLAPSED_TYPES_KEY = "odyssey.notes.collapsed-types.v1";

/** Mount the read-only Notes application while retaining its state while the view is inactive. */
export function mountNotes(root, {
  endpoint = "/api/notes",
  confirmImpl = (message) => globalThis.confirm?.(message) ?? false,
  sessionStorageImpl = safeSessionStorage(),
} = {}) {
  const state = {
    query: "", filters: [], sort: "relevance", items: [], cursor: null, loading: false,
    current: null, back: [], forward: [], feedScroll: 0, historical: false, mode: "feed",
    snapshot: null, total: 0, capabilities: {types: [], fields: []}, editing: false,
    editingWorkSessionId: null, editingWorkSessionActivityId: null,
    workSessionDisclosure: new Map(), feedDirty: false, groups: new Map(), pendingGroupRefresh: false,
    collapsedTypes: readCollapsedTypes(sessionStorageImpl),
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
    if (!state.historical && ["feed", "local"].includes(mode)) {
      await loadGroups({reset, mode, throwOnError});
      return;
    }
    await loadGlobal({reset, mode, snapshotIds, throwOnError});
  }

  function flushPendingGroupRefresh() {
    if (!state.pendingGroupRefresh || state.loading) return;
    state.pendingGroupRefresh = false;
    void load({reset: true, mode: state.query.trim() ? "local" : "feed"});
  }

  async function loadGlobal({reset, mode, snapshotIds, throwOnError}) {
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
      state.total = page.total;
      state.historical = page.mode === "snapshot";
      state.mode = page.mode;
      renderList();
      renderStatus(page.total);
    } catch (error) {
      if (error instanceof NotesRequestError && error.code === "STALE_CURSOR" && !reset) {
        state.cursor = null;
        state.loading = false;
        await load({reset: true, mode, snapshotIds, throwOnError});
        return;
      }
      if (error instanceof NotesRequestError && error.code === "STALE_CURSOR") {
        state.cursor = null;
        status.textContent = "Las notas han cambiado. Vuelve a intentarlo.";
      } else {
        status.textContent = "No se han podido cargar las notas.";
      }
      if (throwOnError) throw error;
    } finally {
      state.loading = false;
      flushPendingGroupRefresh();
    }
  }

  async function loadGroups({reset, mode, throwOnError}) {
    if (state.loading) {
      if (reset) state.pendingGroupRefresh = true;
      return;
    }
    state.loading = true;
    state.historical = false;
    state.mode = mode;
    state.cursor = null;
    state.items = [];
    if (reset) state.groups = new Map();
    const types = eligibleTypes();
    status.textContent = "Cargando…";
    try {
      const results = await Promise.allSettled(
        types.map((type) => loadGroup(type.id, {reset, mode, render: false})),
      );
      state.total = types.reduce((total, type) => total + (state.groups.get(type.id)?.total ?? 0), 0);
      renderList();
      renderStatus(state.total);
      const failed = results.find((result) => result.status === "rejected");
      if (failed && throwOnError) throw failed.reason;
      if (failed) status.textContent = "Algunos grupos no se han podido cargar.";
    } catch (error) {
      status.textContent = "No se han podido cargar las notas.";
      if (throwOnError) throw error;
    } finally {
      state.loading = false;
      flushPendingGroupRefresh();
    }
  }

  async function loadGroup(typeId, {reset = false, mode = state.mode, render = true} = {}) {
    const previous = state.groups.get(typeId) ?? {items: [], cursor: null, total: 0, loading: false};
    if (previous.loading || (!reset && !previous.cursor)) return;
    const group = reset ? {items: [], cursor: null, total: 0, loading: true} : {...previous, loading: true};
    state.groups.set(typeId, group);
    try {
      const page = await requestNotes({endpoint, operation: "query", payload: {
        mode, query: state.query, filters: filtersForType(typeId), sort: state.sort,
        page_size: GROUP_PAGE_SIZE, cursor: reset ? null : previous.cursor, snapshot_ids: [],
      }});
      state.groups.set(typeId, {
        items: reset ? [...page.items] : [...previous.items, ...page.items],
        cursor: page.next_cursor, total: page.total, loading: false,
      });
    } catch (error) {
      if (error instanceof NotesRequestError && error.code === "STALE_CURSOR" && !reset) {
        state.groups.set(typeId, {...previous, cursor: null, loading: false});
        await loadGroup(typeId, {reset: true, mode, render});
        return;
      }
      state.groups.set(typeId, {...previous, loading: false, error: true});
      if (render) status.textContent = "No se ha podido actualizar este grupo.";
      throw error;
    }
    if (render) {
      state.total = eligibleTypes().reduce(
        (total, type) => total + (state.groups.get(type.id)?.total ?? 0), 0,
      );
      renderList();
      renderStatus(state.total);
    }
  }

  function eligibleTypes() {
    const selected = state.filters.find((filter) => filter.field === "type" && filter.op === "eq")?.value;
    const propertyFilters = state.filters.filter((filter) => !GENERAL_FIELDS.has(filter.field));
    return state.capabilities.types.filter((type) => (
      (!selected || type.id === selected) && propertyFilters.every((filter) => {
        const field = state.capabilities.fields.find((candidate) => candidate.id === filter.field);
        return field?.applies_to.includes(type.id);
      })
    ));
  }

  function filtersForType(typeId) {
    return [
      ...state.filters.filter((filter) => filter.field !== "type" && (
        GENERAL_FIELDS.has(filter.field) || state.capabilities.fields.find(
          (field) => field.id === filter.field,
        )?.applies_to.includes(typeId)
      )),
      {field: "type", op: "eq", value: typeId},
    ];
  }

  async function loadCapabilities() {
    try {
      state.capabilities = await requestNotes({endpoint, operation: "capabilities"});
      updateControlAvailability();
    } catch {
      filterButton.disabled = true;
    }
  }

  function renderStatus(total = state.total) {
    if (!state.historical || !state.snapshot) {
      status.textContent = total ? `${total} notas` : "No hay notas";
      return;
    }
    const count = state.snapshot.truncated
      ? `${state.snapshot.note_ids.length} de ${state.snapshot.total}`
      : state.snapshot.total;
    if (state.snapshot.kind === "affected_notes") {
      status.replaceChildren(document.createTextNode(`${count} notas afectadas`));
      appendSnapshotExit();
      return;
    }
    status.replaceChildren(document.createTextNode(`Resultado histórico · ${count} notas`));
    const rerun = button("Actualizar búsqueda", () => void rerunHistorical());
    rerun.className = "notes-rerun";
    status.append(document.createTextNode(" · "), rerun, document.createTextNode(" · "));
    appendSnapshotExit();
  }

  function appendSnapshotExit() {
    const all = button("Ver todas", () => void leaveSnapshot());
    all.className = "notes-show-all";
    status.append(all);
  }

  async function leaveSnapshot() {
    state.snapshot = null;
    state.historical = false;
    state.query = "";
    state.filters = [];
    state.sort = "relevance";
    state.items = [];
    state.cursor = null;
    state.current = null;
    state.back = [];
    state.forward = [];
    state.feedScroll = 0;
    state.mode = "feed";
    search.value = "";
    sort.value = state.sort;
    showList();
    renderList();
    await load({reset: true, mode: "feed", snapshotIds: []});
  }

  function renderList() {
    if (!state.historical && ["feed", "local"].includes(state.mode)) {
      renderNormalGroups();
    } else {
      renderGlobalGroups();
    }
    renderFilterChips();
    updateControlAvailability();
  }

  function renderNormalGroups() {
    const intro = document.createElement("p");
    intro.className = "notes-groups-intro";
    intro.textContent = "Odyssey organiza tu información en notas de distintos tipos. Cuando le das información sobre una persona, proyecto, tarea u otro elemento, crea o actualiza su nota y la relaciona con las demás cuando existe un vínculo entre ellas.";
    const groups = eligibleTypes().map((type) => typeGroup(type, state.groups.get(type.id)));
    list.replaceChildren(intro, ...groups, createTypeCard());
  }

  function renderGlobalGroups() {
    const nodes = state.historical ? historicalGroupNodes() : groupedResultNodes();
    list.replaceChildren(...nodes);
    if (state.cursor) {
      const more = button("Cargar más", () => void load());
      more.className = "notes-more";
      list.append(more);
    }
  }

  function groupedResultNodes() {
    const byType = new Map(state.capabilities.types.map((type) => [type.id, []]));
    const ungrouped = [];
    for (const item of state.items) {
      const target = byType.get(item.type);
      if (target) target.push(item); else ungrouped.push(item);
    }
    return [
      ...state.capabilities.types
        .filter((type) => byType.get(type.id).length)
        .map((type) => typeGroup(type, {items: byType.get(type.id), total: byType.get(type.id).length})),
      ...ungrouped.map((note) => noteRow(note, () => void open(note.id))),
    ];
  }

  function historicalGroupNodes() {
    const types = new Map(state.capabilities.types.map((type) => [type.id, type]));
    const nodes = [];
    let run = [];
    let runType = null;
    const flush = () => {
      if (!run.length) return;
      nodes.push(typeGroup(types.get(runType), {items: run, total: run.length}));
      run = [];
    };
    for (const item of state.items) {
      const type = item.unavailable ? null : types.get(item.type);
      if (!type) {
        flush();
        runType = null;
        nodes.push(item.unavailable ? unavailableRow(item.id) : noteRow(item, () => void open(item.id)));
      } else if (runType === item.type) {
        run.push(item);
      } else {
        flush();
        runType = item.type;
        run = [item];
      }
    }
    flush();
    return nodes;
  }

  function typeGroup(type, group = {items: [], cursor: null, total: 0}) {
    const section = document.createElement("section");
    section.className = "notes-type-group";
    section.dataset.type = type.id;
    const header = document.createElement("header");
    header.className = "notes-type-group-header";
    const collapsed = state.collapsedTypes.has(type.id);
    const toggle = button("", () => toggleGroup(type.id));
    toggle.className = "notes-type-toggle";
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.append(typeBadge(type.id), document.createTextNode(typeLabel(type.id)));
    const count = document.createElement("span");
    count.className = "notes-type-count";
    count.textContent = String(group.total ?? 0);
    const add = button("＋", () => {
      createMessage.hidden = false;
      add.setAttribute("aria-expanded", "true");
    });
    add.className = "notes-type-create-button";
    add.setAttribute("aria-label", `Crear nota de tipo ${typeLabel(type.id)}`);
    add.setAttribute("aria-expanded", "false");
    const info = button("i", () => {
      details.hidden = !details.hidden;
      info.setAttribute("aria-expanded", details.hidden ? "false" : "true");
    });
    info.className = "notes-type-info-button";
    info.setAttribute("aria-label", `Información sobre ${typeLabel(type.id)}`);
    info.setAttribute("aria-expanded", "false");
    header.append(toggle, count, add, info);
    const createMessage = document.createElement("p");
    createMessage.className = "notes-type-action-message";
    createMessage.textContent = `Próximamente · Podrás crear una nota de tipo ${typeLabel(type.id)} desde aquí.`;
    createMessage.hidden = true;
    const details = typeInformation(type);
    details.hidden = true;
    const body = document.createElement("div");
    body.className = "notes-type-group-body";
    body.hidden = collapsed;
    for (const note of group.items ?? []) body.append(noteRow(note, () => void open(note.id)));
    if (group.error) {
      const error = document.createElement("p");
      error.className = "notes-group-error";
      error.textContent = "No se ha podido cargar este grupo.";
      body.append(error);
    }
    if (group.cursor) {
      const more = button("Ver más", () => void loadGroup(type.id));
      more.className = "notes-group-more";
      body.append(more);
    }
    section.append(header, createMessage, details, body);
    return section;
  }

  function typeInformation(type) {
    const details = document.createElement("div");
    details.className = "notes-type-information";
    const description = document.createElement("p");
    description.textContent = localizedTypeDescription(type);
    details.append(description);
    if (type.properties.length) {
      const properties = document.createElement("ul");
      for (const property of type.properties) {
        const item = document.createElement("li");
        const requirement = property.required ? "obligatoria" : "opcional";
        const filtering = property.filterable ? "filtrable" : "no filtrable";
        item.textContent = `${filterLabel(property.id)}: ${localizedPropertyDescription(type.id, property)} (${requirement} · ${localizedValueType(property.value_type)} · ${filtering})`;
        properties.append(item);
      }
      details.append(properties);
    }
    const edit = button("Editar tipo", () => {
      editMessage.hidden = false;
      edit.setAttribute("aria-expanded", "true");
    });
    edit.className = "notes-type-edit-button";
    edit.setAttribute("aria-expanded", "false");
    const editMessage = document.createElement("p");
    editMessage.className = "notes-type-edit-message";
    editMessage.textContent = "Próximamente · Podrás editar la descripción y las propiedades de este tipo.";
    editMessage.hidden = true;
    details.append(edit, editMessage);
    return details;
  }

  function toggleGroup(typeId) {
    if (state.collapsedTypes.has(typeId)) state.collapsedTypes.delete(typeId);
    else state.collapsedTypes.add(typeId);
    writeCollapsedTypes(sessionStorageImpl, state.collapsedTypes);
    renderList();
  }

  function createTypeCard() {
    const card = document.createElement("section");
    card.className = "notes-create-type-card";
    const control = button("＋ Crear nuevo tipo", () => {
      message.hidden = false;
      control.setAttribute("aria-expanded", "true");
    });
    control.className = "notes-create-type-button";
    control.setAttribute("aria-expanded", "false");
    const message = document.createElement("p");
    message.className = "notes-create-type-message";
    message.textContent = "Próximamente · Esta función está en desarrollo.";
    message.hidden = true;
    card.append(control, message);
    return card;
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
    state.feedDirty = false;
    showList();
    await load({reset: true, mode: state.query.trim() ? "local" : "feed"});
  }

  function markFeedDirty() {
    if (!state.historical) state.feedDirty = true;
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
      state.items = [];
      state.cursor = null;
      state.groups = new Map();
      state.mode = "intelligent";
      state.current = null;
      showList();
      renderList();
      status.textContent = error instanceof NotesRequestError && error.message.includes("filtros")
        ? "No se pueden mostrar filtros de esta búsqueda con seguridad."
        : "No se ha podido completar la búsqueda inteligente.";
      if (throwOnError) throw error;
    } finally {
      state.loading = false;
      flushPendingGroupRefresh();
    }
  }

  function filtersAreRepresentable(filters) {
    const selectedType = filters.find((filter) => filter.field === "type" && filter.op === "eq")?.value;
    const valid = filters.every((filter) => {
      if (filter.field === "type") return filter.op === "eq" && state.capabilities.types.some((type) => type.id === filter.value);
      if (filter.field === "tags") return filter.op === "contains" && typeof filter.value === "string";
      if (["created_at", "updated_at"].includes(filter.field)) return ["gte", "lt", "lte"].includes(filter.op) && typeof filter.value === "string";
      const field = state.capabilities.fields.find((candidate) => candidate.id === filter.field);
      if (!field || !field.operators.includes(filter.op) || !field.applies_to.length ||
          (selectedType && !field.applies_to.includes(selectedType))) return false;
      if (field.value_type === "date") return ["gte", "lt", "lte"].includes(filter.op) && typeof filter.value === "string";
      if (field.value_type === "integer") return ["gte", "lte"].includes(filter.op) && Number.isInteger(filter.value);
      if (field.value_type === "array[string]") return filter.op === "contains" && typeof filter.value === "string";
      return field.value_type === "string" && filter.op === "eq" && typeof filter.value === "string";
    });
    if (!valid) return false;
    const propertyFilters = filters.filter((filter) => !GENERAL_FIELDS.has(filter.field));
    return state.capabilities.types.some((type) => (
      (!selectedType || type.id === selectedType) && propertyFilters.every((filter) => (
        state.capabilities.fields.find((field) => field.id === filter.field)?.applies_to.includes(type.id)
      ))
    ));
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
      state.editing = false;
      state.editingWorkSessionId = null;
      state.editingWorkSessionActivityId = null;
      state.feedScroll = list.scrollTop;
      renderDetail();
    } catch {
      status.textContent = "No se ha podido abrir la nota.";
    }
  }

  function showList() {
    state.editing = false;
    state.editingWorkSessionId = null;
    state.editingWorkSessionActivityId = null;
    detail.hidden = true;
    listView.hidden = false;
    searchDock.hidden = false;
    list.scrollTop = state.feedScroll;
  }

  function returnToList() {
    state.current = null;
    state.back = [];
    state.forward = [];
    if (state.feedDirty && !state.historical) {
      void refreshCurrentList();
      return;
    }
    showList();
    renderList();
    renderStatus();
  }

  function renderDetail() {
    const value = state.current;
    if (!value) return;
    detail.hidden = false;
    listView.hidden = true;
    searchDock.hidden = true;
    const header = document.createElement("header");
    header.className = "note-view-header";
    const title = document.createElement("h2");
    if (value.note.type === "task" && value.mutation && ["pending", "in_progress", "completed"].includes(value.note.properties?.status)) {
      const completed = value.note.properties.status === "completed";
      const toggle = button(completed ? "☑" : "☐", () => void toggleTask(value, !completed, toggle));
      toggle.className = "note-task-toggle";
      toggle.setAttribute("role", "checkbox");
      toggle.setAttribute("aria-checked", completed ? "true" : "false");
      toggle.setAttribute("aria-label", completed ? "Reabrir tarea" : "Marcar tarea como completada");
      title.append(toggle);
    }
    title.append(typeBadge(value.note.type), document.createTextNode(value.note.name));
    const headerControls = document.createElement("div");
    headerControls.className = "note-edit-controls";
    const edit = actionButton(state.editing ? "check" : "edit", state.editing ? "Terminar edición" : "Editar nota", () => {
      state.editing = !state.editing;
      renderDetail();
    }, "note-edit-toggle action-edit");
    headerControls.append(edit);
    if (state.editing && value.mutation) {
      const removeNote = actionButton("delete", "Eliminar nota", () => void deleteNote(value, removeNote), "note-danger-button note-delete-button action-delete");
      headerControls.append(removeNote);
    }
    header.append(title, headerControls);
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
    renderBody(body, value.body_blocks, open, state.editing && value.mutation
      ? (locator, control) => void deleteFact(value, locator, control)
      : null, value.note.type === "task" ? value.note.name : null);
    const related = [];
    if (value.note.type === "task") {
      related.push(renderWorkSessions(value));
      const subtasks = document.createElement("section");
      subtasks.className = "note-subtasks";
      const subtasksHeading = document.createElement("h3");
      subtasksHeading.textContent = "Subtareas";
      subtasks.append(subtasksHeading);
      void appendSubtasks(subtasks, value);
      related.push(subtasks);
    }
    const backlinks = document.createElement("section");
    backlinks.className = "note-backlinks";
    const backlinksHeading = document.createElement("h3");
    backlinksHeading.textContent = "Enlazada desde";
    backlinks.append(backlinksHeading);
    void appendBacklinks(backlinks, value.note.id, value.note.type === "task");
    related.push(backlinks);
    detail.replaceChildren(header, controls, properties, tags, body, ...related);
  }

  function mutationRequestId() {
    const bytes = new Uint8Array(16);
    if (!globalThis.crypto?.getRandomValues) throw new NotesRequestError("No se puede preparar la actualización.");
    globalThis.crypto.getRandomValues(bytes);
    return `notes-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  }

  async function toggleTask(value, completed, control) {
    if (completed) {
      let subtasks;
      try {
        subtasks = await loadSubtasks(value.note.id);
      } catch {
        status.textContent = "No se han podido comprobar las subtareas. Vuelve a intentarlo.";
        return;
      }
      const openSubtasks = subtasks.filter((item) => ["pending", "in_progress"].includes(item.source.properties?.status)).length;
      if (openSubtasks && !confirmImpl(`Quedan ${openSubtasks} subtarea${openSubtasks === 1 ? "" : "s"} abierta${openSubtasks === 1 ? "" : "s"}. ¿Completar la tarea de todos modos?`)) return;
    }
    control.disabled = true;
    try {
      const result = await requestNotes({endpoint, operation: "task_status", payload: {
        note_id: value.note.id, completed, expected_revision: value.mutation.revision,
        expected_source_hash: value.mutation.source_hash, request_id: mutationRequestId(),
      }});
      const properties = {...value.note.properties, status: result.status};
      if (result.completed_at) properties.completed_at = result.completed_at;
      else delete properties.completed_at;
      state.current = {...value, note: {...value.note, properties}, mutation: result.mutation};
      markFeedDirty();
      renderDetail();
      status.textContent = completed ? "Tarea completada." : "Tarea reabierta.";
    } catch (error) {
      control.disabled = false;
      status.textContent = mutationErrorMessage(error);
    }
  }

  function renderWorkSessions(value) {
    const section = document.createElement("section");
    section.className = "note-work-sessions";
    const headingRow = document.createElement("div");
    headingRow.className = "work-session-heading";
    const heading = document.createElement("h3");
    heading.textContent = "Sesiones de trabajo";
    const sessions = Array.isArray(value.work_sessions) ? value.work_sessions : [];
    const active = sessions.find((session) => !session.ended_at) ?? null;
    const control = actionButton(
      active ? "stop" : "play",
      active ? "Terminar sesión" : "Empezar sesión",
      () => {
        if (active) void stopWorkSession(value, active, control);
        else void startWorkSession(value, control);
      },
      active ? "work-session-stop action-stop" : "work-session-start action-start",
    );
    const taskCanStart = ["pending", "in_progress"].includes(value.note.properties?.status);
    if (!value.mutation || (!active && !taskCanStart)) control.disabled = true;
    headingRow.append(heading, control);
    section.append(headingRow);

    if (sessions.length) {
      const total = sessions.reduce((sum, session) => sum + sessionDurationMs(session), 0);
      const summary = document.createElement("p");
      summary.className = "work-session-total";
      summary.textContent = `Tiempo registrado: ${formatDuration(total)}`;
      section.append(summary);
    }
    if (!sessions.length) {
      const empty = document.createElement("p");
      empty.className = "work-session-empty";
      empty.textContent = "Aún no hay sesiones de trabajo.";
      section.append(empty);
      return section;
    }
    const list = document.createElement("div");
    list.className = "work-session-list";
    for (const session of sessions) {
      const row = document.createElement("div");
      const editingSession = state.editingWorkSessionId === session.id;
      const openedSession = state.workSessionDisclosure.has(session.id)
        ? state.workSessionDisclosure.get(session.id)
        : !session.ended_at || Array.isArray(session.activity) && session.activity.length > 0;
      row.className = `work-session-row${session.ended_at ? "" : " active"}${editingSession ? " editing" : ""}${openedSession ? " opened" : ""}`;
      if (editingSession) {
        const startLabel = document.createElement("label");
        startLabel.textContent = "Inicio";
        const start = document.createElement("input");
        start.type = "datetime-local";
        start.className = "work-session-edit-start";
        start.value = localDateTimePart(session.started_at);
        startLabel.append(start);
        const endLabel = document.createElement("label");
        endLabel.textContent = "Fin";
        const end = document.createElement("input");
        end.type = "datetime-local";
        end.className = "work-session-edit-end";
        end.value = session.ended_at ? localDateTimePart(session.ended_at) : "";
        endLabel.append(end);
        const actions = document.createElement("div");
        actions.className = "work-session-edit-actions";
        const save = actionButton("check", "Guardar horario", () => void saveWorkSessionEdit(value, session, start, end, save), "work-session-save action-save");
        const cancel = actionButton("close", "Cancelar edición", () => {
          state.editingWorkSessionId = null;
          renderDetail();
        }, "work-session-cancel action-cancel");
        actions.append(save, cancel);
        row.append(startLabel, endLabel, actions);
      } else {
        const main = document.createElement("div");
        main.className = "work-session-main";
        const label = document.createElement("span");
        label.className = "work-session-label";
        label.textContent = workSessionLabel(session);
        const actions = document.createElement("div");
        actions.className = "work-session-row-actions";
        const open = actionButton(openedSession ? "chevronUp" : "chevronDown", openedSession ? "Contraer sesión" : "Expandir sesión", () => {
          state.workSessionDisclosure.set(session.id, !openedSession);
          state.editingWorkSessionActivityId = null;
          renderDetail();
        }, "work-session-open action-disclosure");
        const edit = actionButton("clock", "Editar horario", () => {
          state.editingWorkSessionId = session.id;
          state.editingWorkSessionActivityId = null;
          renderDetail();
        }, "work-session-edit action-time");
        actions.append(open, edit);
        main.append(label, actions);
        row.append(main);
        if (openedSession) row.append(renderWorkSessionActivity(value, session));
      }
      list.append(row);
    }
    section.append(list);
    return section;
  }

  function renderWorkSessionActivity(value, session) {
    const panel = document.createElement("section");
    panel.className = "work-session-activity";
    const heading = document.createElement("h4");
    heading.textContent = "Actividad";
    panel.append(heading);
    const entries = Array.isArray(session.activity) ? session.activity : [];
    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "work-session-activity-empty";
      empty.textContent = "Sin actividad registrada todavía.";
      panel.append(empty);
    } else {
      const list = document.createElement("div");
      list.className = "work-session-activity-list";
      for (const entry of entries) {
        const row = document.createElement("div");
        row.className = "work-session-activity-row";
        if (state.editingWorkSessionActivityId === entry.id) {
          const input = document.createElement("textarea");
          input.rows = 2;
          input.value = entry.text;
          input.className = "work-session-activity-edit-input";
          const actions = document.createElement("div");
          actions.className = "work-session-activity-actions";
          const save = actionButton("check", "Guardar actividad", () => void editWorkSessionActivity(value, session, entry, input, save), "action-save");
          const cancel = actionButton("close", "Cancelar edición", () => {
            state.editingWorkSessionActivityId = null;
            renderDetail();
          }, "action-cancel");
          actions.append(save, cancel);
          row.append(input, actions);
        } else {
          const content = document.createElement("p");
          const time = document.createElement("time");
          time.dateTime = entry.created_at;
          time.textContent = activityTime(entry.created_at);
          const text = document.createElement("span");
          text.textContent = entry.text;
          content.append(time, document.createTextNode(" · "), text);
          const actions = document.createElement("div");
          actions.className = "work-session-activity-actions";
          const edit = actionButton("edit", "Editar actividad", () => {
            state.editingWorkSessionActivityId = entry.id;
            renderDetail();
          }, "action-edit");
          const remove = actionButton("delete", "Eliminar actividad", () => void deleteWorkSessionActivity(value, session, entry, remove), "note-danger-button action-delete");
          actions.append(edit, remove);
          row.append(content, actions);
        }
        list.append(row);
      }
      panel.append(list);
    }
    const form = document.createElement("form");
    form.className = "work-session-activity-form";
    const input = document.createElement("textarea");
    input.rows = 2;
    input.maxLength = 2000;
    input.placeholder = session.ended_at ? "Añadir algo que hiciste en esta sesión…" : "Añadir lo que estás haciendo…";
    input.setAttribute("aria-label", "Actividad de la sesión de trabajo");
    const add = actionButton("add", "Añadir actividad", () => {}, "action-add");
    add.type = "submit";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void addWorkSessionActivity(value, session, input, add);
    });
    form.append(input, add);
    panel.append(form);
    return panel;
  }

  async function startWorkSession(value, control) {
    control.disabled = true;
    setActionIcon(control, "more", "Iniciando sesión");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_start", payload: {
        note_id: value.note.id,
        expected_revision: value.mutation.revision,
        expected_source_hash: value.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.editingWorkSessionId = null;
      state.editingWorkSessionActivityId = null;
      const active = result.work_sessions.find((item) => !item.ended_at);
      if (active) state.workSessionDisclosure.set(active.id, true);
      renderDetail();
      status.textContent = "Sesión de trabajo iniciada.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "play", "Empezar sesión");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function stopWorkSession(value, session, control) {
    control.disabled = true;
    setActionIcon(control, "more", "Terminando sesión");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_stop", payload: {
        session_id: session.id,
        expected_revision: session.mutation.revision,
        expected_source_hash: session.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.editingWorkSessionId = null;
      state.editingWorkSessionActivityId = null;
      state.workSessionDisclosure.set(session.id, true);
      renderDetail();
      status.textContent = "Sesión terminada. Puedes seguir añadiendo actividad si lo necesitas.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "stop", "Terminar sesión");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function saveWorkSessionEdit(value, session, startInput, endInput, control) {
    const startedAt = timezoneAwareDateTime(startInput.value);
    const endedAt = endInput.value ? timezoneAwareDateTime(endInput.value) : null;
    if (!startedAt || (endInput.value && !endedAt)) {
      status.textContent = "Revisa las fechas y horas de la sesión.";
      return;
    }
    control.disabled = true;
    setActionIcon(control, "more", "Guardando horario");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_edit", payload: {
        session_id: session.id, started_at: startedAt, ended_at: endedAt,
        expected_revision: session.mutation.revision,
        expected_source_hash: session.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.editingWorkSessionId = null;
      state.workSessionDisclosure.set(session.id, true);
      renderDetail();
      status.textContent = "Sesión de trabajo corregida.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "check", "Guardar horario");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function addWorkSessionActivity(value, session, input, control) {
    const text = input.value.trim();
    if (!text) {
      status.textContent = "Escribe qué has hecho antes de añadirlo.";
      input.focus();
      return;
    }
    control.disabled = true;
    setActionIcon(control, "more", "Añadiendo actividad");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_activity_add", payload: {
        session_id: session.id, text,
        expected_revision: session.mutation.revision,
        expected_source_hash: session.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.workSessionDisclosure.set(session.id, true);
      state.editingWorkSessionActivityId = null;
      renderDetail();
      status.textContent = "Actividad añadida a la sesión.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "add", "Añadir actividad");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function editWorkSessionActivity(value, session, entry, input, control) {
    const text = input.value.trim();
    if (!text) {
      status.textContent = "La actividad no puede quedar vacía.";
      input.focus();
      return;
    }
    control.disabled = true;
    setActionIcon(control, "more", "Guardando actividad");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_activity_edit", payload: {
        session_id: session.id, activity_id: entry.id, text,
        expected_revision: session.mutation.revision,
        expected_source_hash: session.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.workSessionDisclosure.set(session.id, true);
      state.editingWorkSessionActivityId = null;
      renderDetail();
      status.textContent = "Actividad corregida.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "check", "Guardar actividad");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function deleteWorkSessionActivity(value, session, entry, control) {
    if (!confirmImpl("¿Eliminar esta actividad de la sesión de trabajo?")) return;
    control.disabled = true;
    setActionIcon(control, "more", "Eliminando actividad");
    try {
      const result = await requestNotes({endpoint, operation: "work_session_activity_delete", payload: {
        session_id: session.id, activity_id: entry.id,
        expected_revision: session.mutation.revision,
        expected_source_hash: session.mutation.source_hash,
        request_id: mutationRequestId(),
      }});
      state.current = {...value, work_sessions: result.work_sessions};
      state.workSessionDisclosure.set(session.id, true);
      state.editingWorkSessionActivityId = null;
      renderDetail();
      status.textContent = "Actividad eliminada.";
    } catch (error) {
      control.disabled = false;
      setActionIcon(control, "delete", "Eliminar actividad");
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function deleteFact(value, factLocator, control) {
    if (!confirmImpl(`¿Eliminar esta información de ${value.note.name}?`)) return;
    control.disabled = true;
    try {
      await requestNotes({endpoint, operation: "delete_fact", payload: {
        note_id: value.note.id, fact_locator: factLocator, expected_revision: value.mutation.revision,
        expected_source_hash: value.mutation.source_hash, request_id: mutationRequestId(),
      }});
      await open(value.note.id, {history: false});
      status.textContent = "La información se ha eliminado.";
    } catch (error) {
      control.disabled = false;
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function deleteNote(value, control) {
    if (!confirmImpl(`¿Eliminar la nota ${value.note.name}?`)) return;
    control.disabled = true;
    try {
      await requestNotes({endpoint, operation: "delete_note", payload: {
        note_id: value.note.id, expected_revision: value.mutation.revision,
        expected_source_hash: value.mutation.source_hash, request_id: mutationRequestId(),
      }});
      state.current = null;
      showList();
      await refreshCurrentList();
      status.textContent = "La nota se ha retirado.";
    } catch (error) {
      control.disabled = false;
      status.textContent = mutationErrorMessage(error);
    }
  }

  function mutationErrorMessage(error) {
    if (error instanceof NotesRequestError && error.code === "INCOMING_REFERENCES") return "No se puede eliminar esta nota porque otras notas la enlazan.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_ALREADY_ACTIVE") return "Ya hay una sesión de trabajo activa. Termínala antes de empezar otra.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_TASK_CLOSED") return "No se puede iniciar una sesión en una tarea completada o cancelada.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_HISTORY_PRESENT") return "No se puede eliminar una tarea que tiene sesiones de trabajo registradas.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_END_BEFORE_START") return "La hora de fin no puede ser anterior a la hora de inicio.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_ACTIVITY_INVALID") return "La actividad no es válida.";
    if (error instanceof NotesRequestError && error.code === "WORK_SESSION_ACTIVITY_UNAVAILABLE") return "Esa actividad ha cambiado. Abre de nuevo la sesión antes de modificarla.";
    if (error instanceof NotesRequestError && error.code === "TASK_PARENT_CLOSED") return "No se pueden añadir subtareas a una tarea completada o cancelada.";
    if (error instanceof NotesRequestError && error.code === "TASK_SUBTASK_INVALID") return "El título de la subtarea no es válido.";
    if (error instanceof NotesRequestError && error.code === "TASK_SUBTASK_TARGET_UNAVAILABLE") return "Ya existe una tarea con ese título o no se puede identificar de forma segura.";
    if (error instanceof NotesRequestError && ["WORK_SESSION_NOT_ACTIVE", "WORK_SESSION_UNAVAILABLE", "WORK_SESSION_STATE_INVALID"].includes(error.code)) return "La sesión de trabajo ha cambiado. Abre de nuevo la tarea antes de modificarla.";
    if (error instanceof NotesRequestError && ["STALE_NOTE", "FACT_UNAVAILABLE", "NOTE_UNAVAILABLE", "TASK_UNAVAILABLE", "TASK_INVALID_TRANSITION"].includes(error.code)) return "La nota ha cambiado. Ábrela de nuevo antes de modificarla.";
    return "No se ha podido actualizar la nota.";
  }

  function backlinkText(item) {
    return item.snippets.map((snippet) => snippet.block.segments.map((segment) => segment.text).join("")).join(" ");
  }

  function isSubtaskBacklink(item) {
    return item.source.type === "task" && backlinkText(item).includes("Tarea superior:");
  }

  async function loadSubtasks(id) {
    const value = await requestNotes({endpoint, operation: "backlinks", payload: {note_id: id}});
    return value.items.filter(isSubtaskBacklink);
  }

  async function appendSubtasks(target, parent) {
    try {
      const items = await loadSubtasks(parent.note.id);
      if (!items.length) {
        target.append(document.createTextNode("Sin subtareas."));
      } else {
        for (const item of items) {
          const row = document.createElement("div");
          row.className = "backlink note-subtask";
          const completed = item.source.properties?.status === "completed";
          const cancelled = item.source.properties?.status === "cancelled";
          const toggle = button(cancelled ? "⊘" : completed ? "☑" : "☐", () => void toggleSubtask(item.source, !completed, toggle));
          toggle.className = "note-subtask-toggle";
          toggle.setAttribute("role", "checkbox");
          toggle.setAttribute("aria-checked", completed ? "true" : "false");
          toggle.setAttribute("aria-label", cancelled ? `${item.source.name} cancelada` : completed ? `Reabrir ${item.source.name}` : `Completar ${item.source.name}`);
          if (cancelled) toggle.disabled = true;
          const name = button(item.source.name, () => void open(item.source.id));
          name.className = "note-subtask-name";
          row.append(toggle, name);
          target.append(row);
        }
      }
      if (parent.mutation && ["pending", "in_progress"].includes(parent.note.properties?.status)) target.append(renderSubtaskCreateForm(parent));
    } catch {
      target.append(document.createTextNode("No se han podido cargar las subtareas."));
    }
  }

  async function toggleSubtask(summary, completed, control) {
    control.disabled = true;
    try {
      const child = await requestNotes({endpoint, operation: "detail", payload: {note_id: summary.id}});
      if (!child.mutation || child.note.type !== "task") throw new NotesRequestError("Subtarea no disponible.");
      await requestNotes({endpoint, operation: "task_status", payload: {
        note_id: child.note.id, completed, expected_revision: child.mutation.revision,
        expected_source_hash: child.mutation.source_hash, request_id: mutationRequestId(),
      }});
      markFeedDirty();
      if (state.current) renderDetail();
      status.textContent = completed ? "Subtarea completada." : "Subtarea reabierta.";
    } catch (error) {
      control.disabled = false;
      status.textContent = mutationErrorMessage(error);
    }
  }

  function renderSubtaskCreateForm(parent) {
    const form = document.createElement("form");
    form.className = "note-subtask-create-form";
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 240;
    input.placeholder = "Añadir subtarea…";
    input.setAttribute("aria-label", "Título de la subtarea");
    const add = actionButton("add", "Añadir subtarea", () => {}, "action-add");
    add.type = "submit";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void createSubtask(parent, input, add);
    });
    form.append(input, add);
    return form;
  }

  async function createSubtask(parent, input, control) {
    const title = input.value.trim();
    if (!title) {
      input.focus();
      return;
    }
    control.disabled = true;
    try {
      await requestNotes({endpoint, operation: "task_subtask_create", payload: {
        parent_note_id: parent.note.id, title, expected_revision: parent.mutation.revision,
        expected_source_hash: parent.mutation.source_hash, request_id: mutationRequestId(),
      }});
      markFeedDirty();
      renderDetail();
      status.textContent = "Subtarea añadida.";
    } catch (error) {
      control.disabled = false;
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function appendBacklinks(target, id, excludeSubtasks = false) {
    try {
      const value = await requestNotes({endpoint, operation: "backlinks", payload: {note_id: id}});
      const items = excludeSubtasks ? value.items.filter((item) => !isSubtaskBacklink(item)) : value.items;
      if (!items.length) {
        target.append(document.createTextNode("Sin enlaces entrantes."));
        return;
      }
      for (const item of items) {
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
    const tags = state.filters.filter((filter) => filter.field === "tags" && filter.op === "contains");
    setFormValue("filter-tags", tags.map((filter) => filter.value).join(", "));
    syncRange("created_at", "filter-created");
    syncRange("updated_at", "filter-updated");
    syncTypeSpecificFields();
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
      textField("filter-tags", "Etiquetas", "Una o varias etiquetas separadas por comas"),
      rangeField("filter-created", lifecycleLabel("created_at"), "created_at", fieldFormat("created_at") === "date-time" ? "datetime-local" : "date"),
      rangeField("filter-updated", lifecycleLabel("updated_at"), "updated_at", fieldFormat("updated_at") === "date-time" ? "datetime-local" : "date"),
      extraFieldsContainer(),
    );
    renderTypeSpecificFields();
  }

  function extraFieldsContainer() {
    const container = document.createElement("section");
    container.id = "notes-type-specific-filters";
    container.className = "notes-type-specific-filters";
    return container;
  }

  function renderTypeSpecificFields() {
    const container = filterFields?.querySelector("#notes-type-specific-filters");
    if (!container) return;
    container.replaceChildren();
    const fields = state.capabilities.fields.filter((field) => (
      !GENERAL_FIELDS.has(field.id)
    ));
    if (!fields.length) return;
    const heading = document.createElement("h3");
    heading.textContent = "Propiedades específicas";
    container.append(heading);
    for (const field of fields) {
      let control = null;
      if (field.value_type === "date") {
        control = rangeField(`filter-${field.id}`, filterFieldLabel(field), field.id);
      } else if (field.value_type === "integer") {
        control = numberRangeField(`filter-${field.id}`, filterFieldLabel(field), field.id);
      } else if (field.value_type === "array[string]" && field.operators.includes("contains")) {
        control = textField(`filter-${field.id}`, filterFieldLabel(field), "Valores separados por comas", field.id);
      } else if (field.value_type === "string" && field.operators.includes("eq")) {
        if (field.controlled_values?.length) {
          control = selectField(`filter-${field.id}`, filterFieldLabel(field), field.controlled_values.map((value) => ({id: value, name: controlledValueLabel(field.id, value)})));
        } else {
          control = textField(`filter-${field.id}`, filterFieldLabel(field), "Coincidencia exacta", field.id);
        }
      }
      if (control) container.append(control);
    }
  }

  function filterFieldLabel(field) {
    const types = field.applies_to.map(typeLabel).join(", ");
    return types ? `${filterLabel(field.id)} · ${types}` : filterLabel(field.id);
  }

  function syncTypeSpecificFields() {
    renderTypeSpecificFields();
    for (const field of state.capabilities.fields) {
      if (GENERAL_FIELDS.has(field.id)) continue;
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
    const next = state.filters.filter((filter) => filter.field === "type");
    for (const tag of splitValues(formValue("filter-tags"))) next.push({field: "tags", op: "contains", value: tag});
    appendDateRange(next, "created_at", "filter-created");
    appendDateRange(next, "updated_at", "filter-updated");
    for (const field of state.capabilities.fields) {
      if (GENERAL_FIELDS.has(field.id)) continue;
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
  document.addEventListener("odyssey:open-note", (event) => {
    const noteId = event.detail?.note_id;
    if (typeof noteId === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(noteId)) {
      void open(noteId);
    }
  });
  list.addEventListener("scroll", () => {
    if ((state.historical || state.mode === "intelligent") &&
        list.scrollTop + list.clientHeight >= list.scrollHeight - 80) void load();
  });
  void (async () => {
    await loadCapabilities();
    renderFilterFields();
    await load({reset: true});
  })();
  return {state, refresh: () => refreshCurrentList(), showList: returnToList};
}

function noteRow(note, action) {
  const row = button("", action);
  row.className = "note-row";
  row.dataset.noteId = note.id;
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
function renderBody(parent, blocks, open, removeFact = null, taskName = null) {
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
      const segments = taskName ? legacyTaskActionSegments(block.segments, taskName) : block.segments;
      if (removeFact && block.deletable) {
        item.className = "note-editable-fact";
        const content = document.createElement("span");
        content.className = "note-fact-content";
        appendBodySegments(content, segments, open);
        const remove = actionButton("delete", "Eliminar esta información", () => removeFact(block.fact_locator, remove), "note-fact-delete note-danger-button action-delete");
        item.append(content, remove);
      } else {
        appendBodySegments(item, segments, open);
      }
      list.append(item);
      continue;
    }
    list = null;
    const element = document.createElement(block.kind === "heading" ? "h3" : "p");
    appendBodySegments(element, block.segments, open);
    parent.append(element);
  }
}
function legacyTaskActionSegments(segments, taskName) {
  if (!segments.length || segments[0].target_id || typeof segments[0].text !== "string") return segments;
  const prefix = /^\[[ xX]\]\s+/.exec(segments[0].text);
  if (!prefix) return segments;
  const raw = segments.map((segment) => segment.text).join("");
  const visible = raw.slice(prefix[0].length);
  const normalize = (value) => value.trim().replace(/[.!?]+$/, "").trim().toLocaleLowerCase("es");
  if (normalize(visible) !== normalize(taskName)) return segments;
  return [{...segments[0], text: segments[0].text.slice(prefix[0].length)}, ...segments.slice(1)];
}
function appendBodySegments(parent, segments, open) {
  for (const segment of segments) {
    if (!segment.target_id) {
      parent.append(document.createTextNode(segment.text));
      continue;
    }
    const link = document.createElement("a");
    link.className = "note-inline-link";
    link.href = `#note-${encodeURIComponent(segment.target_id)}`;
    link.setAttribute("aria-label", `${typeLabel(segment.target_type)}: ${segment.text}`);
    link.append(typeBadge(segment.target_type), document.createTextNode(segment.text));
    link.addEventListener("click", (event) => {
      event.preventDefault();
      if (segment.target_type === "calendar_day" && segment.target_id.startsWith("date:")) {
        document.dispatchEvent(new CustomEvent("odyssey:open-calendar-day", {
          detail: {date: segment.target_id.slice(5)},
        }));
        return;
      }
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
export function actionIcon(name) {
  const paths = ACTION_ICONS[name] ?? ACTION_ICONS.notes;
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  for (const pathData of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    icon.append(path);
  }
  return icon;
}
export function setActionIcon(control, name, label) {
  control.replaceChildren(actionIcon(name));
  control.setAttribute("aria-label", label);
  control.setAttribute("title", label);
  return control;
}
export function actionButton(name, label, action, classes = "") {
  const control = document.createElement("button");
  control.type = "button";
  control.className = `icon-action ${classes}`.trim();
  setActionIcon(control, name, label);
  control.addEventListener("click", action);
  return control;
}

export function typeBadge(type) {
  const badge = document.createElement("span");
  badge.className = `note-type type-${type}`;
  badge.append(typeIcon(type));
  badge.setAttribute("aria-label", typeLabel(type));
  return badge;
}
export function typeIcon(type) {
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
export function typeLabel(type) { return TYPE_PRESENTATION[type]?.label ?? type.replaceAll("_", " "); }
function safeSessionStorage() {
  try { return globalThis.sessionStorage ?? null; } catch { return null; }
}
function readCollapsedTypes(storage) {
  try {
    const value = JSON.parse(storage?.getItem(COLLAPSED_TYPES_KEY) ?? "[]");
    return new Set(Array.isArray(value) ? value.filter((item) => typeof item === "string") : []);
  } catch {
    return new Set();
  }
}
function writeCollapsedTypes(storage, values) {
  try { storage?.setItem(COLLAPSED_TYPES_KEY, JSON.stringify([...values].sort())); } catch { /* Session state is optional. */ }
}
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
function localizedTypeDescription(type) {
  return TYPE_DESCRIPTIONS_ES[type.id] ?? type.description;
}
function localizedPropertyDescription(typeId, property) {
  return PROPERTY_DESCRIPTIONS_ES[`${typeId}.${property.id}`] ?? property.description;
}
function localizedValueType(valueType) {
  return ({string: "texto", date: "fecha", integer: "número entero", "array[string]": "lista de textos"})[valueType] ?? valueType;
}
function filterLabel(field) {
  return ({
    type: "Tipo", tags: "Etiqueta", created_at: "Creada", updated_at: "Actualizada",
    entry_date: "Fecha de la entrada", status: "Estado", target_date: "Fecha objetivo",
    planned_start_at: "Inicio previsto", planned_end_at: "Fin previsto", deadline_at: "Fecha límite",
    completed_at: "Completada el",
  })[field] ?? field.replaceAll("_", " ");
}
function controlledValueLabel(field, value) {
  if (field === "status") {
    return ({pending: "Pendiente", in_progress: "En curso", completed: "Completada", cancelled: "Cancelada"})[value] ?? value;
  }
  return value.replaceAll("_", " ");
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
function sessionDurationMs(session) { const start = new Date(session.started_at).valueOf(); const end = session.ended_at ? new Date(session.ended_at).valueOf() : Date.now(); return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : 0; }
function formatDuration(milliseconds) { const minutes = Math.max(0, Math.round(milliseconds / 60000)); const hours = Math.floor(minutes / 60); const rest = minutes % 60; return hours ? `${hours} h${rest ? ` ${rest} min` : ""}` : `${rest} min`; }
function activityTime(value) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? "" : date.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"}); }
function workSessionLabel(session) { const start = new Date(session.started_at); if (Number.isNaN(start.valueOf())) return "Sesión de trabajo"; const day = start.toLocaleDateString(undefined, {day: "numeric", month: "short"}); const time = (date) => date.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"}); if (!session.ended_at) return `${day} · ${time(start)} — en curso · ${formatDuration(sessionDurationMs(session))}`; const end = new Date(session.ended_at); return Number.isNaN(end.valueOf()) ? `${day} · ${time(start)}` : `${day} · ${time(start)} — ${time(end)} · ${formatDuration(sessionDurationMs(session))}`; }
function readableDate(value) { const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString(); }
