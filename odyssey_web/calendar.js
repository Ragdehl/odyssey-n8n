import {CalendarRequestError, requestCalendar} from "./calendar-client.js";
import {typeBadge, typeLabel} from "./notes.js";

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const MONTH_FORMAT = new Intl.DateTimeFormat("es-ES", {month: "long", year: "numeric", timeZone: "UTC"});
const DAY_FORMAT = new Intl.DateTimeFormat("es-ES", {weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});

export function mountCalendar(root, {endpoint = "/api/calendar"} = {}) {
  const monthView = root.querySelector("#calendar-month-view");
  const dayView = root.querySelector("#calendar-day-view");
  const title = root.querySelector("#calendar-month-title");
  const grid = root.querySelector("#calendar-grid");
  const status = root.querySelector("#calendar-status");
  const today = root.querySelector("#calendar-today");
  const previous = root.querySelector("#calendar-prev");
  const next = root.querySelector("#calendar-next");
  const state = {month: localMonth(), monthValue: null, dayValue: null, loading: false};

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
    const value = button(String(Number(day.date.slice(-2))), () => void openDay(day.date));
    value.className = "calendar-day-cell";
    value.dataset.date = day.date;
    if (day.date === localDate()) value.className += " calendar-day-today";
    if (day.materialized) value.className += " calendar-day-materialized";
    const indicators = document.createElement("span");
    indicators.className = "calendar-day-indicators";
    if (day.has_content) indicators.append(indicator("contenido"));
    if (day.journal_count) indicators.append(indicator("diario"));
    if (day.captured_fact_count) indicators.append(indicator("captura"));
    if (day.reference_count) indicators.append(indicator("referencia"));
    value.append(indicators);
    value.setAttribute("aria-label", dayAriaLabel(day));
    return value;
  }

  async function openDay(value) {
    status.textContent = "Cargando día…";
    try {
      const day = await requestCalendar({endpoint, operation: "day", payload: {date: value}});
      state.dayValue = day;
      if (state.month !== value.slice(0, 7)) {
        state.month = value.slice(0, 7);
        state.monthValue = null;
      }
      renderDay();
      status.textContent = "";
    } catch {
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
function indicator(kind) {
  const value = document.createElement("span");
  value.className = `calendar-indicator calendar-indicator-${kind}`;
  value.setAttribute("aria-hidden", "true");
  return value;
}
function dayAriaLabel(day) {
  const details = [];
  if (day.has_content) details.push("contenido propio");
  if (day.journal_count) details.push(`${day.journal_count} diario` + (day.journal_count === 1 ? "" : "s"));
  if (day.captured_fact_count) details.push(`${day.captured_fact_count} hechos capturados`);
  if (day.reference_count) details.push(`${day.reference_count} referencias`);
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
