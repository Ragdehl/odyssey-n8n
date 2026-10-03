export class CalendarRequestError extends Error {
  constructor(message) {
    super(message);
    this.name = "CalendarRequestError";
  }
}

export async function requestCalendar({
  endpoint = "/api/calendar", operation, payload = {}, fetchImpl = globalThis.fetch,
}) {
  if (!["month", "day"].includes(operation)) throw new CalendarRequestError("Operación de calendario no compatible.");
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
  if (value.kind === "calendar_day") {
    if (!isoDate(value.date) || typeof value.materialized !== "boolean" || !Array.isArray(value.content) ||
        !Array.isArray(value.journals) || !Array.isArray(value.captures) || !Array.isArray(value.references)) {
      throw new CalendarRequestError("Día inválido.");
    }
    return {
      kind: "calendar_day", date: value.date, materialized: value.materialized,
      content: value.content.map(validateBlock), journals: value.journals.map(validateJournal),
      captures: value.captures.map(validateCapture), references: value.references.map(validateReference),
    };
  }
  throw new CalendarRequestError("Respuesta de calendario no compatible.");
}

function validateMonthDay(value) {
  if (!value || !isoDate(value.date) || typeof value.materialized !== "boolean" ||
      typeof value.has_content !== "boolean") throw new CalendarRequestError("Día mensual inválido.");
  return {
    date: value.date, materialized: value.materialized, has_content: value.has_content,
    journal_count: count(value.journal_count), captured_fact_count: count(value.captured_fact_count),
    reference_count: count(value.reference_count),
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
function text(value) { return typeof value === "string" && value.length > 0; }
function isoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
function month(value) { return typeof value === "string" && /^\d{4}-\d{2}$/.test(value) && isoDate(`${value}-01`); }
