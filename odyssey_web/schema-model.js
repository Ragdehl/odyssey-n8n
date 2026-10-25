/** Isolated user-note model review sheet. No model output or browser state writes schemas. */
import {requestNotes} from "./notes-client.js";

function stableId(label) {
  return label.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 64);
}

function control(tag, className, content = "") {
  const element = document.createElement(tag);
  element.className = className;
  if (content) element.textContent = content;
  return element;
}

function entry(label, placeholder, {multiline = false} = {}) {
  const wrapper = control("label", "schema-model-field");
  wrapper.append(control("span", "schema-model-label", label));
  const input = control(multiline ? "textarea" : "input", "schema-model-input");
  input.placeholder = placeholder;
  input.maxLength = multiline ? 2000 : 240;
  if (multiline) input.rows = 3;
  wrapper.append(input);
  return {wrapper, input};
}

function button(text, onClick, name = "") {
  const node = control("button", `schema-model-button ${name}`, text);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function newRequestId() {
  const random = globalThis.crypto?.randomUUID?.();
  // Fail closed if secure randomness is unavailable; never make a request ID
  // from Math.random, time or user-controlled text.
  if (!random || random.length > 128) throw new Error("No se ha podido crear un identificador seguro.");
  return `schema_${random.replaceAll("-", "")}`;
}

/** Mount once; only visible when explicitly opened from Notes. */
export function createSchemaModel({root, endpoint = "/api/notes", client = requestNotes,
  onActive = () => {}, storage = null} = {}) {
  const storageKey = "odyssey.schema.model.pending.v1";
  const readPending = () => {
    try {
      const value = storage?.getItem?.(storageKey);
      return typeof value === "string" && /^schema_[a-f0-9]{32}$/.test(value) ? value : null;
    } catch { return null; }
  };
  const savePending = (id) => {
    try { storage?.setItem?.(storageKey, id); } catch { /* UI still supports manual status */ }
  };
  const clearPending = () => {
    try { storage?.removeItem?.(storageKey); } catch { /* best effort */ }
  };
  const sheet = control("section", "schema-model-sheet");
  sheet.hidden = true;
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-label", "Modelo de notas");
  const top = control("header", "schema-model-header");
  top.append(control("h2", "", "Modelo de notas"));
  const close = button("Cerrar", () => {
    sheet.hidden = true;
    invalidate();
  }, "schema-model-close");
  top.append(close);
  const intro = control("p", "schema-model-intro",
    "Organiza personas, libros, plantas o cualquier tipo de cosa con los datos que te interesen. Odyssey comprobará si tu propuesta encaja con el modelo actual.");
  const availability = control("p", "schema-model-message");
  availability.setAttribute("role", "status");
  const assistant = control("section", "schema-model-assistant");
  assistant.append(control("h3", "", "Explícaselo a Odyssey"));
  const request = entry("¿Cómo quieres organizar tus notas?",
    "Ej.: Quiero organizar los libros que leo y guardar su autor y número de páginas", {multiline: true});
  request.input.maxLength = 1200;
  const assistantReply = control("p", "schema-model-assistant-reply");
  assistantReply.setAttribute("role", "status");
  const ask = button("Pedir propuesta a la IA", () => void suggest(), "schema-model-ask");
  assistant.append(request.wrapper, ask, assistantReply,
    control("p", "schema-model-hint", "La IA propone, pero no puede cambiar tus notas ni aprobar cambios. También puedes usar las preguntas guiadas de abajo."));
  const form = control("form", "schema-model-form");
  const preview = control("section", "schema-model-preview");
  preview.hidden = true;
  const summary = control("div", "schema-model-preview-summary");
  const confirmation = control("p", "schema-model-confirmation");
  const confirm = button("Confirmar este cambio", () => void submit(), "schema-model-confirm");
  const review = button("Modificar propuesta", () => {
    const draft = proposed?.draft;
    invalidate();
    preservedProperties = null;
    preview.hidden = true;
    if (draft?.operation === "add_type") {
      preservedProperties = new Map(draft.type.properties.map((property) => [property.id, property]));
      mode = "new";
      fields = build();
      fields.name.value = draft.type.name;
      fields.description.value = draft.type.description;
      fields.properties.value = draft.type.properties.map((p) => p.id).join(", ");
    } else if (draft?.operation === "add_property") {
      mode = "add-property";
      activeType = {id: draft.type_id};
      fields = build();
      fields.name.value = draft.property.id;
      fields.description.value = draft.property.description;
      fields.typeSelector.value = draft.property.value_type;
    }
    form.hidden = false;
    availability.textContent = preservedProperties
      ? "Puedes quitar los datos que no quieras. Los restantes conservan su tipo mientras mantengas su nombre; para renombrar números, fechas o listas, pide otra propuesta a la IA."
      : "Puedes corregir la información y comprobarla otra vez.";
  }, "schema-model-review");
  const controls = control("div", "schema-model-controls");
  controls.append(review, confirm);
  preview.append(summary, confirmation, controls);
  const retry = button("Comprobar activación", () => void checkActivation(), "schema-model-retry");
  retry.hidden = true;
  const recover = button("Descartar seguimiento y empezar otra propuesta", () => {
    clearPending();
    void open({kind: mode, type: activeType});
  }, "schema-model-recover");
  recover.hidden = true;
  const newDraft = button("Preparar otra propuesta", () => void open({kind: mode, type: activeType}),
    "schema-model-new-draft");
  newDraft.hidden = true;
  sheet.append(top, intro, availability, assistant, form, preview, retry, recover, newDraft);
  root.append(sheet);

  let generation = 0;
  let current = null;
  let proposed = null;
  let pendingId = null;
  let mode = "new";
  let activeType = null;
  let canConfirm = false;
  let busy = false;
  let priorClarification = null;
  let preservedProperties = null;

  function invalidate() {
    generation += 1;
    proposed = null;
    pendingId = null;
    busy = false;
  }

  function setBusy(value) {
    busy = value;
    confirm.disabled = value || !canConfirm || !proposed;
    retry.disabled = value;
    ask.disabled = value;
    request.input.disabled = value;
    for (const field of form.querySelectorAll("input")) field.disabled = value;
    for (const field of form.querySelectorAll("textarea")) field.disabled = value;
    for (const field of form.querySelectorAll("select")) field.disabled = value;
  }

  function build() {
    form.replaceChildren();
    const isNew = mode === "new";
    const name = entry(isNew ? "¿Cómo se llama este tipo de nota?" : "¿Qué información quieres añadir?",
      isNew ? "Ej.: Libro" : "Ej.: Autor");
    const description = entry(isNew ? "¿Para qué quieres guardar estas notas?" : "¿Qué significa este dato?",
      isNew ? "Ej.: Libros que leo o quiero leer" : "Ej.: Quién escribió este libro", {multiline: true});
    const properties = isNew ? entry("¿Qué datos particulares quieres recordar? (opcional)",
      "Ej.: autor, número de páginas, estado de lectura") : null;
    const typeSelector = !isNew ? control("select", "schema-model-input") : null;
    if (typeSelector) {
      for (const [value, text] of [["string", "Texto"], ["integer", "Número entero"], ["date", "Fecha completa"], ["array[string]", "Lista de textos"]]) {
        const option = control("option", "", text);
        option.value = value;
        typeSelector.append(option);
      }
      const wrapper = control("label", "schema-model-field");
      wrapper.append(control("span", "schema-model-label", "¿Cómo guardar este dato?"), typeSelector);
      form.append(name.wrapper, description.wrapper, wrapper);
    } else {
      form.append(name.wrapper, description.wrapper, properties.wrapper);
    }
    const hint = control("p", "schema-model-hint", "Vista guiada provisional: la interpretación libre con IA está aún en preparación. Las propiedades nuevas serán consultables por defecto.");
    const go = button("Ver propuesta", () => void propose(), "schema-model-propose");
    form.append(hint, go);
    return {name: name.input, description: description.input, properties: properties?.input, typeSelector};
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); void propose(); });
  sheet.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      sheet.hidden = true;
      invalidate();
    }
  });

  let fields = null;
  function change() {
    const name = fields.name.value.trim();
    const description = fields.description.value.trim();
    const id = stableId(name);
    if (!id || !/^[a-z][a-z0-9_]{0,63}$/.test(id) || !description || name.length > 120 || description.length > 1000) {
      throw new Error("Indica un nombre y una explicación. El nombre debe empezar por una letra y ser identificable.");
    }
    if (mode === "new") {
      const labels = (fields.properties.value || "").split(",").map((x) => x.trim()).filter(Boolean);
      if (labels.length > 6) throw new Error("Añade como máximo seis datos por propuesta.");
      const ids = labels.map(stableId);
      if (ids.some((item) => !/^[a-z][a-z0-9_]{0,63}$/.test(item)) || new Set(ids).size !== ids.length) {
        throw new Error("Revisa los nombres de los datos: algunos están repetidos o no son identificables.");
      }
      const removedTyped = preservedProperties && [...preservedProperties].some(([previousId, property]) =>
        property.value_type !== "string" && !ids.includes(previousId));
      // Removing an unwanted property is safe. A simultaneous replacement by
      // an unfamiliar ID could be a rename that silently loses its value_type.
      if (removedTyped && ids.some((candidate) => !preservedProperties.has(candidate))) {
        throw new Error("Puedes quitar datos de la propuesta. Para cambiar el nombre de uno numérico o de fecha sin perder su tipo, pide otra propuesta a Odyssey.");
      }
      return {operation: "add_type", type: {id, name, description, examples: [],
        properties: labels.map((label, index) => {
          const previous = preservedProperties?.get(ids[index]);
          return {id: ids[index], value_type: previous?.value_type ?? "string",
            description: previous?.description ?? label};
        })}};
    }
    if (!activeType?.id) throw new Error("Este tipo no está disponible.");
    return {operation: "add_property", type_id: activeType.id,
      property: {id, description, value_type: fields.typeSelector.value}};
  }

  async function open({kind = "new", type = null} = {}) {
    invalidate();
    sheet.hidden = false;
    preview.hidden = true;
    retry.hidden = true;
    recover.hidden = true;
    newDraft.hidden = true;
    assistant.hidden = false;
    assistantReply.textContent = "";
    request.input.value = "";
    priorClarification = null;
    preservedProperties = null;
    form.hidden = true;
    current = null;
    canConfirm = false;
    mode = kind;
    activeType = type;
    availability.textContent = "Comprobando si el editor está disponible…";
    const seq = generation;
    try {
      const result = await client({endpoint, operation: "schema_status"});
      if (seq !== generation || sheet.hidden) return;
      current = result;
      canConfirm = result.can_confirm === true;
      if (result.status !== "ready") throw new Error("El modelo no está listo para proponer cambios.");
      const previousId = readPending();
      if (previousId) {
        pendingId = previousId;
        retry.hidden = false;
        availability.textContent = "Hay una confirmación anterior. Comprobando si Odyssey ya la ha activado…";
        await checkActivation();
        if (seq !== generation || sheet.hidden) return;
        return;
      }
      if (kind !== "new" && !activeType?.id) throw new Error("No se encuentra el tipo de nota.");
      fields = build();
      form.hidden = false;
      availability.textContent = canConfirm
        ? "Describe el cambio y revisa la propuesta antes de aprobarla."
        : "Puedes preparar y revisar propuestas. Su confirmación todavía no está habilitada.";
      fields.name.focus();
    } catch {
      if (seq === generation) availability.textContent =
        "Este editor aún no está disponible en esta instalación de Odyssey.";
    }
  }

  function showPreview(draft, result, explanation = "") {
    proposed = {draft, result};
    summary.replaceChildren();
    summary.append(control("h3", "", result.type_preview.name),
      control("p", "", result.type_preview.description));
    const list = control("ul", "");
    for (const property of result.type_preview.properties) {
      list.append(control("li", "", `${property.description} (${property.value_type})`));
    }
    if (result.type_preview.properties.length) summary.append(list);
    confirmation.textContent = canConfirm
      ? "Confirma solo si esta propuesta refleja lo que quieres. Odyssey la activará al reiniciar; las notas anteriores no se modificarán con esta operación."
      : "Es una vista previa. La aprobación y el análisis de las notas anteriores aún no están habilitados.";
    form.hidden = true;
    preview.hidden = false;
    availability.textContent = explanation || "Propuesta validada: ningún cambio ha sido aplicado.";
  }

  async function suggest() {
    if (busy || !current || current.status !== "ready" || pendingId) return;
    const message = request.input.value.trim();
    if (!message || message.length > 1200) {
      assistantReply.textContent = "Explica brevemente qué quieres organizar.";
      return;
    }
    // The model's prior question is NOT user evidence. Source-grounding
    // must inspect only literal user utterances, never assistant-generated text.
    const source = priorClarification
      ? `${priorClarification.source}\n${message}`
      : message;
    if (source.length > 1200) {
      assistantReply.textContent = "La explicación es demasiado larga. Resúmela en un solo mensaje.";
      return;
    }
    invalidate();
    const seq = generation;
    setBusy(true);
    assistantReply.textContent = "Odyssey está revisando qué modelo de nota necesitas…";
    try {
      const result = await client({endpoint, operation: "schema_suggest", payload: {
        message: source, expected_revision: current.revision,
      }});
      if (seq !== generation || sheet.hidden) return;
      if (result.decision === "PROPOSE") {
        priorClarification = null;
        assistantReply.textContent = result.message;
        showPreview(result.change, result.preview,
          "Propuesta de la IA comprobada por Core. Todavía no se ha aplicado ningún cambio.");
      } else if (result.decision === "CLARIFY") {
        priorClarification = {source, question: result.message};
        assistantReply.textContent = `${result.message} Responde con una frase completa para que Odyssey pueda comprobar tus propias palabras.`;
        request.input.value = "";
        request.input.focus();
      } else {
        priorClarification = null;
        assistantReply.textContent = result.message;
      }
    } catch {
      if (seq === generation) assistantReply.textContent =
        "El asistente de IA no está habilitado o no ha podido preparar la propuesta. Puedes usar las preguntas guiadas sin activar ningún cambio.";
    } finally {
      if (seq === generation) setBusy(false);
    }
  }

  async function propose() {
    if (busy || !current || current.status !== "ready") return;
    let draft;
    try { draft = change(); } catch (error) {
      availability.textContent = error.message;
      return;
    }
    invalidate();
    const seq = generation;
    setBusy(true);
    availability.textContent = "Comprobando compatibilidad con tus tipos actuales…";
    try {
      const result = await client({endpoint, operation: "schema_preview", payload: {
        change: draft, expected_revision: current.revision,
      }});
      if (seq !== generation || sheet.hidden) return;
      showPreview(draft, result);
    } catch (error) {
      if (seq === generation) availability.textContent = error?.code === "SCHEMA_REVISION_STALE"
        ? "Los tipos han cambiado. Cierra y vuelve a abrir para preparar una propuesta actualizada."
        : "Odyssey no ha podido validar esa propuesta. Puedes ajustarla e intentarlo de nuevo.";
    } finally {
      if (seq === generation) setBusy(false);
    }
  }

  async function submit() {
    if (busy || !proposed || !canConfirm) return;
    const seq = generation;
    const proposal = proposed;
    let requestId;
    try { requestId = newRequestId(); } catch (error) {
      availability.textContent = error.message;
      return;
    }
    // The deliberate button click is the one approval. No model, network
    // response, or status poll can call this action on its own.
    savePending(requestId); // survive browser refresh before the HTTP acknowledgement
    setBusy(true);
    confirm.disabled = true;
    availability.textContent = "Registrando tu confirmación…";
    try {
      const result = await client({endpoint, operation: "schema_confirm", payload: {
        change: proposal.draft, expected_revision: proposal.result.revision,
        proposal_hash: proposal.result.proposal_hash, request_id: requestId,
      }});
      if (seq !== generation || sheet.hidden) return;
      pendingId = result.request_id;
      proposed = null; // One explicit click may authorize only one proposal.
      retry.hidden = false;
      preview.hidden = true;
      availability.textContent = result.status === "queued"
        ? "Cambio aprobado. Odyssey lo está activando; puedes comprobar el resultado aquí."
        : "Cambio activo. Ya puedes consultar este tipo desde Notas.";
      if (result.status === "active") {
        clearPending();
        retry.hidden = true;
        newDraft.hidden = false;
        onActive();
      }
    } catch {
      if (seq === generation) availability.textContent =
        "No se ha podido verificar la confirmación. No la repitas: comprueba primero el estado en Odyssey.";
      // Do not blindly retry a possibly committed mutation with a new ID.
      pendingId = requestId;
      proposed = null; // Ambiguous HTTP ACK: never resubmit with a fresh ID.
      retry.hidden = false;
    } finally {
      if (seq === generation) setBusy(false);
    }
  }

  async function checkActivation() {
    if (!pendingId || busy) return;
    const seq = generation;
    const id = pendingId;
    setBusy(true);
    try {
      const result = await client({endpoint, operation: "schema_status", payload: {request_id: id}});
      if (seq !== generation || sheet.hidden) return;
      availability.textContent = result.status === "active"
        ? "Cambio activo. El nuevo modelo está disponible en Notas."
        : "Odyssey sigue activando el cambio. Puedes volver a comprobarlo.";
      if (result.status === "active") {
        retry.hidden = true;
        newDraft.hidden = false;
        clearPending();
        pendingId = null;
        onActive();
      }
    } catch (error) {
      if (seq === generation) {
        if (error?.code === "SCHEMA_ACTIVATION_NOT_FOUND") {
          // A typed negative receipt is different from a timeout. Only the
          // explicit recovery action can discard its original request ID.
          availability.textContent = "Odyssey confirma que no existe esta solicitud para tu usuario. Puedes descartar el seguimiento y empezar otra propuesta.";
          recover.hidden = false;
          retry.hidden = true;
        } else {
          availability.textContent = "El servidor puede estar reiniciándose. Vuelve a comprobar el estado; no confirmes otra vez.";
        }
      }
    } finally {
      if (seq === generation) setBusy(false);
    }
  }

  return {open, close: () => { sheet.hidden = true; invalidate(); }, element: sheet};
}
