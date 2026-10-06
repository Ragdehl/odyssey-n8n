import {CalendarRequestError, requestCalendar} from "./calendar-client.js";
import {NotesRequestError, requestNotes} from "./notes-client.js";
import {typeBadge, typeLabel} from "./notes.js";

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const MONTH_FORMAT = new Intl.DateTimeFormat("es-ES", {month: "long", year: "numeric", timeZone: "UTC"});
const DAY_FORMAT = new Intl.DateTimeFormat("es-ES", {weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});
const SCHEDULE_DAY_FORMAT = new Intl.DateTimeFormat("es-ES", {weekday: "short", day: "numeric", month: "short", timeZone: "UTC"});
const CALENDAR_DENSITY_KEY = "odyssey.calendar.month.expanded";
const CALENDAR_VIEW_KEY = "odyssey.calendar.view-mode";
const SCHEDULE_HOUR_HEIGHT = 60;

export function mountCalendar(root, {
  endpoint = "/api/calendar",
  notesEndpoint = "/api/notes",
  sessionStorageImpl = safeSessionStorage(),
} = {}) {
  const monthView = root.querySelector("#calendar-month-view");
  const scheduleView = root.querySelector("#calendar-schedule-view");
  const dayView = root.querySelector("#calendar-day-view");
  const title = root.querySelector("#calendar-month-title");
  const grid = root.querySelector("#calendar-grid");
  const status = root.querySelector("#calendar-status");
  const today = root.querySelector("#calendar-today");
  const expand = root.querySelector("#calendar-expand");
  const previous = root.querySelector("#calendar-prev");
  const next = root.querySelector("#calendar-next");
  const scheduleTitle = root.querySelector("#calendar-schedule-title");
  const scheduleGrid = root.querySelector("#calendar-schedule-grid");
  const schedulePrevious = root.querySelector("#calendar-schedule-prev");
  const scheduleNext = root.querySelector("#calendar-schedule-next");
  const scheduleToday = root.querySelector("#calendar-schedule-today");
  const viewButtons = new Map([
    ["month", root.querySelector("#calendar-view-month")],
    ["7", root.querySelector("#calendar-view-7")],
    ["3", root.querySelector("#calendar-view-3")],
    ["1", root.querySelector("#calendar-view-1")],
  ]);
  const state = {
    month: localMonth(),
    monthValue: null,
    dayValue: null,
    loading: false,
    expanded: readExpandedState(sessionStorageImpl),
    viewMode: readViewMode(sessionStorageImpl),
    scheduleStart: localDate(),
    scheduleValue: null,
    dayReturnMode: "month",
    monthDetailDate: null,
    monthDetail: null,
  };
  let dayRequestGeneration = 0;
  let scheduleRequestGeneration = 0;
  let swipeStart = null;
  const inFlightDays = new Map();

  async function loadMonth(value = state.month) {
    if (state.loading) return;
    state.loading = true;
    status.textContent = "Cargando…";
    try {
      const month = await requestCalendar({endpoint, operation: "month", payload: {month: value}});
      if (state.monthValue?.month !== month.month) {
        state.monthDetailDate = null;
        state.monthDetail = null;
      }
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

  async function loadSchedule(value = state.scheduleStart) {
    const dayCount = Number(state.viewMode);
    if (![1, 3, 7].includes(dayCount)) return;
    const generation = ++scheduleRequestGeneration;
    status.textContent = "Cargando agenda…";
    try {
      const schedule = await requestCalendar({
        endpoint, operation: "schedule", payload: {start_date: value, day_count: dayCount},
      });
      if (generation !== scheduleRequestGeneration || state.viewMode === "month") return;
      state.scheduleStart = schedule.start_date;
      state.scheduleValue = schedule;
      renderSchedule();
      status.textContent = "";
    } catch (error) {
      if (generation !== scheduleRequestGeneration) return;
      status.textContent = error instanceof CalendarRequestError
        ? "No se ha podido cargar la agenda."
        : "La agenda no está disponible.";
    }
  }

  function renderViewSwitch() {
    for (const [mode, control] of viewButtons) {
      if (!control) continue;
      control.setAttribute("aria-pressed", state.viewMode === mode ? "true" : "false");
    }
  }

  function showMonth() {
    dayRequestGeneration += 1;
    scheduleRequestGeneration += 1;
    state.viewMode = "month";
    writeViewMode(sessionStorageImpl, "month");
    state.dayValue = null;
    state.monthDetailDate = null;
    state.monthDetail = null;
    status.textContent = "";
    renderViewSwitch();
    if (state.monthValue?.month === state.month) renderMonth();
    else void loadMonth(state.month);
  }

  function selectView(mode) {
    if (!["month", "7", "3", "1"].includes(mode)) return;
    if (mode === "month") {
      showMonth();
      return;
    }
    if (mode === state.viewMode && !state.dayValue) return;
    state.viewMode = mode;
    writeViewMode(sessionStorageImpl, mode);
    state.dayValue = null;
    state.monthDetailDate = null;
    state.monthDetail = null;
    renderViewSwitch();
    status.textContent = "";
    monthView.hidden = true;
    dayView.hidden = true;
    scheduleView.hidden = false;
    state.scheduleValue = null;
    void loadSchedule(state.scheduleStart);
  }

  function navigateSchedule(direction) {
    const dayCount = Number(state.viewMode);
    if (![1, 3, 7].includes(dayCount)) return;
    state.scheduleStart = shiftDate(state.scheduleStart, direction * dayCount);
    void loadSchedule(state.scheduleStart);
  }

  function renderSchedule() {
    const schedule = state.scheduleValue;
    if (!schedule) return;
    renderViewSwitch();
    monthView.hidden = true;
    dayView.hidden = true;
    scheduleView.hidden = false;
    scheduleTitle.textContent = scheduleRangeLabel(schedule.start_date, schedule.day_count);
    scheduleGrid.className = `calendar-schedule-grid calendar-schedule-${schedule.day_count}`;

    const header = document.createElement("div");
    header.className = "calendar-schedule-header";
    const headerAxis = document.createElement("span");
    headerAxis.className = "calendar-schedule-axis-spacer";
    header.append(headerAxis);
    for (const day of schedule.days) {
      const dayControl = button(scheduleDayLabel(day.date), () => void openDay(day.date));
      dayControl.className = "calendar-schedule-day-heading";
      if (day.date === localDate()) dayControl.className += " calendar-schedule-day-today";
      header.append(dayControl);
    }

    const allDay = document.createElement("div");
    allDay.className = "calendar-schedule-all-day";
    const allDayLabel = document.createElement("span");
    allDayLabel.className = "calendar-schedule-all-day-label";
    allDayLabel.textContent = "Sin hora";
    allDay.append(allDayLabel);
    for (const day of schedule.days) {
      const column = document.createElement("div");
      column.className = "calendar-schedule-all-day-column";
      for (const item of day.all_day) column.append(scheduleItem(item, false));
      allDay.append(column);
    }

    const scroll = document.createElement("div");
    scroll.className = "calendar-schedule-scroll";
    const timeline = document.createElement("div");
    timeline.className = "calendar-schedule-timeline";
    const axis = document.createElement("div");
    axis.className = "calendar-schedule-axis";
    for (let hour = 0; hour < 24; hour += 1) {
      const label = document.createElement("span");
      label.className = "calendar-schedule-hour";
      label.textContent = `${String(hour).padStart(2, "0")}:00`;
      label.style.top = `${hour * SCHEDULE_HOUR_HEIGHT}px`;
      axis.append(label);
    }
    timeline.append(axis);
    for (const day of schedule.days) {
      const lane = document.createElement("div");
      lane.className = "calendar-schedule-lane";
      for (const item of day.timed) lane.append(scheduleItem(item, true));
      timeline.append(lane);
    }
    scroll.append(timeline);
    scheduleGrid.replaceChildren(header, allDay, scroll);
    queueMicrotask(() => {
      if (scroll.scrollTop === 0) scroll.scrollTop = 6 * SCHEDULE_HOUR_HEIGHT;
    });
  }

  function scheduleItem(item, timed) {
    const value = button("", () => {
      if (item.source_type === "calendar_day" && item.source_id.startsWith("date:")) {
        void openDay(item.source_id.slice(5));
      } else {
        openNote(item.source_id);
      }
    });
    value.className = `calendar-schedule-item calendar-schedule-item-${item.kind} calendar-schedule-role-${item.role}`;
    value.append(typeBadge(item.source_type));
    const copy = document.createElement("span");
    copy.className = "calendar-schedule-item-copy";
    const label = document.createElement("strong");
    label.textContent = item.label;
    copy.append(label);
    if (item.text) {
      const text = document.createElement("span");
      text.textContent = item.text;
      copy.append(text);
    }
    if (timed) {
      const start = minutesForClock(item.start_time);
      const end = item.end_time ? minutesForClock(item.end_time) : null;
      value.style.top = `${start}px`;
      value.style.height = `${end !== null && end > start ? Math.max(32, end - start) : 34}px`;
      const time = document.createElement("span");
      time.className = "calendar-schedule-item-time";
      time.textContent = item.end_time ? `${item.start_time}–${item.end_time}` : item.start_time;
      copy.append(time);
    }
    value.append(copy);
    value.setAttribute("aria-label", scheduleItemAriaLabel(item));
    return value;
  }

  function renderMonth() {
    if (!state.monthValue) return;
    status.textContent = "";
    renderViewSwitch();
    monthView.hidden = false;
    scheduleView.hidden = true;
    dayView.hidden = true;
    title.textContent = monthLabel(state.monthValue.month);
    renderDensity();
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
    const value = document.createElement("div");
    const detailOpen = state.monthDetailDate === day.date;
    value.className = `calendar-day-cell${detailOpen ? " calendar-day-more-open" : ""}`;
    value.dataset.date = day.date;
    value.setAttribute("role", "button");
    value.setAttribute("tabindex", "0");
    value.setAttribute("aria-label", dayAriaLabel(day));
    value.addEventListener("click", () => void openDay(day.date));
    value.addEventListener("keydown", (event) => {
      if (event.target !== value || !["Enter", " "].includes(event.key)) return;
      event.preventDefault?.();
      void openDay(day.date);
    });
    if (day.date === localDate()) value.className += " calendar-day-today";
    if (day.materialized) value.className += " calendar-day-materialized";
    const number = document.createElement("span");
    number.className = "calendar-day-number";
    number.textContent = String(Number(day.date.slice(-2)));
    const previews = document.createElement("div");
    previews.className = "calendar-day-previews";
    const detailed = detailOpen && state.monthDetail ? monthDetailPreviews(state.monthDetail) : [];
    const baseLimit = state.expanded ? 6 : 4;
    const baseItems = day.previews.slice(0, baseLimit);
    const items = detailOpen
      ? [...day.previews, ...detailed.slice(day.previews.length)]
      : baseItems;
    for (const preview of items) previews.append(previewRow(preview));
    let overflow = null;
    if (day.preview_total > baseItems.length) {
      overflow = button(
        detailOpen ? (state.monthDetail ? "Mostrar menos ↑" : "Cargando…") : `Ver ${day.preview_total - baseItems.length} más ↓`,
        (event) => {
          event.stopPropagation?.();
          void toggleMonthDetail(day);
        },
      );
      overflow.className = "calendar-day-overflow calendar-day-more";
    }
    value.append(number, previews);
    if (overflow) value.append(overflow);
    return value;
  }


  function previewRow(preview) {
    const row = document.createElement("span");
    row.className = `calendar-month-preview${preview.text ? " calendar-preview-has-text" : ""}`;
    row.append(typeBadge(preview.source_type));
    const copy = document.createElement("span");
    copy.className = "calendar-preview-copy";
    const label = document.createElement("span");
    label.className = "calendar-preview-label";
    label.textContent = preview.label;
    copy.append(label);
    if (preview.text) {
      const text = document.createElement("span");
      text.className = "calendar-preview-text";
      text.textContent = preview.text;
      copy.append(text);
    }
    row.append(copy);
    return row;
  }

  function monthDetailPreviews(day) {
    const items = [];
    if (day.content.length) {
      items.push({kind: "day_content", source_type: "calendar_day", label: day.date, text: firstBlockText(day.content)});
    }
    for (const journal of day.journals) {
      items.push({kind: "journal", source_type: journal.source.type, label: journal.source.name, text: firstBlockText(journal.content)});
    }
    for (const capture of day.captures) {
      items.push({kind: "capture", source_type: capture.source.type, label: capture.source.name, text: firstBlockText(capture.facts)});
    }
    for (const task of day.tasks) {
      items.push({kind: "task", source_type: task.source.type, label: task.source.name});
    }
    for (const reference of day.references) {
      items.push({kind: "reference", source_type: reference.source.type, label: reference.source.name, text: firstBlockText(reference.blocks)});
    }
    return items;
  }

  function firstBlockText(blocks) {
    for (const block of blocks) {
      if (block.kind === "heading") continue;
      const value = block.segments.map((segment) => segment.text).join("").replace(/\s+/g, " ").trim();
      if (value) return value;
    }
    return undefined;
  }

  async function toggleMonthDetail(day) {
    if (state.monthDetailDate === day.date) {
      state.monthDetailDate = null;
      state.monthDetail = null;
      renderMonth();
      return;
    }
    state.monthDetailDate = day.date;
    state.monthDetail = null;
    renderMonth();
    try {
      const detail = await requestDay(day.date);
      if (state.monthDetailDate !== day.date) return;
      state.monthDetail = detail;
      renderMonth();
    } catch {
      if (state.monthDetailDate !== day.date) return;
      state.monthDetailDate = null;
      state.monthDetail = null;
      renderMonth();
      status.textContent = "No se ha podido cargar el contenido adicional de este día.";
    }
  }

  function renderDensity() {
    grid.className = state.expanded ? "calendar-grid calendar-grid-expanded" : "calendar-grid";
    if (!expand) return;
    expand.textContent = "⛶";
    expand.setAttribute("aria-pressed", state.expanded ? "true" : "false");
    expand.setAttribute("aria-label", state.expanded ? "Vista compacta" : "Vista ampliada");
    expand.setAttribute("title", state.expanded ? "Vista compacta" : "Vista ampliada");
  }

  function toggleDensity() {
    state.expanded = !state.expanded;
    writeExpandedState(sessionStorageImpl, state.expanded);
    renderMonth();
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
    state.dayReturnMode = state.viewMode;
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
    scheduleView.hidden = true;
    dayView.hidden = false;
    const header = document.createElement("header");
    header.className = "calendar-day-header";
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
    header.append(navigation);
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
  expand?.addEventListener("click", toggleDensity);
  today?.addEventListener("click", () => {
    state.month = localMonth();
    void openDay(localDate());
  });
  schedulePrevious?.addEventListener("click", () => navigateSchedule(-1));
  scheduleNext?.addEventListener("click", () => navigateSchedule(1));
  scheduleToday?.addEventListener("click", () => {
    state.scheduleStart = localDate();
    void loadSchedule(state.scheduleStart);
  });
  for (const [mode, control] of viewButtons) control?.addEventListener("click", () => selectView(mode));
  scheduleGrid?.addEventListener("touchstart", (event) => {
    const touch = event.touches?.[0];
    swipeStart = touch ? {x: touch.clientX, y: touch.clientY} : null;
  }, {passive: true});
  scheduleGrid?.addEventListener("touchend", (event) => {
    const touch = event.changedTouches?.[0];
    if (!swipeStart || !touch) {
      swipeStart = null;
      return;
    }
    const dx = touch.clientX - swipeStart.x;
    const dy = touch.clientY - swipeStart.y;
    swipeStart = null;
    if (Math.abs(dx) < 55 || Math.abs(dx) <= Math.abs(dy) * 1.2) return;
    navigateSchedule(dx < 0 ? 1 : -1);
  }, {passive: true});
  document.addEventListener("odyssey:open-calendar-day", (event) => {
    const value = event.detail?.date;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) void openDay(value);
  });
  renderViewSwitch();
  if (state.viewMode === "month") void loadMonth();
  else void loadSchedule(state.scheduleStart);
  return {state, openDay, loadMonth, loadSchedule, selectView, showMonth};
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
function scheduleDayLabel(value) {
  const label = SCHEDULE_DAY_FORMAT.format(new Date(`${value}T00:00:00Z`)).replace(".", "");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
function scheduleRangeLabel(startDate, dayCount) {
  const endDate = shiftDate(startDate, dayCount - 1);
  return dayCount === 1 ? scheduleDayLabel(startDate) : `${scheduleDayLabel(startDate)} – ${scheduleDayLabel(endDate)}`;
}
function minutesForClock(value) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}
function scheduleItemAriaLabel(item) {
  const time = item.start_time
    ? `${item.start_time}${item.end_time ? ` a ${item.end_time}` : ""}. `
    : "";
  return `${time}${typeLabel(item.source_type)}: ${item.label}${item.text ? `. ${item.text}` : ""}`;
}
function mondayIndex(value) { const weekday = new Date(`${value}T00:00:00Z`).getUTCDay(); return (weekday + 6) % 7; }
function localDate() {
  const now = new Date();
  const part = (number) => String(number).padStart(2, "0");
  return `${now.getFullYear()}-${part(now.getMonth() + 1)}-${part(now.getDate())}`;
}
function localMonth() { return localDate().slice(0, 7); }
function safeSessionStorage() {
  try { return globalThis.sessionStorage ?? null; } catch { return null; }
}
function readViewMode(storage) {
  try {
    const value = storage?.getItem(CALENDAR_VIEW_KEY);
    return ["month", "7", "3", "1"].includes(value) ? value : "month";
  } catch {
    return "month";
  }
}
function writeViewMode(storage, mode) {
  try { storage?.setItem(CALENDAR_VIEW_KEY, mode); } catch {}
}
function readExpandedState(storage) {
  try { return storage?.getItem(CALENDAR_DENSITY_KEY) === "true"; }
  catch { return false; }
}
function writeExpandedState(storage, expanded) {
  try { storage?.setItem(CALENDAR_DENSITY_KEY, expanded ? "true" : "false"); }
  catch {}
}
