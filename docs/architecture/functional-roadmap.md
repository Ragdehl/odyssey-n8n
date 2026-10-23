# Functional Roadmap — Odyssey

**Normative current-state entry point.** Verify these snapshots against Git and the actual DEV/PROD deployment marker before acting. **Historical checkpoints are NOT active decisions:** the complete previous 1,957-line roadmap is preserved at [October 2026 roadmap archive](functional-roadmap-history-20261023.md).

## Current — 23 October 2026

**Latest verified before the documentation refactor** (from Git/runtime checks; not a new deployment):
- GitHub `dev`, local source branch `dev`: `802d219`, clean at audit start. Zero open PRs; E1 #153 merged, E2 #154 closed because already incorporated, and E6 included in later `dev` ancestry. The working branch may advance independently; always inspect current HEAD.
- Real DEV checkout and `/data/odyssey-dev/runtime/deployed-commit`: `841918a`; both services last checked HTTP 200. E1–E6 incremental architecture is implemented and DEV-accepted in bounded functional checkpoints. **PROD not promoted by those DEV acceptances.**
- The Notes UI chronology (commit `c34d700`, included in DEV `841918a`) groups native facts and incoming references by original capture date, shows compact source links and subtle incoming-background, and has a successful deployed Chromium mobile+desktop read-only trial (8 dates / 43 references). No Markdown migration.
- Latest complete accumulated offline evidence at that UI checkpoint: **1857 Python + 184 JavaScript PASS**; separate real Event/Task/Work Session synthetic DEV evidence and E6 audits recorded in [E6 weekend regression](e6-weekend-regression-20261022.md), [E6 UI acceptance](ui-notes-unified-timeline-20261022.md) and [E6 checkpoint](e6-incremental-composition-checkpoint-20261022.md). Do not infer universal language or browser coverage.
- Historical E4 plural/collective `ambos` cases have documented uncertainty/abstention limits and focused tests. Do **not** reopen the same loop based only on a historic failing example; require a genuinely new reproducer and evidence.

## Next — active development

**Conversation C1–C3 — contrato integrado en código, desactivado por defecto (23-10-2026):** `RuntimeComposition.execute_product` conecta clasificación, historial actor-bound y respuestas C3, preservando la prioridad de aclaraciones Core/E3 y el texto original completo hacia Router cuando corresponde guardar. `workflows/odyssey-online.ts` proyecta únicamente un resultado de Chat validado sin permisos de escritura; la composición habilita el servicio solo con `ODYSSEY_CHAT_C3_ENABLED=1` y `ODYSSEY_DEPLOYMENT_ENV=DEV`. Pruebas de integración hasta ahora **1.999 Python + 187 JavaScript PASS**, 12 grupos. Prueba real de interfaz Chromium móvil con proveedor/puente **sintéticos**: dos mensajes enviados desde el formulario Odyssey, respuestas visibles, recarga persistente, cero escrituras y cuatro turnos guardados. Prompts de respuesta/ayuda anteriormente evaluados con Luna **8/8 + 8/8**, sin nueva matriz de integración real. **NO desplegado en DEV; APP E2E NOT VERIFIED** con n8n+GPT reales y el recorrido completo. Faltan auditoría independiente, campaña Luna integrada y autorización específica para adopción DEV y prueba final usuario→n8n→Core/E3→Markdown→UI. [Contrato y evidencias C3](conversation-chat-c3.md). Git HEAD y marker DEV deben verificarse antes de cada paso.

**Conversation C2 — isolated code and real prompt evaluation (23-10-2026):** actor-scoped exact-source conversation context (16 recent turns; up to 30 days / 48 historical turns), typed handoff preserving source, and optional second Luna classification; none connected to browser/n8n/DEV. Updated mandatory LLM skill to require *behavioral prompt tests with real provider*, not just strict JSON. Initial-stage real Luna matrix: V1 9/12, V2 11/12, **V3 12/12**. Second-stage original prompt (trying to certify referents) failed **2/3** and **14/19**. Revised C2.1 now asks Luna **only for intent**; every reference remains UNVERIFIED for Router/Core/E3. Bounded real-model main matrix **19/19** on final hash `0900ac84034e10e0`; independent multilingual holdout **10/10** on an immediately earlier hash, not a single combined score. C2 code is accepted for isolated experiments, **NOT yet approved for user-facing DEV adoption** pending C3/help, safe clarification handling and real integrated E2E. [Evidence and blockers](conversation-continuity-c2.md). Existing DEV/PROD untouched.

**Conversation C1 — primera implementación local (23-10-2026; aún no conectada a DEV):** se inventariaron y reutilizaron conversación persistente, Router Luna, contexto acotado, answerer, diagnóstico estructurado y aclaraciones. Nuevo contrato tipado `odyssey_runtime/conversation_gateway.py`: Luna ligero `ROUTER`/`CHAT`/`CONTEXT`, posterror `ERROR` solo con recibo verificado, referencia al mensaje original inalterado, lectura del contexto reciente con aislamiento de usuario y sin reintentos automáticos. Gate final **1.950 Python +184 JS PASS**, segunda auditoría independiente del contrato de errores **PASS** (la primera detectó y permitió corregir texto de error libre y suposición implícita de cero escrituras). Pruebas y manual recuperable bajo demanda; **sin nueva API/endpoints n8n, sin llamadas reales GPT ni cambios de datos o PROD**. Alcance y pendientes: [Conversation C1](conversation-front-door-c1.md). Próximo: integración segura en un flujo DEV con un modelo Chat/ayuda fundamentado, recuperación histórica por actor, evaluación real de clasificación y aclaraciones, y posterior explicación de errores; nunca promover el modelo a autoridad E3.

**Agent knowledge refactor finished in the source branch, documentation/tooling-only (23-10-2026):** always-on `AGENTS.md` shortened; the full earlier roadmap archived without deleting evidence; five new discoverable scoped skills including LLM-stage prompt inheritance; four existing skills retained (post-merge now uses the true PR base); one normative provider runbook; read-only context doctor, document guard, tests and dev/main CI wiring. Offline cross-surface gate **1862 Python +184 JavaScript PASS**; independent focused instructions audit **PASS**. No DEV/PROD deployment or real-model gate authorized by this cleanup. New source commit/remote state must be checked with Git.

**Next task:** return to a specific **user-selected** product feature, especially Notes/UI improvements or future capabilities. New Apps use incremental registered-App/Run/Writer contracts, only narrowly justified E6 extractions; no blanket Clean Architecture rewrite. Do not infer the next phase from historic E4/E5/E6 dates.

## Always-preserved product and validation contracts

1. **Local-first canonical Markdown / Core/E3** own identities, facts, target authorization and mutations. Router/Temporal/Apps provide bounded untrusted interpretation. `config/note-schema.json` owns exact machine schema.
2. **Generality:** candidates↔facts may be N:M; no per-phrase/name, note type, language or fixed participant/candidate-count exceptions. Preserve source scope, unknown/pending evidence, typed identity create vs complete-set literal distinction.
3. **No hidden deployment authority:** Git commit, successful offline tests, DEV deployed marker, authenticated browser E2E and PROD are different claims. Model-facing production changes require bounded authorized real-model evidence with the actual selected model/effort.
4. **Safety:** no unapproved mutation of PROD or private data, no secret logging, no forced Git pushes, destructive migrations or silent merge/deploy, preserve concurrent worktrees.

## Where details belong

| Need | Normative owner |
| --- | --- |
| Always-on agent rules / skill routing | [AGENTS.md](../../AGENTS.md) |
| Architecture and implemented boundaries | [Architecture overview](overview.md), [App extensibility plan](application-extensibility-plan.md) |
| Hybrid Router groups | [Hybrid interpretation contract](router-hybrid-interpretation-contract.md), [ADR 0010](../decisions/0010-router-hybrid-interpretation-groups.md) |
| Shared source/context/mutations | [E2 shared context](e2-shared-context-contract.md), Core/E3 contracts and tests |
| Process, quality, PRs | [Development pipeline](development-pipeline.md), [testing](testing.md), [acceptance ledger](odyssey-acceptance-contracts.json) |
| Raspberry/DEV/provider/PROD operations | [Raspberry runbook](../infrastructure/raspberry-runtime.md), [DEV isolation](phase-21-development-isolation.md) |
| How to invoke specialized work | [Instruction map](instruction-map.md), `.codex/skills/` |
| Historic evidence/older decisions | [Archived original roadmap](functional-roadmap-history-20261023.md), dated phase reports and versioned benchmarks |

**Maintenance:** update only the current facts above for each substantive acceptance. Move a superseded snapshot into the linked evidence report, not another 'ESTADO VIGENTE' paragraph here. Verify actual Git/deployed state each time, and do not change older receipts.
