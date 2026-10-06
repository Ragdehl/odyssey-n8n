const MONTH_PREVIEW_KINDS = new Set(["day_content", "journal", "capture", "task", "reference"]);
const MONTH_PREVIEW_LIMIT = 6;
const MONTH_PREVIEW_LABEL_LIMIT = 80;
const MONTH_PREVIEW_TEXT_LIMIT = 120;
const SCHEDULE_DAY_COUNTS = new Set([1, 3, 7]);
const SCHEDULE_ROLES = new Set(["target", "deadline", "semantic_date", "planned", "semantic_time", "work_session"]);

export class CalendarRequestError extends Error {
  constructor(message) {
    super(message);
    this.name = "CalendarRequestError";
  }
}

export async function requestCalendar({
  endpoint = "/api/calendar", operation, payload = {}, fetchImpl = globalThis.fetch,
}) {
  if (!["month", "day", "schedule"].includes(operation)) throw new CalendarRequestError("Operación de calendario no compatible.");
  let response;
  try {
    response = await fetchImpl(endpoint, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {Accept: "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({operation, ...payload}),
    });
  } catch {
    throw new CalendarRequestError("No se ha podido cargar el calendario.");
  }
  let value;
  try { value = await response.json(); } catch { throw new CalendarRequestError("Odyssey devolvió un calendario inválido."); }
  if (!response.ok) throw new CalendarRequestError("No se ha podido completar la consulta de calendario.");
  return validateCalendarResponse(value);
}

export function validateCalendarResponse(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new CalendarRequestError("Calendario inválido.");
  if (value.kind === "calendar_month") {
    if (!month(value.month) || !Array.isArray(value.days)) throw new CalendarRequestError("Mes inválido.");
    const days = value.days.map(validateMonthDay);
    if (days.some((day) => day.date.slice(0, 7) !== value.month)) throw new CalendarRequestError("Mes inconsistente.");
    return {kind: "calendar_month", month: value.month, days};
  }
  if (value.kind === "calendar_schedule") {
    if (!isoDate(value.start_date) || !SCHEDULE_DAY_COUNTS.has(value.day_count) ||
        !Array.isArray(value.days) || value.days.length !== value.day_count) {
      throw new CalendarRequestError("Agenda de calendario inválida.");
    }
    const days = value.days.map((day, index) => validateScheduleDay(day, shiftIsoDate(value.start_date, index)));
    return {kind: "calendar_schedule", start_date: value.start_date, day_count: value.day_count, days};
  }
  if (value.kind === "calendar_day") {
    if (!isoDate(value.date) || typeof value.materialized !== "boolean" || !Array.isArray(value.content) ||
        !Array.isArray(value.journals) || !Array.isArray(value.captures) || !Array.isArray(value.references) || !Array.isArray(value.tasks)) {
      throw new CalendarRequestError("Día inválido.");
    }
    return {
      kind: "calendar_day", date: value.date, materialized: value.materialized,
      content: value.content.map(validateBlock), journals: value.journals.map(validateJournal),
      captures: value.captures.map(validateCapture), references: value.references.map(validateReference),
      tasks: value.tasks.map(validateTask),
    };
  }
  throw new CalendarRequestError("Respuesta de calendario no compatible.");
}

function validateMonthDay(value) {
  if (!value || !isoDate(value.date) || typeof value.materialized !== "boolean" ||
      typeof value.has_content !== "boolean" || !Array.isArray(value.previews)) throw new CalendarRequestError("Día mensual inválido.");
  const previews = value.previews.map(validateMonthPreview);
  const previewTotal = count(value.preview_total);
  if (previews.length > MONTH_PREVIEW_LIMIT || previews.length > previewTotal) throw new CalendarRequestError("Vista previa mensual inválida.");
  return {
    date: value.date, materialized: value.materialized, has_content: value.has_content,
    journal_count: count(value.journal_count), captured_fact_count: count(value.captured_fact_count),
    reference_count: count(value.reference_count), task_count: count(value.task_count),
    preview_total: previewTotal, previews,
  };
}
function validateMonthPreview(value) {
  if (!value || !MONTH_PREVIEW_KINDS.has(value.kind) || !boundedText(value.source_type, 80) ||
      !boundedText(value.label, MONTH_PREVIEW_LABEL_LIMIT) ||
      (value.text !== undefined && !boundedText(value.text, MONTH_PREVIEW_TEXT_LIMIT))) {
    throw new CalendarRequestError("Vista previa mensual inválida.");
  }
  return value.text === undefined
    ? {kind: value.kind, source_type: value.source_type, label: value.label}
    : {kind: value.kind, source_type: value.source_type, label: value.label, text: value.text};
}
function validateScheduleDay(value, expectedDate) {
  if (!value || value.date !== expectedDate || !Array.isArray(value.all_day) || !Array.isArray(value.timed)) {
    throw new CalendarRequestError("Día de agenda inválido.");
  }
  const allDay = value.all_day.map((item) => validateScheduleItem(item, false));
  const timed = value.timed.map((item) => validateScheduleItem(item, true));
  return {date: value.date, all_day: allDay, timed};
}
function validateScheduleItem(value, timed) {
  if (!value || !["task", "fact", "work_session"].includes(value.kind) || !boundedText(value.source_id, 240) ||
      !boundedText(value.source_type, 80) || !boundedText(value.label, MONTH_PREVIEW_LABEL_LIMIT) ||
      !SCHEDULE_ROLES.has(value.role) ||
      (value.text !== undefined && !boundedText(value.text, MONTH_PREVIEW_TEXT_LIMIT)) ||
      (value.segments !== undefined && !Array.isArray(value.segments))) {
    throw new CalendarRequestError("Elemento de agenda inválido.");
  }
  if (timed) {
    if (!clock(value.start_time) || (value.end_time !== undefined && !clock(value.end_time))) {
      throw new CalendarRequestError("Hora de agenda inválida.");
    }
  } else if (value.start_time !== undefined || value.end_time !== undefined) {
    throw new CalendarRequestError("Elemento sin hora inválido.");
  }
  return {
    kind: value.kind, source_id: value.source_id, source_type: value.source_type,
    label: value.label, role: value.role,
    ...(value.text !== undefined ? {text: value.text} : {}),
    ...(value.segments !== undefined ? {segments: value.segments.map(validateSegment)} : {}),
    ...(value.start_time !== undefined ? {start_time: value.start_time} : {}),
    ...(value.end_time !== undefined ? {end_time: value.end_time} : {}),
  };
}
function validateJournal(value) {
  if (!value || !Array.isArray(value.content)) throw new CalendarRequestError("Diario inválido.");
  return {source: validateSummary(value.source), content: value.content.map(validateBlock)};
}
function validateCapture(value) {
  if (!value || !Array.isArray(value.facts)) throw new CalendarRequestError("Captura inválida.");
  return {source: validateSummary(value.source), facts: value.facts.map(validateBlock)};
}
function validateReference(value) {
  if (!value || !Array.isArray(value.blocks)) throw new CalendarRequestError("Referencia inválida.");
  return {source: validateSummary(value.source), blocks: value.blocks.map(validateBlock)};
}
function validateTask(value) {
  if (!value || !Array.isArray(value.roles) || value.roles.some((role) => !["target", "planned_start", "planned_end", "deadline", "completed"].includes(role)) ||
      !value.mutation || !Number.isInteger(value.mutation.revision) || value.mutation.revision < 1 || !/^[a-f0-9]{64}$/.test(value.mutation.source_hash || "")) {
    throw new CalendarRequestError("Tarea de calendario inválida.");
  }
  return {source: validateSummary(value.source), roles: [...new Set(value.roles)], mutation: {revision: value.mutation.revision, source_hash: value.mutation.source_hash}};
}
function validateSummary(value) {
  if (!value || !text(value.id) || !text(value.name) || !text(value.type) || !Array.isArray(value.tags) ||
      !text(value.created_at) || !text(value.updated_at) || !value.properties || typeof value.properties !== "object" || Array.isArray(value.properties)) {
    throw new CalendarRequestError("Nota relacionada inválida.");
  }
  return {id: value.id, name: value.name, type: value.type, tags: value.tags.filter(text), created_at: value.created_at, updated_at: value.updated_at, properties: value.properties};
}
function validateBlock(value) {
  if (!value || !["heading", "paragraph", "list_item"].includes(value.kind) || !Array.isArray(value.segments)) throw new CalendarRequestError("Contenido de calendario inválido.");
  return {kind: value.kind, segments: value.segments.map(validateSegment)};
}
function validateSegment(value) {
  if (!value || typeof value.text !== "string") throw new CalendarRequestError("Segmento de calendario inválido.");
  const linked = value.target_id !== undefined || value.target_type !== undefined;
  if (linked && (!text(value.target_id) || !text(value.target_type))) throw new CalendarRequestError("Enlace de calendario inválido.");
  return linked ? {text: value.text, target_id: value.target_id, target_type: value.target_type} : {text: value.text};
}
function count(value) { if (!Number.isInteger(value) || value < 0) throw new CalendarRequestError("Conteo de calendario inválido."); return value; }
function boundedText(value, maximum) { return typeof value === "string" && value.length > 0 && [...value].length <= maximum; }
function text(value) { return typeof value === "string" && value.length > 0; }
function clock(value) { return typeof value === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value); }
function shiftIsoDate(value, offset) {
  const current = new Date(`${value}T00:00:00Z`);
  current.setUTCDate(current.getUTCDate() + offset);
  return current.toISOString().slice(0, 10);
}
function isoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
function month(value) { return typeof value === "string" && /^\d{4}-\d{2}$/.test(value) && isoDate(`${value}-01`); }
