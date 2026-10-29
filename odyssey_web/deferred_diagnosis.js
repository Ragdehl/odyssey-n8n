/** Presentation-only C4 sidecar. No model text, writing or retries. */

const ACTION_COPY = {
  REVIEW_SAFE_RETRY: "Se puede revisar la interpretación, sin repetir todavía la solicitud.",
  CHECK_SYSTEM: "Hay que comprobar el servicio antes de intentar otra operación.",
  INSPECT_RESULT: "Comprueba el resultado antes de decidir si quieres repetir la solicitud.",
};

const ICONS = new Set(["router","temporal","planner","tasks","core","git","index","pending","result"]);

export function validatedDeferredDiagnosis(value, requestId, originalStatus, ledger) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join(",") !== "diagnosis,request_id,status,version" ||
      value.version !== 1 || value.request_id !== requestId || value.status !== "completed" ||
      !["failed","partial","needs_attention"].includes(originalStatus)) return null;
  const d = value.diagnosis;
  if (!d || typeof d !== "object" || Array.isArray(d) ||
      Object.keys(d).sort().join(",") !== "evidence_stage,next_step,reason_code,route_index,stage_view,status,verified_stage_only,write_evidence" ||
      d.verified_stage_only !== true || d.status !== originalStatus ||
      typeof d.evidence_stage !== "string" || d.evidence_stage.length > 80 ||
      !Object.hasOwn(ACTION_COPY, d.next_step) ||
      !["UNKNOWN","SOME"].includes(d.write_evidence) ||
      typeof d.reason_code !== "string" || d.reason_code.length > 120) return null;
  const view = d.stage_view;
  if (!view || typeof view !== "object" || Array.isArray(view) ||
      Object.keys(view).sort().join(",") !== "icon,label,version" ||
      view.version !== 1 || typeof view.label !== "string" ||
      view.label.length < 1 || view.label.length > 80 ||
      /[\r\n<>]/.test(view.label) || !ICONS.has(view.icon)) return null;
  const stages = ledger?.stages;
  if (!Array.isArray(stages) ||
      !stages.some(st => st?.name === d.evidence_stage && st.route_index === d.route_index &&
        ["failed","unavailable"].includes(st.outcome) &&
        st.stage_view?.label === view.label && st.stage_view?.icon === view.icon &&
        st.stage_view?.version === view.version) ||
      stages.some(st => st?.parent_stage === d.evidence_stage &&
        st.route_index === d.route_index && ["failed","unavailable"].includes(st.outcome))) return null;
  const summary = d.write_evidence === "SOME"
    ? "Algunos cambios están confirmados, pero el resultado completo no."
    : "No se ha podido confirmar si hubo cambios.";
  return summary + " El problema se observó en «" + view.label + "». " + ACTION_COPY[d.next_step];
}

export async function pollDeferredDiagnosis({
  request, requestId, originalStatus, ledger, onResult,
  delay = ms => new Promise(resolve => setTimeout(resolve, ms)),
  maxAttempts = 24,
}) {
  if (typeof request !== "function" || typeof onResult !== "function" ||
      !Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 30) return;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let value;
    try {
      value = await request(requestId);
    } catch {
      return; // Optional advice must never replace or fail the base reply.
    }
    if (!value || value.request_id !== requestId) return;
    if (value.status === "completed") {
      const message = validatedDeferredDiagnosis(value, requestId, originalStatus, ledger);
      if (message) onResult(message);
      return;
    }
    if (value.status !== "pending") return;
    await delay(1250);
  }
}
