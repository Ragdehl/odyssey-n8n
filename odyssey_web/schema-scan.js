/** Read-only schema retrospective preview. Scans are local to the trusted profile.
 * No candidate identities or note mutations are accepted over this UI boundary.
 */
import {requestNotes} from "./notes-client.js";

function item(tag, name, content = "") {
  const element = document.createElement(tag);
  element.className = name;
  element.textContent = content;
  return element;
}

/** Mount a resumable automatic read-only scan into the note-model sheet. */
export function createSchemaScanPanel({root, endpoint = "/api/notes", client = requestNotes} = {}) {
  const panel = item("section", "schema-model-scan");
  panel.hidden = true;
  panel.append(item("h3", "", "Revisar notas existentes"));
  const explanation = item("p", "", "Odyssey revisa tus notas existentes automáticamente y guarda el progreso localmente. Esta etapa muestra las fuentes encontradas; el enriquecimiento de las notas se incorporará después.");
  const status = item("p", "schema-model-scan-status", "");
  status.setAttribute("role", "status");
  const advanceButton = item("button", "schema-model-button schema-model-scan-advance", "Analizar notas existentes");
  advanceButton.type = "button";
  const statusButton = item("button", "schema-model-button schema-model-scan-recover", "Recuperar avance local");
  statusButton.type = "button";
  const pauseButton = item("button", "schema-model-button schema-model-scan-pause", "Pausar análisis");
  pauseButton.type = "button";
  pauseButton.hidden = true;
  panel.append(explanation, status, advanceButton, statusButton, pauseButton);
  root.append(panel);

  let target = null;
  let busy = false;
  let generation = 0;
  let running = false;
  let pauseRequested = false;
  // Avoid an unbounded request loop in a foreground/mobile page. The next
  // click resumes the same durable checkpoint without restarting the vault.
  const MAX_PAGES_PER_RUN = 50;

  function render(data, isHistorical = false) {
    if (data.status === "not_started") {
      status.textContent = "No se ha iniciado ningún análisis para este tipo de nota.";
      advanceButton.hidden = false;
      advanceButton.textContent = "Analizar notas existentes";
      return;
    }
    const context = isHistorical ? "Avance guardado (todavía sin verificar si las notas han cambiado): " : "";
    status.textContent = context + data.scanned_paths + " notas examinadas; " +
      data.eligible_notes + " fuentes candidatas; " + data.skipped_existing_values + " con valor previo; " +
      data.legacy_sources + " con texto antiguo sin trazabilidad completa. " +
      (data.status === "complete" ? "Lectura finalizada, sin modificar notas." :
        "El análisis puede continuar automáticamente.");
    advanceButton.hidden = data.status === "complete" && !isHistorical;
    advanceButton.textContent = "Continuar análisis";
  }

  async function request(action) {
    if (!target || busy) return;
    busy = true;
    advanceButton.disabled = statusButton.disabled = true;
    const seq = generation;
    status.textContent = action === "advance" ? "Leyendo un lote en el almacenamiento local…" :
      "Consultando el avance guardado…";
    try {
      const result = await client({endpoint, operation: "schema_scan", payload: {...target, action}});
      if (seq !== generation || panel.hidden) return;
      render(result, action === "status");
    } catch (error) {
      if (seq === generation) {
        status.textContent = error?.code === "SCHEMA_SCAN_STALE_OR_INVALID"
          ? "Las notas o el modelo han cambiado, o el avance no es válido. No se ha continuado el análisis. La revisión necesitará reiniciarse de forma controlada."
          : "El análisis local no está habilitado o no se ha podido comprobar. No se han cambiado tus notas.";
        advanceButton.hidden = true;
      }
    } finally {
      if (seq === generation) {
        busy = false;
        advanceButton.disabled = statusButton.disabled = false;
      }
    }
  }

  async function scanAll() {
    if (!target || busy || running) return;
    running = true;
    pauseRequested = false;
    advanceButton.disabled = true;
    statusButton.disabled = true;
    pauseButton.hidden = false;
    const seq = generation;
    let complete = false;
    let interrupted = false;
    let count = 0;
    try {
      for (; count < MAX_PAGES_PER_RUN && !pauseRequested; count += 1) {
        // Never mutate Notes here; each call returns a bounded read-only
        // checkpoint committed by the device-local Core storage.
        const result = await client({endpoint, operation: "schema_scan",
          payload: {...target, action: "advance"}});
        if (seq !== generation || panel.hidden) return;
        render(result);
        if (result.status === "complete") {complete = true; break;}
        if (result.status !== "scanning") throw new Error("Invalid scan progress");
      }
    } catch (error) {
      interrupted = true;
      if (seq === generation) {
        status.textContent = error?.code === "SCHEMA_SCAN_STALE_OR_INVALID"
          ? "El modelo o las notas han cambiado; no se ha continuado el análisis. No se han modificado notas."
          : "El análisis se ha detenido por un error; el avance anterior sigue guardado.";
      }
    } finally {
      if (seq === generation) {
        running = false;
        pauseButton.hidden = true;
        advanceButton.disabled = statusButton.disabled = false;
        advanceButton.hidden = complete || interrupted;
        if (!complete && !interrupted && !pauseRequested && count >= MAX_PAGES_PER_RUN) {
          status.textContent += " Pausa de rendimiento tras 1.000 archivos: puedes continuar desde este punto.";
        } else if (pauseRequested && !complete && !interrupted) {
          status.textContent += " Análisis pausado; puedes reanudarlo cuando quieras.";
        }
      }
    }
  }

  advanceButton.addEventListener("click", () => void scanAll());
  statusButton.addEventListener("click", () => void request("status"));
  pauseButton.addEventListener("click", () => {pauseRequested = true;});

  function show({scanKind, typeId, propertyId = null, revision, autoStart = false}) {
    generation += 1;
    running = false;
    pauseRequested = false;
    pauseButton.hidden = true;
    if (!["discover_type", "backfill_property"].includes(scanKind) ||
        !/^[a-z][a-z0-9_]{0,63}$/.test(typeId ?? "") ||
        (scanKind === "discover_type" ? propertyId !== null :
          !/^[a-z][a-z0-9_]{0,63}$/.test(propertyId ?? "")) ||
        !Number.isSafeInteger(revision) || revision < 0 || revision > 100) {
      throw new Error("El análisis necesita un tipo y una revisión canónica.");
    }
    target = {scan_kind: scanKind, target_type_id: typeId,
      property_id: propertyId, expected_revision: revision};
    panel.hidden = false;
    advanceButton.hidden = false;
    advanceButton.textContent = "Analizar notas existentes";
    status.textContent = "Puedes empezar o recuperar el avance anterior de este tipo.";
    const seq = generation;
    void request("status").then(() => {
      if (autoStart && seq === generation && !panel.hidden && !busy &&
          !advanceButton.hidden) void scanAll();
    });
  }

  function hide() {
    generation += 1;
    running = false;
    pauseRequested = true;
    pauseButton.hidden = true;
    panel.hidden = true;
    target = null;
  }
  return {panel, show, hide, advance: scanAll};
}
