---
name: odyssey-results
description: Report verified Odyssey development results and continuity in a consistent concise format; use after implementation, audits, tests, PR changes, before stopping, and whenever the user asks what was done, what is happening, what is missing, examples or future stages. Not a substitute for running verification.
---

# Odyssey development results — reusable user update

Prefer a **single scannable progress report** based on the current code/PR, the canonical roadmap and observed test/deployment receipts. Invoke `odyssey-start-work` if state is stale or unclear. Follow `odyssey-verify-change` to assess code, and its independent-audit timing; this skill **only reports** evidence, never turns predictions into PASS.

## Consistent user-facing structure

For substantial work or a continuation, use these sections **in this order**, scaled to the amount of progress. In Spanish by default when conversing in Spanish:

1. **En una frase / estado global** — outcome and current scope, e.g. `implemented in source, not yet in DEV` instead of unqualified `done`.
2. **Qué he hecho desde la última vez** — 2–5 concrete changes, with an **example before → after** or a realistic user story showing what works. If no changes, explicitly say so.
3. **Pruebas y auditorías** — report exact passing/failing counts and tested SHA where known, which checks were synthetic vs real-model vs real-browser vs deployed; for Codex name Generalidad, Calidad, Pruebas, Rendimiento individually as PASS/FAIL/BLOCKED/NOT RUN when available, and next audit gate. Never call a local unit test an app end-to-end test. NEVER present a completed user-facing architecture/LLM stage without `--require-stage-accepted Rn` passing on the pinned source and independently inspected real browser/model/Markdown receipts. If blocked, state `ETAPA NO ACEPTADA`, name missing cases and actual model/browser status. The default CI integrity check is NOT a live E2E check.
4. **En qué estamos y qué falta para cerrar esta etapa** — current task, short ordered blockers, whether a blocker needs user action. Distinguish `planned`, `in progress`, `implemented`, `verified`, `deployed`, and `merged`.
5. **Próximos pasos** — the next 1–3 executable actions, then **siguientes fases** in roadmap order (not just a technical rabbit hole).
6. **Estado de entrega** — branch/commit/PR, CI, DEV deployed SHA, PROD status and user-data changes **only when verified**. If not checked, say `no comprobado` rather than claiming unchanged.

For a small edit or quick status request, condense to a paragraph and small table; keep the same conceptual fields without six empty headings. Include real examples proactively whenever a feature was implemented or a failure was found. Avoid every low-level file or token count unless material. No invented percentage complete, ETA, cost, or automatic notification.

## Example: good progress update

**Estado:** editor de tipos listo en código y probado parcialmente en DEV; el recorrido con IA sigue pendiente.

- **Ejemplo real:** en la app de pruebas, el usuario creó `Ficha tarjetas`, cambió `cantidad` a entero y confirmó; Core registró el tipo y se comprobó tras reinicio. **No equivale** a creación asistida por GPT ya verificada.
- **Pruebas:** 2.176 Python y 233 JS PASS en `3994569`; los cuatro auditores de cierre: **NO EJECUTADOS** para ese commit.
- **Ahora:** conectar el descubrimiento retrospectivo y el backfill autorizado. **Falta:** deduplicación, confirmación por lotes, CAS y recorrido de usuario con IA real.
- **Después:** auditar los cuatro roles sobre el SHA candidato, corregir defectos, E2E y fusionar la PR solo con permiso. **Luego:** Recordatorios → ubicación → Proyectos/Gantt.
- **Entrega:** PR #156 en borrador; DEV en `5e340da`, no afirmar que `3994569` está desplegado.

## Guardrails for continuity

- Keep the **single canonical current-state owner** (`docs/architecture/functional-roadmap.md`) truthful; do not append a new historical narrative to it every time. Durable findings live in the relevant contract/PR/audit receipt.
- Always distinguish results of **this turn** from previously verified checkpoints and from intended next steps.
- Mention what remains after the immediate phase, including user-facing product capabilities, if known.
- Explicitly explain an interrupted/blocked audit and the next condition that would trigger it. Never quietly imply the Codex agents already ran.
- A report is not a long checklist for the user; continue authorized work without repeatedly asking for nonessential approval.
