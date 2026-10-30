/** Presentation-only C4 sidecar. No model text, writing or retries. */

const ACTION_COPY = {
  REVIEW_SAFE_RETRY: "Se puede revisar la interpretación, sin repetir todavía la solicitud.",
  CHECK_SYSTEM: "Hay que comprobar el servicio antes de intentar otra operación.",
  INSPECT_RESULT: "Comprueba el resultado antes de decidir si quieres repetir la solicitud.",
};

const ICONS = new Set(["router","temporal","planner","tasks","core","git","index","pending","result"]);

export function validatedDeferredDiagnosis(value, requestId, originalStatus, ledger) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join(",") !== "diagnosis,receipt_evidence,request_id,status,version" ||
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
  // Actor-scoped evidence is reconstructed server-side from the immutable E3
  // receipt, so it remains available after ConversationStore strips live E2
  // details from history. The model cannot choose its own grounding.
  const proof = value.receipt_evidence;
  if (!proof || typeof proof !== "object" || Array.isArray(proof) ||
      Object.keys(proof).sort().join(",") !== "reason_code,stages,status,version,write_evidence" ||
      proof.version !== 1 || proof.status !== originalStatus ||
      proof.reason_code !== d.reason_code || proof.write_evidence !== d.write_evidence ||
      !Array.isArray(proof.stages) || proof.stages.length < 1 || proof.stages.length > 64 ||
      !proof.stages.every(st => st && typeof st === "object" && !Array.isArray(st) &&
        Object.keys(st).sort().join(",") === "name,outcome,parent_stage,route_index,stage_view" &&
        typeof st.name === "string" && st.name.length > 0 && st.name.length <= 80 &&
        ["failed", "unavailable"].includes(st.outcome) &&
        (st.route_index === null || Number.isInteger(st.route_index) &&
          st.route_index >= 0 && st.route_index <= 31) &&
        (st.parent_stage === null || typeof st.parent_stage === "string" &&
          st.parent_stage.length > 0 && st.parent_stage.length <= 80) &&
        st.stage_view && typeof st.stage_view === "object" &&
        !Array.isArray(st.stage_view) &&
        Object.keys(st.stage_view).sort().join(",") === "icon,label,version" &&
        st.stage_view.version === 1 &&
        typeof st.stage_view.label === "string" && st.stage_view.label.length > 0 &&
        st.stage_view.label.length <= 80 && !/[\r\n<>]/.test(st.stage_view.label) &&
        ICONS.has(st.stage_view.icon))) return null;
  const stages = proof.stages;
  if (!stages.some(st => st.name === d.evidence_stage && st.route_index === d.route_index &&
        st.stage_view.label === view.label && st.stage_view.icon === view.icon &&
        st.stage_view.version === view.version) ||
      stages.some(st => st.parent_stage === d.evidence_stage &&
        st.route_index === d.route_index)) return null;
  // When the current response includes E2, it must agree independently with
  // the reconstructed E3 proof. The server projection alone covers reloads.
  if (ledger && (!Array.isArray(ledger.stages) ||
      ledger.status !== originalStatus ||
      !Array.isArray(ledger.affected_stable_note_ids) ||
      (ledger.affected_stable_note_ids.length > 0 ? "SOME" : "UNKNOWN") !== d.write_evidence ||
      !ledger.stages.some(st => st?.name === d.evidence_stage &&
        st.route_index === d.route_index && ["failed", "unavailable"].includes(st.outcome) &&
        st.stage_view?.label === view.label && st.stage_view?.icon === view.icon &&
        st.stage_view?.version === view.version) ||
      ledger.stages.some(st => st?.parent_stage === d.evidence_stage &&
        st.route_index === d.route_index &&
        ["failed", "unavailable"].includes(st.outcome)))) return null;
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
