/** Narrow, validated same-origin transport for the read-only Notes surface. */

export class NotesRequestError extends Error {
  /** Create a bounded Notes transport/contract error. */
  constructor(message, code = null) {
    super(message);
    this.name = "NotesRequestError";
    this.code = code;
  }
}

/** Request one typed Notes operation without granting browser-side semantic authority. */
export async function requestNotes({endpoint = "/api/notes", operation, payload = {}, fetchImpl = globalThis.fetch}) {
  if (!["capabilities", "query", "intelligent", "detail", "backlinks"].includes(operation)) {
    throw new NotesRequestError("Operación de notas no compatible.");
  }
  let response;
  try {
    response = await fetchImpl(endpoint, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {Accept: "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({operation, ...payload}),
    });
  } catch {
    throw new NotesRequestError("No se han podido cargar las notas.");
  }
  let value;
  try { value = await response.json(); } catch { throw new NotesRequestError("Odyssey devolvió notas inválidas."); }
  if (!response.ok) {
    throw new NotesRequestError("No se ha podido completar la consulta.", value?.error === "STALE_CURSOR" ? "STALE_CURSOR" : null);
  }
  return validateNotesResponse(value);
}

/** Validate the small public Notes response union before it reaches rendering code. */
export function validateNotesResponse(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || typeof value.kind !== "string") {
    throw new NotesRequestError("Odyssey devolvió notas inválidas.");
  }
  if (value.kind === "capabilities") {
    if (!Array.isArray(value.types) || !Array.isArray(value.fields)) throw new NotesRequestError("Capacidades inválidas.");
    return {kind: "capabilities", types: value.types.map(validateType), fields: value.fields.map(validateField)};
  }
  if (value.kind === "page") return validatePage(value);
  if (value.kind === "detail") {
    if (!isText(value.body) || !Array.isArray(value.links)) throw new NotesRequestError("Detalle inválido.");
    return {kind: "detail", note: validateSummary(value.note), body: value.body, links: value.links.map(validateLink)};
  }
  if (value.kind === "backlinks") {
    if (!isText(value.target_id) || !Array.isArray(value.items) || !Number.isInteger(value.total) || !cursor(value.next_cursor)) throw new NotesRequestError("Enlaces entrantes inválidos.");
    return {kind: "backlinks", target_id: value.target_id, total: value.total, next_cursor: value.next_cursor,
      items: value.items.map((item) => ({source: validateSummary(item?.source), occurrences: count(item?.occurrences), context: text(item?.context)}))};
  }
  throw new NotesRequestError("Respuesta de notas no compatible.");
}

function validatePage(value) {
  if (!["feed", "local", "intelligent", "snapshot"].includes(value.mode) || !["relevance", "updated_desc", "created_desc", "created_asc"].includes(value.sort) || !isText(value.ranking_version) || !isText(value.as_of) || !Array.isArray(value.applied_filters) || !Array.isArray(value.items) || !Number.isInteger(value.total) || !cursor(value.next_cursor)) throw new NotesRequestError("Página de notas inválida.");
  return {kind: "page", mode: value.mode, sort: value.sort, ranking_version: value.ranking_version, as_of: value.as_of,
    applied_filters: value.applied_filters.map(validateFilter), items: value.items.map(validateSummary), total: value.total, next_cursor: value.next_cursor};
}
function validateSummary(value) { if (!value || typeof value !== "object" || !isText(value.id) || !isText(value.name) || !isText(value.type) || !Array.isArray(value.tags) || !isText(value.created_at) || !isText(value.updated_at) || !value.properties || typeof value.properties !== "object" || Array.isArray(value.properties)) throw new NotesRequestError("Nota inválida."); return {id: value.id, name: value.name, type: value.type, tags: value.tags.filter(isText), created_at: value.created_at, updated_at: value.updated_at, properties: value.properties}; }
function validateType(value) { if (!value || !isText(value.id) || !isText(value.name)) throw new NotesRequestError("Tipo inválido."); return {id: value.id, name: value.name}; }
function validateField(value) { if (!value || !isText(value.id) || !isText(value.value_type) || !Array.isArray(value.operators) || !Array.isArray(value.applies_to)) throw new NotesRequestError("Campo inválido."); return {id: value.id, value_type: value.value_type, operators: value.operators.filter(isText), applies_to: value.applies_to.filter(isText)}; }
function validateFilter(value) { if (!value || !isText(value.field) || !isText(value.op)) throw new NotesRequestError("Filtro inválido."); return {field: value.field, op: value.op, value: value.value}; }
function validateLink(value) { if (!value || !isText(value.target_id) || !isText(value.target_name) || !isText(value.target_type) || !isText(value.label)) throw new NotesRequestError("Enlace inválido."); return {...value, occurrences: count(value.occurrences)}; }
function count(value) { if (!Number.isInteger(value) || value < 1) throw new NotesRequestError("Conteo inválido."); return value; }
function cursor(value) { return value === null || isText(value); }
function isText(value) { return typeof value === "string" && value.length > 0; }
function text(value) { return typeof value === "string" ? value : ""; }
