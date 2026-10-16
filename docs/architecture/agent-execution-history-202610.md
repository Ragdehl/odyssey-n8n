# Agent execution history — October 2026 (archived verbatim)

Historical agent checkpoints preserved **verbatim** from `AGENTS.md` to reduce agent-facing instruction bloat. These notes are not current product status or additional write authority.

The canonical status is [Functional Roadmap](functional-roadmap.md), latest active heading. The architecture contract is [Application Extensibility Plan](application-extensibility-plan.md).

---

### 2026-10-16 — P4 five-stage stabilized isolated follow-up (NO DEV)

Read `docs/architecture/p4-five-stage-evidence-20261016.md` and the newest heading in `docs/architecture/functional-roadmap.md` before proceeding. Five areas advanced IN FEATURE BRANCH ONLY: GPT Router distinguishes Work Session activity as Tasks (10/10 fresh-model Tasks-only interpretations), Core expands group references only with current authenticated SELF fact and rechecks it before each write (real GPT synthetic children proof), E3 claim forensics are read-only and do NOT retry/clear unresolved mutation, P4-only per-request/raw-Markdown decode cache reduced synthetic 1000-note wall time ~5.23s→~4.10s still too slow, local HTTP Chat→Core Tasks Work Session→UI Notes demonstrates same physical session without real n8n/browser. Mixed GPT record+Task still 3/4 in latest probe with one unresolved proposal; Core correctly abstains. Cross-surface 588 Py+168 Node PASS; global 3513 Py PASS/80 SKIP/same 10 historical. **Still BLOCKED for DEV and PROD** until genuine isolated browser→n8n→new P4→GPT→Writer→browser graph/donut/transcript and mixed Work Sessions, subtasks, E3 crash reconciliation and Raspberry performance are proven. Keep no blind retries, no real vault mutation, no deployment or merge.


### 2026-10-16 — P4 legacy validator audit / Core generic write-plan enrichment (NO DEV)

Before editing hybrid/P4 validators, consult `docs/architecture/p4-validator-boundary-audit-20261016.md` and `scripts/audit_semantic_validator_boundaries.py`: five identified narrow legacy/experimental adapters have explicit bounded consumers, **not** blanket authority for new Core Apps. Tasks' generic plan enrichment now belongs to `odyssey_core/write_plan_enrichment.py`; App adapters retain lifecycle/role meaning, no generic `KnowledgeUnit`/reference mechanics. Whole-source P4 compiles *every* operation before starting a mutation and verifies Task subrequest readbacks by exact source position. These are new branch changes, not deployed, and do not complete mixed Work Sessions, n8n/browser E2E, parent task NL capture or claim-crash reconciliation. Cross-surface 574 Python/168 Node PASS, full 3499 PASS/80 SKIP/same 10 historical, model variability still blocks DEV. Keep DEV `1474681` and PROD unchanged until comprehensive real E2E acceptance.


### 2026-10-16 — P4 HTTP aislado: hallazgo de duplicación Task y gate de producto bloqueado

Antes de cualquier cambio de Router, leer `docs/architecture/light-router-p4-http-evidence-20261016.md`. La prueba HTTP local auténtica con 5 mensajes y nuevas llamadas GPT+Core+Tasks (3 completos, 2 bloqueados, 5/5 replay, 97 Notes clonadas) NO atraviesa n8n ni DOM ni embeddings productivos. Se descubrió que Task force_create reejecutado tras un fallo posterior a escritura DUPLICA tareas; el opt-in `RuntimeComposition.full_source_mutation_guard=False` (por defecto inactivo) reserva un claim duradero E3 ANTES del write y lo libera tras el recibo. Ante caída → HTTP 500 inicial, retry HTTP 409 sin nueva escritura; no hay aún reconciliación automática. 208 backend + 143 Node focalizados y suite completa 3395 Python PASS/80 SKIP/mismos 10 fallos históricos; 165 Node PASS, pero mapeo n8n sin opciones de aclaración y falta observabilidad UI. NO desplegar ni pedir pruebas manuales hasta E2E **real** navegador→n8n→runtime→IA→Markdown→n8n→UI con vault aislado y múltiples escenarios variando el proveedor, validación de parciales y fallos. DEV sigue 1474681 y PROD no tocado.


### 2026-10-16 — Último estado P3: contrato Core y pruebas de Writer AISLADAS; P4 obligatorio

Leer [informe P3](docs/architecture/light-router-p3-results-20261016.md) junto con los receipts reales antes de continuar. La arquitectura ligera conserva mensaje íntegro y ya ha probado Core+Tasks+Writer sobre 97 Notes DEV clonadas: 5/6 casos correctos, Ana bloqueada; «mis hijos» 3 facts sin fecha escritos en SELF autenticado y backlinks Cloe+Bruno, 0 duplicados. Otros 5 casos adversos no escribieron. 256 pytest relevantes + 140 JS UI pasan. Nuevos contratos Core: `whole_message_coverage.py`, `whole_message_identity_guard.py`, `whole_message_relationship_proof.py`. **NINGUNO habilita la ruta nueva del chat**; aún NO se probó la ruta completa HTTP→n8n→UI ni índices de embedding reales y no se puede dar autorización DEV. P4 requiere una integración productiva separada de benchmarks, pruebas vivas de IA con payloads distintos, E3 idempotencia/partial, propietario de hechos no fechados, negativa/condicional, identidad segura, carga Raspberry y visualización; no despliegue PROD. No aplicar parches ligados a nombres concretos.


### 2026-10-16 — P2 integrada demostrada SOLO EN SANDBOX; P3/P4 pendientes

Leer `docs/architecture/light-router-p2-results-20261016.md` y los receipts `benchmarks/application_router/light_router_poc_20261016/p2_integration_receipts_fresh.json` antes de implementar el Router ligero. Una PoC con **GPT-6 + GPT-5.6 nuevos**, revisión independiente, Core Writer y Tasks reales ha escrito correctamente 5/6 escenarios en CLON temporal de las 97 Notes DEV, verificando Markdown, IDs, fechas y backlinks; «Ana» frente a «Ana López» queda sin escrituras (ambigüedad de identidad). 71 pruebas de regresión relevantes superadas. La entrada experimental NO pasa por el antiguo `candidate_coverage`; en su lugar dispone de una revisión provisional del mensaje completo que AÚN requiere formalización, tests adversariales e identidad canónica real. El resultado no autoriza DEV, no demuestra integración n8n/HTML, ni resuelve SELF/mis hijos sin fecha. No sustituir el Writer ni crear otra aplicación semántica; integrar el contrato revisado en Core/E2 por capacidades y preservar seguridad E3. No anunciar «listo para probar» hasta E2E nuevo de IA real con el vault y navegador DEV.


### 2026-10-16 — Override activo: Router ligero y gate de IA real (NO DEV)

La aceptación manual real del 16-10 falló gravemente: 16 mensajes en DEV, 5 completed, 1 partial y 10 needs_attention; los muchos tests aislados, frozen-provider y del Writer NO equivalían al comportamiento live con el vault, el estado y la UI. El usuario ha aprobado **investigar/probar** un Router ligero y un contexto original íntegro; NO ha aprobado la implementación ni el deploy. La PoC semántica real del 16-10 es prometedora (11 ejemplos), PERO Core/Writer actual en copia de DEV falló 0/3; la arquitectura sigue NO validada E2E. Leer antes de cualquier código [el diagnóstico/contrato/gates](docs/architecture/light-router-poc-20261016.md) y [los receipts PoC](benchmarks/application_router/light_router_poc_20261016/README.md), prevalecen sobre los recuentos históricos de 25/27. Próximo paso P2: puente de contexto íntegro/identidad/facts/Tasks/Writer probado contra vault descartable, con IA REAL y readback, sin bypass de validaciones ni apuntes genéricos. Solo después P3 implementación y gates n8n/UI/CPU/RAM antes de pruebas del usuario. No tocar PROD, ni instalar DEV, ni presuponer que ejemplos que funcionaron en fixture funcionarán en Notes reales.


### 2026-10-13 — LATEST hybrid status: 25 completed + 2 safe pending

Older 23/27 and 24/27 counts below are historical. F09 now passes:
two independent genuine GPT-5.6 semantic equivalence reviews confirm
Marta already has the complete Lyon fact, so her canonical Note is
unchanged. Luis receives the new fact. Current-note identity, content
hash and exact supporting quote are checked before a skip and again
during readback. Semantic review is optional, read-only, provider store
disabled, and bounded: long Notes remain writable, no truncated
existing context is allowed to certify an already-known fact.

F14/F27 already persist their independently proven prior conversation
facts. The new opt-in hybrid pending boundary now also stores their exact
original cinema source clause with captured date, reference and options
Eric/Luis proven by the previous Core-linked persisted fact. It does
NOT resolve "él" itself: it requires a user choice. The actual pending
v2 workflow and guarded subsequent Core continuation ("Con Luis") are
covered by deterministic replay of genuine Router/Temporal/Planner and
independent reviewer outputs. No second invented Person or Day fact.
If the callback is unavailable, source cannot be scoped, options change
or proof goes stale, never promote a candidate identity.
More than four plausible people may be kept as source-only pending,
not a misleading truncated choice list.

The strict score is therefore 25/27 fully completed; the other two
are correctly handled as durable pending clarification, NOT magically
fully resolved. This capability is not yet deployed in DEV or PROD.
When activating hybrid in DEV, wire the route ambiguity recorder to
authenticated per-conversation v2 Pending state and display choices in
the chat; do not claim live app support before then.

Evidence: benchmarks/application_router/hybrid_known_fact_v1/F09.json;
tests/runtime/test_hybrid_known_fact_real_review_20261013.py;
tests/runtime/test_hybrid_ambiguous_real_pending_20261013.py.
Last full-suite results on 2026-10-13: 3039 passed, 80 skipped,
the same 10 historical dated/version-hash failures; no new regressions.
Continue incremental Clean Architecture only when touching modules
for functional work, never a wholesale rewrite during DEV preparation.

### Regression memory for real chat failures

When a real Odyssey chat interaction reveals a new semantic failure mode, preserve that exact case as
a deterministic regression sentinel before considering the fix complete. If the failure depends on
LLM interpretation or prompt behavior, also run the smallest relevant live Luna check during the
change when credentials are available; keep deterministic tests as the CI authority so provider
variance never weakens the gate. Generalize the regression with additional note types or equivalent
shapes when the product invariant is type-generic. Do not remove or relax an accepted real-chat
sentinel merely to make a later prompt or architecture change pass.

### 2026-10-13 — Mandatory cross-boundary DEV observability and post-write gate

A passing backend write/read test is NOT enough to authorize manual DEV chat
testing. Any changed Core telemetry field or execution flow must be checked
through the generated n8n response contract AND the browser validator/graph;
unknown optional diagnostic metrics must never erase otherwise valid stages,
costs, or write outcomes. Assert real hybrid lifecycle progress events using
the authenticated progress store rather than assuming the donut advances.
When an error occurs after a physical canonical write, retain the verified
Core write receipt and affected note IDs, disclose partial completion and
block unsafe dependent handoff; do not convert it into an apparent zero-write
failure or retry using a new delivery ID. For each real user-chat regression,
record exact source/result and a provider-free crossing-boundary sentinel,
and make a bounded DEV E2E smoke (stages, flow, progress, readback) a deployment
acceptance check. See the active functional roadmap for the 13-Oct findings.

### 2026-10-14 — Candidate source cohesion and same-ID replay evidence

One source anchor is not proof of an independently assertable fact. Qualifiers,
objects and subordinate purposes must not be dispatched as autonomous Core
writes merely because Router emitted additional candidates. Prefer conservative
source grouping for Core review when semantic independence is unproven, and
verify unrelated actions, dates, Tasks, ambiguous references and physical
Markdown readback against the frozen regression corpus. Never patch an example
word, language-specific connective, person or test identifier.

Two n8n executions of one user message under the SAME delivery ID may differ
if the first failed result was not persisted. Diagnose each execution separately;
do not infer that a delivered failure was the post-write receipt of a later
success. Source-independent assertions and replay/idempotency require explicit
contracts, not accidental retries. See current Functional Roadmap checkpoint.

### 2026-10-14 — Router v6 source semantics are opt-in, not an executable authority

For any future Router revision, do not infer a new executable fact merely from
one accurately quoted anchor, a local predicate, or a model-supplied
independent_assertion label. The opt-in v6 JSON source-relation contract
expresses attributes, purposes, conditions, shared lexical context and uncertain
relationships with previous source candidates; the runtime compiler revalidates
their positions and groups uncertain same-clause material for Core review.
Existing v1-v5 prompts and DEV runtime remain unchanged until new gates pass.
No name, example-specific adjective, language connective or two-entity template
may be used as the independence oracle. Successful route grouping is NOT
evidence of successful Core semantic review. The pure decision trace contains
only source hash, offsets, tags and deterministic validation decisions and is
not yet authorized for user-facing logging without privacy/contract tests.
Complete Core review, Tasks/canonical readback, n8n/browser diagnostics,
multi-lingual provider variance and replay safety before DEV activation.
See the E1.x direction in application-extensibility-plan.md.

### 2026-10-14 — Preserve safe diagnostics on unproven source dependency

Even before an independent Core boundary reviewer starts, a valid-looking
Router v6 proposal can encode an inherited source role that has no real
predecessor evidence. Core's dependency tracer correctly refuses it. The
product boundary must preserve that refusal as a typed no-write
`NEEDS_ATTENTION` outcome with a safe failure stage/category, not an opaque
HTTP error or a guessed role. Never drop inherited source roles just to get
an executable route, nor automatically rerun a potentially written delivery.
Cross-check this path through runtime, n8n and browser contracts. The
synthetic 14-Oct DEV modifier smoke and generic deterministic sentinel are
recorded in the functional roadmap.

### 2026-10-14 — Bounded independent Core source review BEFORE any writes

Router source candidates and a compiler split are proposals, not sufficient
authority for independent execution. Opt-in v6 now supports a Core-owned
whole-message boundary reviewer BEFORE Temporal, per-group Planner, Tasks or
Writer. It reviews only multi-route requests, uses low-effort GPT-5.6, and
produces an enum accept/revise/needs_attention with one boundary index and
reason, bound to original/partition hashes. Core's existing candidate/fact
mapping still independently validates each plan before mutation. One unsafe
boundary may receive ONE Router v6 correction with bounded reason/index;
after a second rejection, missing reviewer, stale text/partition, or provider
error, fail closed with no writes. NEVER retry Router automatically after Core
may have written ANY note. v1-v5 and PROD/DEV remain unchanged until gates.
This is NOT a generic inference service behind every other AI nor a proof of
perfect semantics. Review `odyssey_core/source_boundary_review.py` and
`docs/architecture/application-extensibility-plan.md` E1.x for the contracts.
Remaining gates are reviewer telemetry into n8n/web, real Core write/readback
on disposable data, reference/pending edge cases, and request-id idempotency.

### 2026-10-13 — Auditoria exhaustiva de formas y casos pendientes

Consultar docs/architecture/hybrid-source-validator-audit-20261013.md.
La arquitectura hibrida usa evidencia fuente 1..N y nunca plantillas
espanolas de dos nombres/conversaciones. F22 completo funciona en
replay real con tres Tasks y enlaces canonicos; nuevo conteo 24/27.
F09 sigue NO ACEPTADO por duplicacion semantica de Marta aunque el
WRITE informe COMPLETED. F14/F27 conservan partes correctas y
no resuelven el pronombre ambiguo el por cercania.
Priorizar contrato Core semantico de ya representado con readback
canonicamente verificado. NO parchear nombres ni verbos de ejemplos.

### 2026-10-13 — Hybrid validator generalization (implemented, feature branch)

The previous Spanish phrase-template pilot in
odyssey_core/candidate_sequential_contacts.py is **LEGACY ONLY**. Hybrid
Core may NEVER dispatch through it: multi-fact participant coverage now
checks each independently reviewed candidate/fact using explicit source
participants, independently proven inheritance, unique canonical reference
helpers and the ordinary Writer. No fixed name, two-contact phrase, or
three-unit Action topology may be introduced as a hybrid rule.

The independent graph reviewer now permits a slightly longer ORIGINAL
source quote around a verified Router anchor (e.g. one preposition), but
NEVER a fabricated quote, and all other Core prewrite checks remain.
F01 now completes three dated group events in two Day Notes with real
model/reviewer and physical readback.

F02 mixed exact/approximate Temporal interpretation is supported only
when Temporal's UNSPECIFIED wording exactly matches an original Router
time_approx span. It stays a literal approximate phrase, never a clock;
exact independent days/clocks still pass with per-fact coverage. Same-Day
redundant date-reference parts are removed before the normal compiler
and Writer, never guessed or emitted as self-links.

Current **strict isolated-genuine-model corpus checkpoint: 23/27**:
F01 F02 F03 F04 F05 F06 F07 F08 F10 F11 F12 F13 F15 F16 F17
F18 F19 F20 F21 F23 F24 F25 F26. Remaining F09 (redundant/canonical
semantic delta), F14/F27 (truly ambiguous subject pronouns: safe partial),
and F22 (Task body omits known person link). F02 results captured in
benchmarks/application_router/hybrid_approximate_live_v2 and
hybrid_core_review_v4, final F01 in hybrid_core_review_v3.
**Estimated cumulative experiment spend USD 0.64794381 of 1.00 authorized,
not billing reconciliation.** No activation in DEV/PROD and no user-vault
writes. Frozen original captures remain immutable. This checkpoint
supersedes older counts but not their historical test records.

One limitation remains separate: the read-only experimental known-Note
hint lookup currently refuses to scan vaults larger than 5000 Notes and
only returns 16 prompt hints. This is a performance guard, **not** a
permitted semantic limit on Odyssey's Note or fact count. Replace with an
indexed, bounded-retrieval implementation before broad DEV adoption;
never silently treat a too-large vault as evidence that a named Note
does not exist. Similarly audit historical narrow validators instead
of copying their grammar templates.
