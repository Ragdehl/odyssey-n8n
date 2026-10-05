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
export function mountNotes(root, {
  endpoint = "/api/notes",
  confirmImpl = (message) => globalThis.confirm?.(message) ?? false,
} = {}) {
  const state = {
    query: "", filters: [], sort: "relevance", items: [], cursor: null, loading: false,
    current: null, back: [], forward: [], feedScroll: 0, historical: false, mode: "feed",
    snapshot: null, total: 0, capabilities: {types: [], fields: []}, editing: false,
    editingWorkSessionId: null, editingWorkSessionActivityId: null,
    workSessionDisclosure: new Map(), feedDirty: false,
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
      state.current = null;
      showList();
      renderList();
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
      if (state.feedDirty && !state.historical) {
        void refreshCurrentList();
        return;
      }
      showList();
      renderList();
      renderStatus();
    });
    back.setAttribute("aria-label", "Volver a resultados de notas");
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
    const edit = button(state.editing ? "Hecho" : "Editar", () => {
      state.editing = !state.editing;
      renderDetail();
    });
    edit.className = "note-edit-toggle";
    headerControls.append(edit);
    if (state.editing && value.mutation) {
      const removeNote = button("Eliminar nota", () => void deleteNote(value, removeNote));
      removeNote.className = "note-danger-button note-delete-button";
      headerControls.append(removeNote);
    }
    header.append(back, title, headerControls);
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
    const control = button(active ? "Terminar sesión" : "Empezar sesión", () => {
      if (active) void stopWorkSession(value, active, control);
      else void startWorkSession(value, control);
    });
    control.className = active ? "work-session-stop" : "work-session-start";
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
        const save = button("Guardar", () => void saveWorkSessionEdit(value, session, start, end, save));
        save.className = "work-session-save";
        const cancel = button("Cancelar", () => {
          state.editingWorkSessionId = null;
          renderDetail();
        });
        cancel.className = "work-session-cancel";
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
        const open = button(openedSession ? "Cerrar" : "Abrir", () => {
          state.workSessionDisclosure.set(session.id, !openedSession);
          state.editingWorkSessionActivityId = null;
          renderDetail();
        });
        open.className = "work-session-open";
        const edit = button("Editar horario", () => {
          state.editingWorkSessionId = session.id;
          state.editingWorkSessionActivityId = null;
          renderDetail();
        });
        edit.className = "work-session-edit";
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
          const save = button("Guardar", () => void editWorkSessionActivity(value, session, entry, input, save));
          const cancel = button("Cancelar", () => {
            state.editingWorkSessionActivityId = null;
            renderDetail();
          });
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
          const edit = button("Editar", () => {
            state.editingWorkSessionActivityId = entry.id;
            renderDetail();
          });
          const remove = button("Eliminar", () => void deleteWorkSessionActivity(value, session, entry, remove));
          remove.className = "note-danger-button";
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
    const add = button("Añadir", () => {});
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
    control.textContent = "Iniciando…";
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
      control.textContent = "Empezar sesión";
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function stopWorkSession(value, session, control) {
    control.disabled = true;
    control.textContent = "Terminando…";
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
      control.textContent = "Terminar sesión";
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
    control.textContent = "Guardando…";
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
      control.textContent = "Guardar";
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
    control.textContent = "Añadiendo…";
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
      control.textContent = "Añadir";
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
    control.textContent = "Guardando…";
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
      control.textContent = "Guardar";
      status.textContent = mutationErrorMessage(error);
    }
  }

  async function deleteWorkSessionActivity(value, session, entry, control) {
    if (!confirmImpl("¿Eliminar esta actividad de la sesión de trabajo?")) return;
    control.disabled = true;
    control.textContent = "Eliminando…";
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
      control.textContent = "Eliminar";
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
    const add = button("+ Añadir subtarea", () => {});
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
        if (field.controlled_values?.length) {
          container.append(selectField(`filter-${field.id}`, filterLabel(field.id), field.controlled_values.map((value) => ({id: value, name: controlledValueLabel(field.id, value)}))));
        } else {
          container.append(textField(`filter-${field.id}`, filterLabel(field.id), "Coincidencia exacta", field.id));
        }
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
  document.addEventListener("odyssey:open-note", (event) => {
    const noteId = event.detail?.note_id;
    if (typeof noteId === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(noteId)) {
      void open(noteId);
    }
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
        const remove = button("Eliminar", () => removeFact(block.fact_locator, remove));
        remove.className = "note-fact-delete note-danger-button";
        remove.setAttribute("aria-label", "Eliminar esta información");
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
    link.className = `note-inline-link type-${segment.target_type}`;
    link.href = `#note-${encodeURIComponent(segment.target_id)}`;
    link.setAttribute("aria-label", `${typeLabel(segment.target_type)}: ${segment.text}`);
    link.append(typeIcon(segment.target_type), document.createTextNode(segment.text));
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
function sessionDurationMs(session) { const start = new Date(session.started_at).valueOf(); const end = session.ended_at ? new Date(session.ended_at).valueOf() : Date.now(); return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : 0; }
function formatDuration(milliseconds) { const minutes = Math.max(0, Math.round(milliseconds / 60000)); const hours = Math.floor(minutes / 60); const rest = minutes % 60; return hours ? `${hours} h${rest ? ` ${rest} min` : ""}` : `${rest} min`; }
function activityTime(value) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? "" : date.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"}); }
function workSessionLabel(session) { const start = new Date(session.started_at); if (Number.isNaN(start.valueOf())) return "Sesión de trabajo"; const day = start.toLocaleDateString(undefined, {day: "numeric", month: "short"}); const time = (date) => date.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"}); if (!session.ended_at) return `${day} · ${time(start)} — en curso · ${formatDuration(sessionDurationMs(session))}`; const end = new Date(session.ended_at); return Number.isNaN(end.valueOf()) ? `${day} · ${time(start)}` : `${day} · ${time(start)} — ${time(end)} · ${formatDuration(sessionDurationMs(session))}`; }
function readableDate(value) { const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString(); }
