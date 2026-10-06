import {CalendarRequestError, requestCalendar} from "./calendar-client.js";
import {NotesRequestError, requestNotes} from "./notes-client.js";
import {typeBadge, typeLabel} from "./notes.js";

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const MONTH_FORMAT = new Intl.DateTimeFormat("es-ES", {month: "long", year: "numeric", timeZone: "UTC"});
const DAY_FORMAT = new Intl.DateTimeFormat("es-ES", {weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});

export function mountCalendar(root, {endpoint = "/api/calendar", notesEndpoint = "/api/notes"} = {}) {
  const monthView = root.querySelector("#calendar-month-view");
  const dayView = root.querySelector("#calendar-day-view");
  const title = root.querySelector("#calendar-month-title");
  const grid = root.querySelector("#calendar-grid");
  const status = root.querySelector("#calendar-status");
  const today = root.querySelector("#calendar-today");
  const previous = root.querySelector("#calendar-prev");
  const next = root.querySelector("#calendar-next");
  const state = {month: localMonth(), monthValue: null, dayValue: null, loading: false};
  let dayRequestGeneration = 0;
  const inFlightDays = new Map();

  async function loadMonth(value = state.month) {
    if (state.loading) return;
    state.loading = true;
    status.textContent = "Cargando…";
    try {
      const month = await requestCalendar({endpoint, operation: "month", payload: {month: value}});
      state.month = month.month;
      state.monthValue = month;
      renderMonth();
      status.textContent = "";
    } catch (error) {
      status.textContent = error instanceof CalendarRequestError
        ? "No se ha podido cargar el calendario."
        : "El calendario no está disponible.";
    } finally {
      state.loading = false;
    }
  }

  function renderMonth() {
    if (!state.monthValue) return;
    status.textContent = "";
    monthView.hidden = false;
    dayView.hidden = true;
    title.textContent = monthLabel(state.monthValue.month);
    const weekdayRow = document.createElement("div");
    weekdayRow.className = "calendar-weekdays";
    for (const weekday of WEEKDAYS) {
      const label = document.createElement("span");
      label.textContent = weekday;
      weekdayRow.append(label);
    }
    const cells = document.createElement("div");
    cells.className = "calendar-cells";
    const first = state.monthValue.days[0]?.date;
    const padding = first ? mondayIndex(first) : 0;
    for (let index = 0; index < padding; index += 1) {
      const blank = document.createElement("span");
      blank.className = "calendar-blank";
      cells.append(blank);
    }
    for (const day of state.monthValue.days) cells.append(dayButton(day));
    grid.replaceChildren(weekdayRow, cells);
  }

  function dayButton(day) {
    const value = button("", () => void openDay(day.date));
    value.className = "calendar-day-cell";
    value.dataset.date = day.date;
    if (day.date === localDate()) value.className += " calendar-day-today";
    if (day.materialized) value.className += " calendar-day-materialized";
    const number = document.createElement("span");
    number.className = "calendar-day-number";
    number.textContent = String(Number(day.date.slice(-2)));
    const previews = document.createElement("span");
    previews.className = "calendar-day-previews";
    for (const preview of day.previews) previews.append(previewRow(preview));
    if (day.preview_total > day.previews.length) {
      const overflow = document.createElement("span");
      overflow.className = "calendar-day-overflow";
      overflow.textContent = `+${day.preview_total - day.previews.length}`;
      previews.append(overflow);
    }
    value.append(number, previews);
    value.setAttribute("aria-label", dayAriaLabel(day));
    return value;
  }

  function previewRow(preview) {
    const row = document.createElement("span");
    row.className = "calendar-month-preview";
    row.append(typeBadge(preview.source_type));
    const text = document.createElement("span");
    text.className = "calendar-preview-text";
    text.textContent = preview.text || preview.label;
    row.append(text);
    return row;
  }

  function requestDay(value) {
    const current = inFlightDays.get(value);
    if (current) return current;
    const pending = requestCalendar({endpoint, operation: "day", payload: {date: value}})
      .finally(() => { if (inFlightDays.get(value) === pending) inFlightDays.delete(value); });
    inFlightDays.set(value, pending);
    return pending;
  }

  async function openDay(value) {
    const generation = ++dayRequestGeneration;
    status.textContent = "Cargando día…";
    try {
      const day = await requestDay(value);
      if (generation !== dayRequestGeneration) return;
      state.dayValue = day;
      if (state.month !== value.slice(0, 7)) {
        state.month = value.slice(0, 7);
        state.monthValue = null;
      }
      renderDay();
      status.textContent = "";
    } catch {
      if (generation !== dayRequestGeneration) return;
      status.textContent = "No se ha podido abrir este día.";
    }
  }

  function renderDay() {
    const day = state.dayValue;
    if (!day) return;
    monthView.hidden = true;
    dayView.hidden = false;
    const header = document.createElement("header");
    header.className = "calendar-day-header";
    const back = button("‹ Mes", () => {
      dayRequestGeneration += 1;
      status.textContent = "";
      state.dayValue = null;
      if (state.monthValue?.month === state.month) renderMonth();
      else void loadMonth(state.month);
    });
    const navigation = document.createElement("div");
    navigation.className = "calendar-day-date-nav";
    const previousDay = button("←", () => void openDay(shiftDate(day.date, -1)));
    previousDay.className = "calendar-day-step calendar-day-previous";
    previousDay.setAttribute("aria-label", "Día anterior");
    const heading = document.createElement("h2");
    heading.textContent = dayLabel(day.date);
    const nextDay = button("→", () => void openDay(shiftDate(day.date, 1)));
    nextDay.className = "calendar-day-step calendar-day-next";
    nextDay.setAttribute("aria-label", "Día siguiente");
    navigation.append(previousDay, heading, nextDay);
    header.append(back, navigation);
    const sections = document.createElement("div");
    sections.className = "calendar-day-sections";
    if (day.content.length) sections.append(blockSection("Contenido del día", day.content));
    if (day.journals.length) sections.append(journalSection(day.journals));
    if (day.captures.length) sections.append(captureSection(day.captures));
    if (day.tasks.length) sections.append(taskSection(day.tasks));
    if (day.references.length) sections.append(referenceSection(day.references));
    if (!sections.children.length) {
      const empty = document.createElement("p");
      empty.className = "calendar-day-empty";
      empty.textContent = "No hay información asociada a este día.";
      sections.append(empty);
    }
    dayView.replaceChildren(header, sections);
  }

  function blockSection(label, blocks) {
    const section = sectionWithHeading(label);
    const body = document.createElement("div");
    body.className = "calendar-blocks";
    renderBlocks(body, blocks);
    section.append(body);
    return section;
  }

  function journalSection(journals) {
    const section = sectionWithHeading("Diario");
    for (const journal of journals) {
      const group = document.createElement("article");
      group.className = "calendar-related-group calendar-journal-group";
      group.append(noteButton(journal.source));
      const body = document.createElement("div");
      body.className = "calendar-related-blocks";
      renderBlocks(body, journal.content);
      group.append(body);
      section.append(group);
    }
    return section;
  }

  function captureSection(captures) {
    const section = sectionWithHeading("Capturado este día");
    for (const capture of captures) {
      const group = document.createElement("article");
      group.className = "calendar-related-group";
      group.append(noteButton(capture.source));
      const facts = document.createElement("div");
      facts.className = "calendar-related-blocks";
      renderBlocks(facts, capture.facts);
      group.append(facts);
      section.append(group);
    }
    return section;
  }

  function taskSection(tasks) {
    const section = sectionWithHeading("Tareas");
    for (const task of tasks) {
      const group = document.createElement("article");
      group.className = "calendar-related-group calendar-task-group";
      const row = document.createElement("div");
      row.className = "calendar-task-row";
      const taskStatus = task.source.properties?.status;
      let marker;
      if (["pending", "in_progress", "completed"].includes(taskStatus)) {
        const completed = taskStatus === "completed";
        marker = button(completed ? "☑" : "☐", () => void toggleCalendarTask(task, !completed, marker));
        marker.className = "calendar-task-status calendar-task-toggle";
        marker.setAttribute("role", "checkbox");
        marker.setAttribute("aria-checked", completed ? "true" : "false");
        marker.setAttribute("aria-label", completed ? `Reabrir ${task.source.name}` : `Completar ${task.source.name}`);
      } else {
        marker = document.createElement("span");
        marker.className = "calendar-task-status";
        marker.textContent = "⊘";
      }
      row.append(marker, noteButton(task.source));
      group.append(row);
      const roles = document.createElement("p");
      roles.className = "calendar-task-roles";
      roles.textContent = task.roles.map(taskRoleLabel).join(" · ");
      group.append(roles);
      section.append(group);
    }
    return section;
  }

  async function toggleCalendarTask(task, completed, control) {
    control.disabled = true;
    try {
      const result = await requestNotes({endpoint: notesEndpoint, operation: "task_status", payload: {
        note_id: task.source.id, completed, expected_revision: task.mutation.revision,
        expected_source_hash: task.mutation.source_hash, request_id: calendarMutationRequestId(),
      }});
      task.source.properties = {...task.source.properties, status: result.status};
      if (result.completed_at) task.source.properties.completed_at = result.completed_at;
      else delete task.source.properties.completed_at;
      task.mutation = result.mutation;
      state.monthValue = null;
      renderDay();
      status.textContent = completed ? "Tarea completada." : "Tarea reabierta.";
    } catch (error) {
      control.disabled = false;
      status.textContent = error instanceof NotesRequestError ? "La tarea ha cambiado; vuelve a intentarlo." : "No se ha podido actualizar la tarea.";
    }
  }

  function calendarMutationRequestId() {
    const bytes = new Uint8Array(16);
    if (!globalThis.crypto?.getRandomValues) throw new NotesRequestError("No se puede preparar la actualización.");
    globalThis.crypto.getRandomValues(bytes);
    return `calendar-task-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  }

  function taskRoleLabel(role) {
    return ({target: "Prevista", planned_start: "Inicio previsto", planned_end: "Fin previsto", deadline: "Fecha límite", completed: "Completada"})[role] || role;
  }

  function referenceSection(references) {
    const section = sectionWithHeading("Referencias a este día");
    for (const reference of references) {
      const group = document.createElement("article");
      group.className = "calendar-related-group";
      group.append(noteButton(reference.source));
      const blocks = document.createElement("div");
      blocks.className = "calendar-related-blocks";
      renderBlocks(blocks, reference.blocks);
      group.append(blocks);
      section.append(group);
    }
    return section;
  }

  function noteButton(note) {
    const value = button("", () => openNote(note.id));
    value.className = "calendar-note-link";
    value.append(typeBadge(note.type), document.createTextNode(note.name));
    value.setAttribute("aria-label", `Abrir ${typeLabel(note.type)} ${note.name}`);
    return value;
  }

  function openNote(noteId) {
    document.dispatchEvent(new CustomEvent("odyssey:open-note", {detail: {note_id: noteId}}));
  }

  function renderBlocks(parent, blocks) {
    let list = null;
    for (const block of blocks) {
      if (block.kind === "list_item") {
        if (!list) {
          list = document.createElement("ul");
          parent.append(list);
        }
        const item = document.createElement("li");
        appendSegments(item, block.segments);
        list.append(item);
        continue;
      }
      list = null;
      const element = document.createElement(block.kind === "heading" ? "h4" : "p");
      appendSegments(element, block.segments);
      parent.append(element);
    }
  }

  function appendSegments(parent, segments) {
    for (const segment of segments) {
      if (!segment.target_id) {
        parent.append(document.createTextNode(segment.text));
        continue;
      }
      const link = document.createElement("a");
      link.href = "#";
      link.className = "calendar-inline-link";
      link.setAttribute("aria-label", `${typeLabel(segment.target_type)}: ${segment.text}`);
      link.append(typeBadge(segment.target_type), document.createTextNode(segment.text));
      link.addEventListener("click", (event) => {
        event.preventDefault();
        if (segment.target_type === "calendar_day" && segment.target_id.startsWith("date:")) {
          void openDay(segment.target_id.slice(5));
        } else {
          openNote(segment.target_id);
        }
      });
      parent.append(link);
    }
  }

  previous?.addEventListener("click", () => void loadMonth(shiftMonth(state.month, -1)));
  next?.addEventListener("click", () => void loadMonth(shiftMonth(state.month, 1)));
  today?.addEventListener("click", () => {
    state.month = localMonth();
    void openDay(localDate());
  });
  document.addEventListener("odyssey:open-calendar-day", (event) => {
    const value = event.detail?.date;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) void openDay(value);
  });
  void loadMonth();
  return {state, openDay, loadMonth};
}

function sectionWithHeading(label) {
  const section = document.createElement("section");
  section.className = "calendar-day-section";
  const heading = document.createElement("h3");
  heading.textContent = label;
  section.append(heading);
  return section;
}
function dayAriaLabel(day) {
  const details = [];
  if (day.has_content) details.push("contenido propio");
  if (day.journal_count) details.push(`${day.journal_count} diario` + (day.journal_count === 1 ? "" : "s"));
  if (day.captured_fact_count) details.push(`${day.captured_fact_count} hechos capturados`);
  if (day.reference_count) details.push(`${day.reference_count} referencias`);
  if (day.task_count) details.push(`${day.task_count} tarea` + (day.task_count === 1 ? "" : "s"));
  return `${dayLabel(day.date)}${details.length ? `. ${details.join(", ")}` : ""}`;
}
function button(label, action) {
  const value = document.createElement("button");
  value.type = "button";
  value.textContent = label;
  value.addEventListener("click", action);
  return value;
}
function shiftDate(value, offset) {
  const current = new Date(`${value}T00:00:00Z`);
  current.setUTCDate(current.getUTCDate() + offset);
  return current.toISOString().slice(0, 10);
}
function shiftMonth(value, offset) {
  const [year, month] = value.split("-").map(Number);
  const current = new Date(Date.UTC(year, month - 1 + offset, 1));
  return `${current.getUTCFullYear()}-${String(current.getUTCMonth() + 1).padStart(2, "0")}`;
}
function monthLabel(value) { return MONTH_FORMAT.format(new Date(`${value}-01T00:00:00Z`)); }
function dayLabel(value) { const label = DAY_FORMAT.format(new Date(`${value}T00:00:00Z`)); return label.charAt(0).toUpperCase() + label.slice(1); }
function mondayIndex(value) { const weekday = new Date(`${value}T00:00:00Z`).getUTCDay(); return (weekday + 6) % 7; }
function localDate() {
  const now = new Date();
  const part = (number) => String(number).padStart(2, "0");
  return `${now.getFullYear()}-${part(now.getMonth() + 1)}-${part(now.getDate())}`;
}
function localMonth() { return localDate().slice(0, 7); }
