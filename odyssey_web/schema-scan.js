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

/** Mount an explicit, page-by-page local scan control into the note-model sheet. */
export function createSchemaScanPanel({root, endpoint = "/api/notes", client = requestNotes} = {}) {
  const panel = item("section", "schema-model-scan");
  panel.hidden = true;
  panel.append(item("h3", "", "Revisar notas existentes"));
  const explanation = item("p", "", "Puedes buscar información anterior por lotes. Por ahora solo se cuentan las fuentes: Odyssey no modifica tus notas ni crea entidades.");
  const status = item("p", "schema-model-scan-status", "");
  status.setAttribute("role", "status");
  const advanceButton = item("button", "schema-model-button schema-model-scan-advance", "Examinar 20 notas");
  advanceButton.type = "button";
  const statusButton = item("button", "schema-model-button schema-model-scan-recover", "Recuperar avance local");
  statusButton.type = "button";
  panel.append(explanation, status, advanceButton, statusButton);
  root.append(panel);

  let target = null;
  let busy = false;
  let generation = 0;

  function render(data, isHistorical = false) {
    if (data.status === "not_started") {
      status.textContent = "No se ha iniciado ningún análisis para este tipo de nota.";
      advanceButton.hidden = false;
      advanceButton.textContent = "Examinar 20 notas";
      return;
    }
    const context = isHistorical ? "Avance guardado (todavía sin verificar si las notas han cambiado): " : "";
    status.textContent = context + data.scanned_paths + " notas examinadas; " +
      data.eligible_notes + " fuentes candidatas; " + data.skipped_existing_values + " con valor previo; " +
      data.legacy_sources + " con texto antiguo sin trazabilidad completa. " +
      (data.status === "complete" ? "Lectura finalizada, sin modificar notas." :
        "Puedes examinar el siguiente lote.");
    advanceButton.hidden = data.status === "complete" && !isHistorical;
    advanceButton.textContent = "Continuar: examinar otras 20 notas";
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

  advanceButton.addEventListener("click", () => void request("advance"));
  statusButton.addEventListener("click", () => void request("status"));

  function show({scanKind, typeId, propertyId = null, revision}) {
    generation += 1;
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
    advanceButton.textContent = "Examinar 20 notas";
    status.textContent = "Puedes empezar o recuperar el avance anterior de este tipo.";
    void request("status");
  }

  function hide() {
    generation += 1;
    panel.hidden = true;
    target = null;
  }
  return {panel, show, hide, advance: () => request("advance")};
}
