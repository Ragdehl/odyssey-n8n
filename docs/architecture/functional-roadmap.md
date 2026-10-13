# Functional Roadmap

This is Odyssey's canonical source for **functional implementation status, intended order, and the next adoption gate**. Detailed contracts and historical evidence live in linked phase documents, ADRs, and benchmarks rather than being copied here.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **LATER / CONDITIONAL**

## ➡️ Seguimiento activo — DEV híbrido y extensibilidad (13-10-2026)

**Fuente canónica para la etapa activa y el siguiente paso; esta sección prevalece sobre checkpoints históricos fechados más abajo.** El objetivo, el diseño propuesto y los criterios de aceptación están en [Plan de continuidad: arquitectura híbrida y aplicaciones reutilizables](application-extensibility-plan.md). Continuar siempre desde este bloque y verificar el repo/DEV en lugar de suponer estados.

- **Rama/worktree de partida:** `/home/ragdehl/projects/odyssey-fact-candidates-v1`, rama `feat/router-fact-candidate-contract-v1`, commit base auditado `13d713f` (puede cambiar: comprobar con Git).
- **Realidad verificada:** híbrido experimental en rama, **no desplegado en DEV/PROD**. Última evidencia registrada: 25/27 completamente terminados y F14/F27 correctamente pendientes por pronombre ambiguo; 3039 passed, 80 skipped, 10 fallos históricos. No hay validación del usuario en DEV de este híbrido.
- **Decisión del usuario:** probar primero la aplicación en DEV y **después** generalizar contrato de datos, puerta común de mutaciones, limpieza de excepciones y Events; Clean Architecture de forma incremental, nunca una reescritura previa al primer ciclo DEV.

| Paso | Estado | Resultado necesario / nota de continuidad |
| --- | --- | --- |
| E0 — Auditoría de arquitectura (13-10) | ✅ Revisada | Diferencias entre materialización de Task, Work Sessions y Core; `TaskCorePlanner` transforma planes; `TaskScopedEvidence` especial; guard F14/F27 de frase fija es piloto. Auditoría de lectura, no prueba DEV. |
| **E1 — Activación segura y pruebas del usuario en DEV** | **✅ DESPLEGADO EN DEV, PRUEBAS MANUALES HABILITADAS** | Existe un seam híbrido explícito, desactivado por defecto y exclusivo de `ODYSSEY_DEPLOYMENT_ENV=DEV`; requiere actor y conversación autenticados y conserva v0 cuando está apagado. n8n entrega `conversation_id=main` y runtime/n8n/web están sincronizados en DEV al commit `d121344`; los smoke de lectura, escritura Day y Task con datos sintéticos devolvieron resultados correctos, con notas e historial Git verificados. La ruta híbrida ahora solicita al Planner Core una disposición semántica de sólo lectura antes de ejecutar: sólo un `RequestPlan` validado formado enteramente por `RetrieveAction` entra al Core normal con ese mismo plan fijado; escrituras/delegaciones y resultados no demostrados quedan en el ejecutor híbrido; una petición mixta devuelve aclaración y no pierde ninguna intención. Pending v2 y Tasks mantienen sus límites anteriores. Próximo gate: pruebas manuales de UX y casos semánticos del usuario; las selecciones pendientes v2 aún no materializan el hecho ambiguo, y los mensajes mixtos read+write se rechazan de forma segura hasta contar con un split verificable. |
| E2 — Contrato común de contexto | ⬜ Pendiente | Inventario de carriers y diseño mínimo tipo/versión, tests con Apps existentes y nueva App ficticia. |
| E3 — Puerta común de mutaciones | ⬜ Pendiente | Garantías transversales para chat, UI Task y Work Sessions; propiedad de planes genéricos en Core. |
| E4 — Excepciones y legado | ⬜ Pendiente | Sustituir pilotos de frase fija y validar retirar legacy sin romper centinelas. |
| E5 — Events como prueba de extensibilidad | ⬜ Pendiente | App Events aprovecha Core/Temporal/Calendar sin duplicar mecanismos. |
| E6 — Clean Architecture incremental | 💡 Dirección continua aprobada | Refactorizaciones acotadas al tocar módulos; checkpoint de mantenibilidad después de Tasks/Events. |

**Próxima acción concreta:** usuario habilitado para probar el chat de **Odyssey DEV** con escenarios ficticios de lectura, escritura Day, Tasks, múltiples fechas y referencias ambiguas. Recoger mensaje exacto, resultado UI, IDs/gráfico/notas y analizar cada fallo preservando regresión antes de corregir. E1 NO equivale a aprobación de PROD. `Pending v2` permite visualizar/elegir opciones, pero la continuación ambigua no escribe (`CONTINUATION_REVIEW_REQUIRED`); lecturas+escrituras combinadas permanecen bloqueadas de forma segura. Una vez revisados los resultados reales, continuar E2 (contrato de contexto) y puerta común de mutaciones conforme al plan, sin refactor global.

**Bitácora de hitos (añadir solo cambios reales, con evidencia y estado operativo):**

| Fecha | Hito / evidencia | Git / runtime | Siguiente paso |
| --- | --- | --- | --- |
| 2026-10-13 | Auditoría solo lectura; se acordó plan de reutilización y seguimiento persistente. | Rama experimental, base `13d713f`; **sin modificaciones funcionales ni deploy**. | Preparar E1 y revisar la integración DEV, no iniciar refactor masivo. |
| 2026-10-13 | E1: se añadió en `odyssey_runtime/composition.py` un despacho híbrido acotado que sólo se construye con `ODYSSEY_HYBRID_DEV_ENABLED=1` y `ODYSSEY_DEPLOYMENT_ENV=DEV`; fuera de esa combinación v0 es idéntico. Exige actor + conversación, enruta por el compilador híbrido revisado y guarda pending v2 bajo el root del actor. F14/F27 siguen sin continuación conectada al chat: no se exponen opciones seleccionables ni se ejecuta el guard piloto de frase fija. Los candidatos Task se envían a la capacidad Tasks y fallan cerrados mientras no exista el ejecutor scoped; no se permite fallback genérico a una nota Day. El historial Git canónico se transmite al ejecutor por ruta. Nuevos tests provider-free: `tests/runtime/test_hybrid_dev_route_gate.py`. | Worktree `feat/router-fact-candidate-contract-v1` en `6dc5ec0` al empezar; checkpoint E1 registrado en commit posterior (consultar `git log`). `/home/ragdehl/projects/odyssey-dev` limpio en `6ae8695`; runtime/n8n observados detenidos. PR #152 borrador comprobada mediante GitHub antes de la sesión aislada de Codex. Gate independiente con venv local: 131 tests focalizados correctos. Suite completa final: 3046 passed, 80 skipped y los mismos 10 fallos históricos (ninguna regresión nueva); además, tras conectar historial Git pasaron 52 tests focalizados de ruta, Tasks y pending. Ruff import/format correctos; sin llamadas al proveedor. DEV/PROD sin operaciones ni cambios. | Completar ejecutor Tasks scoped y presentación/continuación v2 genérica; comprobar historial Git e integración real E2E autenticada en entorno aislado, confirmar que `conversation_id=main` llega correctamente desde n8n, revisar versión/variables efectivas DEV y pedir autorización humana antes de desplegar o reiniciar nada. |
| 2026-10-13 | E1 bounded increment: the DEV-only hybrid composition now passes `TaskScopedEvidence` to a real `execute_scoped` Tasks adapter. The adapter runs `interpret_scoped`, fresh exact local Temporal when the selected Task semantics require it, `compose_scoped_task_domain_interpretation`, `TaskCorePlanner`, `TaskLifecycleGuard`, and the existing authenticated Core persistence/history boundary. Unsupported scoped operations, invalid scope/domain, or unresolved local Temporal return `NEEDS_ATTENTION`; Task candidates have no Day/Core fallback. Existing frozen-provider/disposable-vault Task replays cover three pending canonical Task Notes, inherited date/modality evidence, zero Day facts, and invalid evidence; no provider was called in this increment. | Uncommitted worktree on `feat/router-fact-candidate-contract-v1`, base observed `b56b86a`; focused command: `/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m pytest tests/runtime/test_hybrid_task_app_delegation.py tests/runtime/test_hybrid_tasks_real_provider_replay.py tests/runtime/test_hybrid_tasks_named_source_live_replay_20261013.py tests/apps/tasks/test_interpretation.py -q` → 32 passed. `ruff check odyssey_runtime/composition.py` and `git diff --check` passed. DEV/PROD, n8n, services, personal vaults, Git commit/push, and paid models untouched. | Add/verify the authenticated composition-level DEV E2E gate with the effective deployment variables, confirm real n8n conversation delivery, and implement only a general pending-v2 UI continuation after its separate validation; obtain human authorization before any deploy/restart. |

| 2026-10-13 | Revisión independiente de la conexión Tasks: se corrigió un fallo real en la interfaz del adaptador (`task_route_executor` necesitaba exponer `execute_scoped`, no ser solo una función). Se añadió `_ScopedTaskRouteExecutor` tipado y se probó el recorrido del dispatcher con el adaptador efectivo, conservando Core, preflight Task y Git. E1 sigue sin incorporar la UI/continuación general pending v2. | Branch experimental, base `b56b86a`; Ruff correcto, 39 pruebas focalizadas correctas, suite completa **3046 passed, 80 skipped, 10 fallos históricos idénticos**. Ningún deploy DEV/PROD ni cambio de vault; checkpoint documentado en Git. | A continuación, completar el contrato de selección y continuación pending v2 con pruebas de aislamiento por conversación, frescura, idempotencia y readback, y después preparar gate autenticado y despliegue DEV con autorización. |
| 2026-10-13 | E1 pending v2: `RuntimeComposition.execute_product` proyecta sólo el registro v2 del actor/conversación autenticados al JSON de aclaración que ya consume `odyssey_web`. La entrega es idempotente por `LocalDeliveryResultStore`; una respuesta se procesa por v2 antes de v1, conserva cancelación/estado, rechaza opciones/facts obsoletos y nunca deriva a v0 mientras el seam híbrido está activo. La elección revalida identidad, hechos ya escritos y reloj original, pero devuelve `CONTINUATION_REVIEW_REQUIRED` sin crear `RequestPlan`, sin invocar el guard F14/F27 y sin escribir Markdown. Más de cuatro opciones sigue siendo fuente pendiente sin lista mostrada. | Worktree `feat/router-fact-candidate-contract-v1`, cambios sin commit; nuevo test provider-free `tests/runtime/test_hybrid_product_pending_v2.py`. Ruff y `git diff --check` correctos. Focalizados: **66 passed**. Suite determinista completa por particiones (incluyendo HTTP loopback fuera del sandbox): **3050 passed, 80 skipped, 10 fallos históricos**; sin regresiones nuevas. No hubo llamadas pagadas, despliegue/reinicio, cambios de n8n, PROD ni vault real. | Revisión humana; comprobar runtime/n8n efectivo y variables DEV, ejecutar gate autenticado con datos DEV desechables y después desplegar exclusivamente DEV si pasa. La continuación automática F14/F27 sigue bloqueada hasta validador semántico general revisado. |

| 2026-10-13 | E1 revisión pre-DEV: se corrigió la correlación inmediata de respuesta de clarificación con el ID externo y el ID de ruta hijo aun cuando la UI ya guardó un turno de asistente. Test de datos sintéticos con origen de ruta real; elección de persona persistida, nunca ejecuta escritura ambigua. La pasarela n8n permite opciones v2 acotadas y hace explícito que la elección no guardó el hecho. Sólo `deploy/odyssey-dev-runtime.service` activa el híbrido, con `ODYSSEY_DEPLOYMENT_ENV=DEV`. | Baseline final **3052 pytest passed, 80 skipped, 10 fallos históricos idénticos**, 52 subtests. **139 Node tests passed**, Ruff, formato y `git diff --check` correctos. Datos personales/PROD sin cambios. DEV aún no desplegado a la hora de registrar esta entrada. | Desplegar commit probado en DEV, verificar commit efectivo + n8n + interfaz, prueba real de entrega; después pruebas manuales del usuario. Generador de continuación semántica genérica fuera del primer deploy: hasta entonces una elección v2 sólo se registra y devuelve `CONTINUATION_REVIEW_REQUIRED`. |

| 2026-10-13 | Primer deploy DEV autorizado completó (`odyssey-dev deploy`, salida 0); status: `dev_state=active`, runtime y n8n `healthy`, `workflow_source_provenance=MATCH`, web `MATCH`, checkout limpio; commit de runtime/n8n/web `5586b15`. El smoke de mensaje sintético sólo de lectura por n8n devolvió error genérico; ejecución de n8n reveló respuesta HTTP 500 de runtime. El Router v5 aislado devuelve propuesta válida con el mismo tipo de frase. Se añade traza técnica acotada SOLO en DEV híbrido (tipo/función/línea de excepción, sin mensajes ni payload) para localizar problema; no considerar aprobado el gate funcional. | PROD no se tocó: vault commit `0a87fed` y limpio. Diagnóstico DEV: 56 pruebas Python de servidor y privacidad correctas. Commit de trazas aislado del deploy inicial. | Redeploy de diagnóstico; repetir lectura sintética y corregir la causa. Mantener el despliegue funcional como NO VALIDADO hasta smoke correcto. |

| 2026-10-13 | E1 diagnóstico de entrega DEV: desplegado `3bff1f0` con `runtime_health=healthy`, `n8n_health=healthy`, workflows/web/procedencia `MATCH`, checkout limpio; se resolvieron los bloqueos de despliegue evitando dos importadores n8n concurrentes y ejecución del inventario sin stdin. Smoke de lectura genérica → `HTTP 200`, aclaración segura; smoke de identidad sintética explícita → error de aplicación (respuesta HTTP 200 del proxy). La traza DEV acotada identificó `ConversationError` en `LocalConversationStore.append_turn`: un chunk histórico llegó al límite de 256 KiB antes del límite por turnos. Se implementó rotación por bytes del JSON, conservando chunks existentes, y test sobre chunk histórico casi lleno. | Focalizado: **20 passed**; suite integral en precommit **3054 passed, 80 skipped, los mismos 10 fallos históricos**. Cambio de Core aún pendiente de redeploy y smoke funcional en el momento de documentar; PROD sin cambios. | Publicar y desplegar solo la corrección de rotación en DEV, repetir la lectura canónica con nombre sintético y verificar el resultado de Core antes de habilitar pruebas manuales. |

| 2026-10-13 | E1 segundo deploy DEV completado y sincronizado a `27822b6`: `runtime_health=healthy`, `n8n_health=healthy`, workflow/web/public route `MATCH`. Se solucionó el fallo genérico de rotación de chunks del historial por bytes (256 KiB), con 20 tests focalizados y suite precommit 3054 passed/80 skipped/10 fallos históricos. Smoke n8n con «¿Dónde trabaja Odyssey DEV Synthetic User?» y «¿Dónde trabajo?» → `HTTP 200` con `needs_attention` y opciones vacías, ya sin el anterior `ConversationError`. **Nuevo bloqueador semántico:** `RuntimeComposition.execute` entrega toda solicitud al Router híbrido de candidatos cuando está habilitado, incluidas las lecturas, sin conservar el recorrido de consultas de Core. No hubo escritura ni validación funcional positiva de retrieval. | DEV commit `27822b6`, checkout limpio, producción intacta, estado funcional **NO APTO AÚN para pruebas del usuario**. Este checkpoint documental puede quedar en commit posterior sin redeploy. | Implementar routing seguro de solicitudes de lectura y mixtas sin bypass de validadores de escritura; pruebas específicas y smoke E2E con respuesta correcta antes de invitar al usuario. |

| 2026-10-13 | E1 read-routing local: se introdujo en Core `RequestDisposition`, derivada exclusivamente de los tipos validados de `RequestPlan`. El seam DEV planifica primero el mensaje fuente exacto; sólo `RetrieveAction` puro se ejecuta mediante el mismo plan fijado y la frontera Core habitual. Write/delegate, aclaración/error y disposición no demostrada nunca llaman Core genérico; siguen hacia candidatos híbridos. Una petición mixta devuelve `HYBRID_MIXED_REQUEST_REQUIRES_SEPARATE_REQUESTS`, sin ejecutar ni omitir su lectura/escritura. Tests provider-free cubren lectura con fuente exacta, escritura, mixto, disposición no resuelta y auth/conversación; los contratos Core cubren read/write/delegate/mixed. | Worktree local sobre `8252c5e`, aún sin commit/push/deploy; pruebas focalizadas de ruta/router/Tasks/pending/Core: **83 passed**; Core completo: **1102 passed, 39 skipped**; Apps: **217 passed**. Ruff, formato y `git diff --check` correctos. La corrida completa encontró los 9 fallos históricos de benchmarks de coste/hash y el runtime normal fue bloqueado por sockets loopback del sandbox; la repetición con permiso local no devolvió un resumen final antes del límite del runner. Ninguna llamada de proveedor, deploy, n8n, vault DEV/PROD o dato personal fue realizada. | Revisar diff/secret scan, commit y push; desplegar sólo DEV y correr smoke n8n autenticado con la nota sintética. Si no devuelve una respuesta segura que incluya `Synthetic Systems`, diagnosticar/corregir. |

| 2026-10-13 | **E1 gate DEV superado para pruebas manuales:** `d121344` desplegado con `dev_state=active`, `runtime_health=healthy`, `n8n_health=healthy`, checkout limpio, workflows/web/public routes `MATCH`. Smoke lectura n8n «¿Dónde trabajo?» → HTTP 200 `completed`, respuesta «Trabajas en Synthetic Systems», nota `odyssey-dev-synthetic-person` verificada, sin mutación. Smoke escritura «Hoy compré una libreta turquesa para la prueba técnica E1» → HTTP 200 `completed`, hecho visible en `calendar/days/2026-10-13.md`, commit Git `85b4ee6`. Smoke Tasks «Tengo que preparar una demostración técnica de Odyssey E1 mañana» → HTTP 200 `completed`, nota física `type=task`, `status=pending`, `target_date=2026-10-14` y escritura Git correcta. Suite completa ejecutada fuera del sandbox: **3060 passed, 80 skipped, mismos 10 fallos históricos**; 857 pruebas de runtime correctas. | PR/feature commit `d121344`, DEV idéntico a `d121344`; PROD fuera de alcance. Sólo se usaron datos ficticios en DEV; el historial existente no se eliminó. | El usuario puede probar el chat de Odyssey DEV; siguiente trabajo corregir problemas reales detectados y continuar el roadmap. Restricciones conocidas: aclaración v2 no completa por sí sola la escritura ambigua, y mensajes de lectura+escritura en la misma entrada piden separación. |

| 2026-10-13 | E1 corrección de regresiones reales DEV preparada: `candidate_context_bytes` entra en las listas explícitas de telemetría n8n/web; campos de tamaño desconocidos o inválidos se descartan individualmente sin borrar stages, flujo ni resultado canónico. El dispatcher híbrido publica límites reales Router/Temporal/Planner/Tasks a través del canal de progreso autenticado existente; Core conserva sus propios hitos de acción. Una excepción de ruta ahora genera el stage real `application.execution` con clase de excepción solamente y razón pública controlada, sin mensaje/fuente. Tests ejecutan el código real del workflow con 8 stages, validan el navegador, la ruta Core/Task, polling del producto y la evidencia de fallo. | Worktree `feat/router-fact-candidate-contract-v1` sobre `1c81ba5`, pendiente de commit/deploy al registrar este hito. Ruff/formato/diff/secret scan correctos. Node: **8 passed**. Python completo fuera del sandbox: **3061 passed, 80 skipped, mismos 10 fallos históricos** (gates dated/model-hash); no llamadas proveedor, migraciones ni cambios PROD. | Revisar commit/push, desplegar una sola vez exclusivamente DEV, comprobar health/provenance y hacer replay sintético acotado de dependencia ambigua. Gate preventivo: ningún campo métrico nuevo puede borrar stages validados; hitos híbridos se observan en el camino de producto; todo fallo de ruta tiene stage y categoría segura. |

**Protocolo de cierre por paso:** dejar aquí estado, hechos observados, commit/PR, pruebas ejecutadas (o no), estado DEV/PROD, bloqueador y próximo paso. Los contratos de diseño se detallan en el plan enlazado. Un chat nuevo debe poder empezar aquí sin recuperar conversación anterior.

## 💡 Futuro: Clean Architecture incremental

Dirección aprobada el 13-10-2026: aplicar mejoras de separación
dominio/puertos/adaptadores cuando un cambio funcional futuro toque el módulo.
Sin reescritura transversal ahora ni bloqueo del despliegue DEV.
Ver clean-architecture-incremental-direction.md y AGENTS.md.

## Completed foundation

| Phase | Result |
| --- | --- |
| 9 | Deterministic exact entity resolution by canonical name/alias. |
| 10 | Local semantic entity candidate retrieval; similarity is evidence only. |
| 11 | Contextual/hybrid existing-entity resolution with deterministic Core validation. |
| 12 | Explicit deterministic entity persistence primitives. |
| 13 | General knowledge context retrieval (`get_context`) over rebuildable local indexes. |
| 14 | Validated top-level `RequestPlan` interpretation. |
| 15–15.3 | Semantic write planning, schema-aware selection/mutations, explicit links/tags, generic delegation preservation. |
| 16–16.7C | Safe create/update targeting, bounded UPDATE writing, deterministic CREATE, reference binding, bulk UPDATE, soft DELETE, and type migration. |
| 17A–17C | Executable Core application flow, durable pending work, and request-correlated local Git history. |
| 17D | Append-first atomic facts with request-derived fact locators and targeted correction/removal. |
| 17E | Pre-E2E schema/retrieval validation; unevidenced Combined Top-500 adoption withdrawn after identity-aware correction. |
| 18 | First real n8n -> runtime -> Core WRITE/READ end-to-end path. |
| 19 | Retry/failure hardening plus bounded timing/provider-usage evidence. |

Canonical/historical detail remains in the phase documents under this directory and in [Architecture Decisions](../decisions/README.md). The [Architecture Overview](overview.md) describes the current composed system without replaying this history.

## ➡️ Next: Router hybrid interpretation groups — accepted target (2026-10-12)

**Human-approved direction, NOT an active implementation.** See the
[authoritative hybrid contract](router-hybrid-interpretation-contract.md) and
[ADR 0010](../decisions/0010-router-hybrid-interpretation-groups.md).
This explicitly supersedes the 2026-10-11 mandate that every atomic
candidate be interpreted in a separate Core call. Router still extracts
source-grounded **atomic candidates**; a compiler groups **semantically
interdependent** candidates into exact-source interpretation groups.
Temporal interprets relevant group dates/times; ordinary Core GPT-5.6
plans zero or more **individually owned facts** from each group; a separate
Core reviewer and the canonical Writer must validate each fact and
account for all source candidates, including pending ones. Independent
topics remain separate groups. Cross-group verified reference, temporal
and event handoffs remain available as a safe fallback. A whole message
containing unrelated topics must NOT become one new Core request.

**Historical first pilot (preserved, not the current status):** in the
initial five-case real-model grouping experiment, F04/F16 completed,
F03/F23 were Core pending and F21 was Temporal blocked (**2/5**).
Those model outputs are preserved unchanged in `hybrid_grouped_v1/`.
The later, opt-in feature-branch repairs have fresh real-model and Writer
readback evidence for all three formerly pending **specific positive
shapes** (F03/F21/F23), frozen under `hybrid_grouped_v2/`. The total five
specific examples now have passing real evidence, not a general 27-case
language or production-readiness claim. Historical route-local benchmarks
remain evidence, not competing architecture rules.

**Implementation checkpoint (branch only, opt-in):** The approved
documentation/ADR audit is complete. A bounded
`odyssey_runtime/hybrid_group_compiler.py` now groups real source
candidates without merging facts; the existing scoped executor accepts it
**only via explicit `bundle_compiler` injection** and defaults to the
unchanged atomic compiler. The 26 compilable source cases go from
**53 atomic routes to 37 conservative interpretation groups**. F27
continues to fail closed. The initial five-case replay retained F04/F16
success and the earlier F03/F21/F23 failures as separate evidence.
**Subsequent repairs** now separately validate F03 literal `mis hijos`
participants, F21 two Temporal-verified weekday/clock destinations, and
F23 two positive reference-free properties of the Odyssey project, with
freshly captured GPT-6/5.6 calls, independent Core review and per-fact
Markdown readback in copied Notes. F06's independent second group can
persist even if its first Core plan declines.
See the [hybrid target and implementation checkpoint](router-hybrid-interpretation-contract.md).
This is **experimental code, not deployed behavior**, and is NOT an
authorization to declare all cases semantically solved.

**Sensitive-scope testing checkpoint (2026-10-12):** Fresh real
GPT-6/5.6 grouped tests now cover F17, F19 and F20, and separate-route
tests cover F18 and F22. F17 remains pending on negation, F19 fails
closed rather than writing a cancelled plan, F20 stays pending for its
conditional branches, and F18 leaves both mixed-polarity routes pending.
The original F22 execution was **partial**, writing only its final
preparation intent to a Day Note rather than to a Task; new opt-in
hybrid coverage explicitly blocks this **false Task completion**. F25
likewise cannot silently promote a repair need to a Task. Authentic
outputs and the historical F22 partial outcome are frozen in
`benchmarks/application_router/hybrid_sensitive_v1/`. Ambiguous F14
remains unwritten and F27 fails provenance validation. These are safe
negative/partial results, **not** a claim that negations, corrections,
conditionals or the Tasks lifecycle are fully supported.

**Subsequent code/test checkpoint (2026-10-12; opt-in branch only):**
F19 now permits an independently reviewed, source-grounded FUTURE
INTENTION for the final replacement, with exact Temporal clock/date.
The discarded plan is marked `superseded_by_correction` only if a
validated replacement fact is reviewed and written; the resulting
request **COMPLETED** in physical synthetic Markdown replay with an
authentic saved GPT-6/5.6 reply. Three real-provider historical attempt
outputs are frozen in `hybrid_correction_v1/F19.json` and reproducible
with no new provider calls. This does not enable F17 negations or F20
conditional claims. The pure task groups in F22 can now be dispatched
**only with explicit enable_tasks=True** to the existing registered Tasks
capability, which owns its independent TaskCorePlanner/lifecycle and
canonical task schema. A deterministic end-to-end test creates a genuine
`task` Note with `status=pending` and a target date; a missing Tasks
executor fails closed. No real-model hybrid Tasks integration was claimed.
Mixed F25 property+repair descriptions are not automatically Task creates.
The source compiler defaults to the previous route contract.

**Latest validated checkpoint (2026-10-12, opt-in branch only):**
F17 and F20 are now **completed** in *new* fresh GPT-6/5.6 tests:
a joint negative or mutually exclusive conditional is persisted as
**one source-identical literal sentence** on the Temporal-certified
Day Note, not as two real occurrences. An independent N:1 Core graph
reviewer must account for both source candidates; the special
prewrite gate rejects altered polarity, altered condition, added
identities and wrong Day targets. New actual model captures in
`hybrid_sensitive_literal_v1/` are replayable and do **not**
overwrite the initial fail-closed F17/F20 receipts.

For F22, the **third** task `mañana preparar la factura` now has a
separate fresh-model GPT-6 Tasks + GPT-6 Temporal + GPT-5.6 Core
successful CREATE: one `task` Note with `pending` status and proven
target date, with physical synthetic Markdown. Saved output under
`hybrid_tasks_v1/F22-last.json`. The hybrid dispatcher replay
reuses those real outputs and leaves F22's first two task fragments
pending; the whole original F22 case has **NOT** been completed.
No change to app deployment, task schema or human Notes.
Estimated cumulative model experiment spend: USD 0.3356791 / 0.50.

**Standalone negative-literal continuation (2026-10-12, opt-in branch
only):** the same exact-source gate now handles a one-candidate negative and
variable bounded negative candidate counts, including a source-owned
`participants` role instead of `object`. Every candidate needs its own exact
polarity, predicate, and one participant/object scope; the only authorized
write remains the complete routed source as one literal Day fact on an exact
Temporal-proven Day, without references or event semantics. Provider-free
tests cover 1/3/5/9 candidates and missing/swapped/extra scope, target, date,
polarity, mixed-kind, partial-source, and canonical-reference rejection. No
Router prompt, model, schema, DEV/PROD route, workflow, or provider evidence
changed. The immutable historical real-model F18 replay remains
non-completed, but a subsequent source-provenance audit corrected the earlier
diagnosis: its original Router proposal ALREADY cites `Ayer` as a DATE role
for the independent affirmative candidate. The hybrid compiler carries that
out-of-fragment source role and ScopedTemporalHandoff verifies its exact
date-only transfer; no polarity or identity is inherited. A provider-free
end-to-end replay of that ORIGINAL Router proposal with independently scripted
Core plans and coverage now writes a safe literal negative Day fact AND a
distinct affirmative Day fact linked to the seeded canonical Luis, with
physical Markdown readback. Deleting the affirmative DATE source role removes
the date proof. This validates structural feasibility, NOT the actual GPT-5.6
Planner/reviewer quality; F18 remains outside the fully live-accepted count
until fresh model-based semantic review succeeds.

**Scoped continuation (opt-in branch only):** corrected future plans now
accept a source-proven linear replacement chain rather than assuming exactly
two candidates. The first candidate supplies date/predicate/polarity; each
successor must exactly replace its immediate predecessor's object and carry
its own time plus immediate predicate/date inheritance. Only the final
candidate may map to the sole fact; all predecessors require complete
independent `unsupported_scope` review before their non-write status becomes
`superseded_by_correction`. Deterministic 2/3/5/9-chain coverage and a
three-step synthetic Markdown readback supplement the unchanged genuine F19
replay. This is not general correction-language support, a fresh model gate,
or authorization to activate DEV/PROD.

**Tasks cross-route evidence continuation (2026-10-12; opt-in branch only):**
The F22 original GPT-6 Router proposal already carries exact-source
`date=Hoy` and `modality=tengo que` provenance on its independent second
Task route. A closed Tasks-owned `TaskScopedEvidence` and opt-in
`execute_scoped` executor hook now carry only hash-checked lexical modality
and independently verified predecessor Temporal references; neither is
permission to select `CREATE`, pick a Task identity, or write. Tasks retains
its own interpreter, one-task-per-operation `TaskCorePlanner`, lifecycle
guard, and canonical Markdown writer. A deterministic full-request replay
using the original Router proposal and independently scripted Task/Core
semantic decisions writes **three separate actual pending Task Notes**, with
fixture dates 2026-10-04 / 2026-10-04 / 2026-10-05 and zero Day fallback facts.
The first route's actual Temporal proof may be reused even when no first
Task mutation succeeds. Legacy four-argument Tasks executors retain their
local-route behavior; when they cannot receive a necessary verified inherited
date, the independent route stays `NEEDS_ATTENTION` instead of guessing it.
Frozen third-route real GPT-6/GPT-5.6 reply/readback remains unchanged.
**F22 stays PARTIAL**, because no real model-based Tasks interpretation and
Core planner/reviewer acceptance exists for its first two intents. The
ordinary `TaskInterpretation` provider schema and frozen responses remain
unchanged. An additional opt-in `interpret_scoped` contract now permits a
model to choose only `{reference_index, role}` from a bounded verified
Temporal list; it cannot send a date, copy external wording as a local
mention, select Work Session semantics, choose identity, or mutate. The
sidecar is parsed fail-closed for exact fields, bounds, duplicates, local
set/clear conflicts and exact date/date-time compatibility. Its mapper emits
current-fragment property evidence plus exactly the selected inherited
references, so Core retains planning and lifecycle authority. Deterministic
strict-provider tests capture the on-wire prompt/schema and a full synthetic
three-Task Markdown replay now exercises the second fragment through that
selection. This is **not fresh provider evidence** and does not alter the
27-case score. A focused live gate, adversarial evidence and Core review are
still required before any activation. DEV/PROD, n8n, personal vaults, and
model settings remain untouched.

**Fresh F22 model execution (2026-10-12; no deployment):**
An earlier claim that OpenAI API access was blocked was WRONG. The ordinary
shell lacks `OPENAI_API_KEY` by design, but the already approved
`/home/ragdehl/.config/odyssey/secrets.env` loaded securely through
ephemeral `systemd --user EnvironmentFile`; authenticated GET /v1/models
returned HTTP 200. The first GPT-6 Tasks live trial omitted F22's second
inherited date; a GENERAL scoped prompt revision then selected the
correct verified earlier `TARGET_DATE` in a new genuine model response.
The ensuing eight-call GPT-6 Tasks/Temporal + GPT-5.6 Core isolated
full-ORIGINAL-F22 replay produced three `COMPLETED` route statuses and
three actual pending Task Markdown Notes with target dates
2026-10-04 / 2026-10-04 / 2026-10-05. All eight genuine provider outputs
are preserved in `benchmarks/application_router/hybrid_tasks_v1/F22-full-v2.json`
and the trial's detailed receipts remain in the separately protected
experimental receipts folder. One generated creation-day `calendar_day`
Note is empty (frontmatter-only), not an invented Day event.
**F22 STILL PARTIAL:** the first Task correctly linked [[Ana]], but
the second Task left a known Luis as literal wording, with NO [[Luis]]
canonical reference. Do not equate technically `COMPLETED` writes with
full independent semantic coverage. The Core person-link proof gap remains.
Estimated cumulative experiments USD 0.3558277 / approved USD 0.50;
no DEV/PROD, real Note, credential, n8n, or model-setting changes.

**Complete remaining-corpus genuine model batch (2026-10-12):**
The already documented approved `systemd --user` EnvironmentFile and live
budget were used to run **all 18 formerly unaccepted non-F22 original
cases**, each with fresh GPT-6 Router, conditional GPT-6 Temporal, GPT-5.6
Core Planner and independent Core graph reviewer, the CURRENT opt-in
`compile_hybrid_candidate_bundle`, an isolated copy of canonical synthetic
Markdown, and actual physical readback. Every provider response, source
digest, route status and changed Markdown preview was saved under
`benchmarks/application_router/hybrid_live_matrix_20261012/`.
No new DEV/PROD routes, human Notes or model migration. Complete 18/18:
3 technically COMPLETED, 4 PARTIAL, 9 NEEDS_ATTENTION, 2 FAILED. Cost
estimated USD 0.0843914 this batch; cumulative USD 0.4402191 / 0.50.

| Status | Original cases | Important readback outcome |
|---|---|---|
| COMPLETED | F08 F09 F11 | F08 wrote both appointments but doubled the date link in Marta's fact; F09 wrote `Viven en Lyon.` separately on Marta and Luis; **F11 precisely wrote `Hoy compré pan y leche.`** to one Day |
| PARTIAL | F01 F02 F13 F26 | Independent writes persisted; F13 persisted only `Compré pan.`, F26 first report-arrival fact only; remaining claims not all accepted |
| NEEDS_ATTENTION | F05 F06 F07 F14 F15 F18 F24 F25 F27 | Declined rather than inventing unsupported identity/provenance/facts; F14/F27 did not save their safe independent parts |
| FAILED | F10 F12 | Core Planner emitted ESCALATE; no writes |

**Independent acceptance accounting:** F11's entire original request has one
correct Day fact with genuine-model replay, checked with a permanent
zero-provider-call vertical regression test. Promote **F11** into the
fully accepted original-message count: **9 / 27 genuinely accepted** (the
eight already accepted F03 F04 F16 F17 F19 F20 F21 F23, plus F11).
The other technically completed F08 and F09 require a semantic/Markdown
review, NOT an automatic acceptance increase. **18 original messages
still require complete acceptance** (including the separately partially
accepted F22).

**Participant/source-coverage follow-up (2026-10-12, deterministic replay
only):** The opt-in Core participant gate no longer assumes one collective
phrase, one Calendar-Day unit, or a 1:1 candidate/fact mapping. For each
affirmative grouped event it now proves the exact direct or immediate
source-inherited participant spans, that candidate's own predicate/object or
location evidence, and each fact-local reference helper before ordinary Core
canonical binding and Markdown readback. This deliberately does not resolve a
collective description into people, create identities, or make Router evidence
canonical. Frozen genuine F07 Router/Temporal/Planner/reviewer outputs now
replay with two isolated-Day facts at 15:00/17:00 and independently bound Bea
and Luis links. Deterministic 1/3/5/9 candidate/fact shapes plus swapped actor,
lost event object, fabricated helper, and ambiguous-pronoun refusals protect
the contract. This is replay evidence, not a fresh model-quality acceptance or
an increase to the 9/27 count. F01 remains partial because its cinema candidate
has no source-proven participant inheritance; F27 remains pending because its
ambiguous future pronoun and existing provenance failure are outside this gate.

**Deferred reviewer evidence proposal:** The independent graph reviewer sees
only the selected source, proposed targets and typed predecessor evidence; it
does not receive a canonical-note list. Existing fixture names for F05/F06/F13/
F14 therefore cannot be used as identity proof. A future bounded Core-owned
canonical-evidence handoff would need a separate contract restricting it to
source-matched, current repository selections and preserving ordinary Core
binding as the sole write authority. It was not implemented in this follow-up.

**Core semantic-source reviewer and exact Temporal text follow-up (2026-10-12,
fresh model evidence):** Another old assumption has been rejected:
`ambiguous_identity` from the read-only independent reviewer is NOT a
canonical-Note lookup failure. The graph reviewer has no Note repository
and may only compare the user's *source referent* with Core's planned fact,
while ordinary Core retains identity lookup/create/write authority. The
model-facing prompt now distinguishes an explicit, unambiguous source name
from a genuinely unresolved pronoun and forbids using lack of repository
access as a reason to label a named person ambiguous. It still rejects
swapped identities, lost participants, wrong owners, negated/conditional
mismatches and invented canonical bindings.

Six **fresh GPT-6 Router/Temporal + GPT-5.6 Core/graph** trial requests,
each on a clean copied canonical vault, are fully captured in
`benchmarks/application_router/hybrid_source_review_v1/`:

| Original case | New result | Exact factual readback |
|---|---|---|
| F06 | **COMPLETED** | One Day, two actual facts, including `Vi a [[Ana|Ana]]` and `y compré pan.`; independent reviewers both accepted. This is semantically complete despite optional punctuation/style polish. |
| F13 | **COMPLETED** | Three actual Day Notes, 03/10 conversation with canonical `[[Eric]]`, 05/10 cinema `[[Eric]]` using Core-persisted predecessor proof for `él`, and 04/10 bread purchase. The bread fact begins `. Hoy`: factual coverage complete, Markdown punctuation needs repair before strict UI-quality acceptance. |
| F14 | PARTIAL (correct fail-closed) | 03/10 conversation successfully linked to BOTH Eric and Luis. The subsequent `él` genuinely has two antecedents and no safe cinema write was made. |
| F05 | NEEDS_ATTENTION | Elliptical second dinner still cannot be fully source-attested. |
| F07 | FAILED | Fresh Planner supplied `temporal_reference.text='a las 15h'` / `'a las 17h'` although Temporal certified only `'15h'` / `'17h'`; Core correctly rejected these unauthorised longer source spans at prewrite validation. |
| F15 | NEEDS_ATTENTION | Collective/self-reference identity source proof still missing; no unsafe writes. |

The normal Core Planner prompt now explicitly requires the exact
`temporal_reference.source_text` and value, not a source-word superset,
and keeps the deterministic validator unchanged. One additional fresh F07
attempt in `benchmarks/application_router/hybrid_temporal_reference_v1/`
finished FAILED **before a Planner model response** (only Router and
Temporal were called): the experiment's conservative per-request maximum
cost reservation exceeded its temporary USD 0.485 cap. This is a
budget-preflight refusal, **not evidence that the revised Temporal prompt
does or does not work**. A zero-paid-call SDK-shaped replay test freezes
all six calls/outcomes; the three cases with physical writes have full
Markdown readback assertions.

**Latest strict source-and-readback acceptance = 10/27**: F06 now joins
the earlier nine cases. F13's three facts are semantically correct and
source-verified but one stored fact has an extraneous leading period;
hold its strict UI-quality acceptance until general source-fragment
punctuation treatment is verified. F07's historical grouped real
responses now replay into two person-linked facts under the general
participant guard but contain orphaned clock preposition/double spaces;
its subsequent fresh model attempts did not establish fully clean
writing. No other promotion is claimed. Total estimated experimental
spend: USD **0.471058 / 0.50 approved**, including the bounded fresh
reviewer batch and budget-preflight trial. No new paid gates are needed
to preserve or replay these receipts.

**Audit of the 13 seeded Notes:** Alex, Bea, Nina and Pablo already
contain mutual family links. These Notes are **not proof that a particular
incoming speaker is Alex**. Thus mapping `mi mujer` to Bea or `mis
hijos` to Nina/Pablo without an authenticated self-binding would be
an invented identity, even if the vault makes the relationship plausible.
Do not change the expected case outputs to pretend that this self-binding
is guaranteed. `person`, `project`, `concept`, `document`,
`calendar_day` and legacy `journal_entry` are BASE NoteSchema types;
`task` belongs only to the Tasks app extension.

**Two actively investigated blockers:**
- F18's **historical** Core reviewer returned `ambiguous_identity` for
  both source-fragment claims; the **fresh 2026-10-12 reviewer now returns
  `unsupported_scope` for BOTH even though the GPT-5.6 Planner proposes
  `No vi a Ana.` and `pero sí hablé con Luis.` correctly. The source
  candidate anchors `vi a Ana` / `hablé con Luis` omit `no` /
  `pero sí`, which must be reconciled with verified source polarity and
  discourse roles. This is general candidate-to-Core fact attribution,
  not merely a missing API credential or an absent date.
- F22's fresh GPT-6 Tasks/Temporal + GPT-5.6 Core run now creates all
  three correctly dated pending Task Notes, but GPT-5.6 Core Planner
  preserves the explicit canonical person identity for `Ana` while
  omitting the corresponding `Luis` wikilink. The middle Task's exact
  source action gets represented by a Temporal role/property, not an
  identity fact. Need **generic mandatory participant-source coverage in
  Task note content**, verified by Core, not an `Ana`/`Luis` heuristic.
  An empty `calendar_day` stub was also generated; it has no false
  factual content but deserves separate cleanup.

**Next execution order:** repair Core reviewer source polarity/discourse
attribution and Task missing-participant content coverage generally;
replay these genuine receipts, retest F18/F22 with bounded live gates,
then address the grouped failure classes (unsafe/missing references,
Planner ESCALATE, Temporal ordering, redundant Day references), always
checking actual Markdown. Historical 10 unrelated full-suite failures
remain and must be diagnosed before DEV. Do not mistake this new live
batch for 18 new accepted cases or deploy before the full original
27/27 gate.

**NEXT ORDER:** (1) obtain a new Router prompt gate before relying on new
standalone-negative proposals beyond deterministic source fixtures;
(2) resolve F18 independent negative/positive semantics and the remaining
F22 task intents with verified cross-group modality/date ownership;
(3) expand mixed-polarity F18 and ambiguous F14/F27 with canonical proof,
regression across all 27 original cases, and adversarial readback;
(4) review quality/cost and request separate approval before DEV/PROD.
Keep Core GPT-5.6 for now.

## Deferred model consolidation — user decision (2026-10-10)

**Do not change models during the current Router fact-candidate / Temporal / Core work.**
The user explicitly prefers finishing and validating this functional block
first, keeping its existing configured models and historical live-gate evidence
stable. **After this block is closed**, schedule a separate reviewed effort to
migrate remaining Odyssey components to **GPT-6 Luna** (including Core Planner,
Core Attribution, Writer, Fact Selector, clarification and contextual reasoning,
where still on GPT-5.6 Luna). Inventory actual runtime overrides as well as
code defaults; preserve prompt/contract and cost benchmarks, run focused live
model-quality gates under separately agreed budgets, then request approval
for DEV/PROD promotion. This is **deferred work**, not an authorization to
silently switch models, merge or deploy now.

## Router parallel preparation (DEV optimization)

[Router parallel preparation, Slices 1–2](router-parallel-preparation.md) allows
independent validated Router spans (Core, Tasks, Temporal) to run their
app-specific interpretation when needed **and shared Core model planning**
concurrently (up to two workers). The existing Core
execution boundary alone handles identity resolution, preflight, pending work,
Git and canonical writes **sequentially in route order**. Production still defaults
to sequential, with the preparation enabled only in isolated DEV. Do not confuse
concurrent Core *model planning* with parallel Core *execution*, and do not claim
measured latency savings from deterministic concurrence tests alone.

## Historical Router fact-candidate development log (superseded grouping policy)

**Precedence:** the 2026-10-12 [hybrid target](router-hybrid-interpretation-contract.md)
in the NEXT section above supersedes any older "one Core interpretation per
atomic candidate" instructions in the dated entries below. These entries
remain valuable evidence of actual implementation progress, provider
experiments and safety gates; they do **not** set the current target grouping
algorithm or imply hybrid DEV/PROD activation.



[Router fact-candidate units v1](router-fact-units-v1.md) records the user-reviewed direction for independent atomic candidate assertions, typed source-context inheritance, and separation from Core-owned persistence. Its 22 user-agreed plus four additional generic-subject future oracles are not a live Router contract, and the current `dev` Router v0 remains unchanged. Frontend Block 3 preparation now makes existing validated v1 route evidence legible, provides an optional read-only renderer for the inactive bounded checkpoint shape, and supplies a local test-only candidate preview; none crosses a product transport or grants write/identity authority. The approved partial-write direction retains validated independent facts while ambiguity remains pending with targeted clarification, not blanket abort. Diagnostic checkpoints/graph come before any v1 provider/runtime activation; product choices about partial writes and conditional/negative persistence remain open.

**Router candidates Block 4A (feature branch, not activated):** the closed
source-anchored parser and injected one-call proposal adapter are implemented for
the 26 design cases / 56 candidates. Roles and inheritance remain unverified
linguistic evidence with no Note type, Core write, runtime dispatch or new
frontend transport. Read-only Router→Temporal source-scope and Core-owned
candidate evidence/prompt opt-in are also prepared on the feature branch,
including one fully injected provider-free F13 vertical planner test. No
runtime branch uses these new contracts and none executes candidate writes.
Disposable Markdown tests now exercise existing Core persistence for three
activities across two dates, one shared two-item purchase, exact-request replay
and an ambiguous pronoun held out of synthetic writes. A Core-owned read-only
receipt observer exposes genuine unit statuses but deliberately leaves **all**
source candidates `unattributed`, since ordinals alone cannot prove a semantic
candidate was persisted. The existing Core result may say `completed` despite
an unresolved candidate deliberately omitted by a handwritten test plan; this
shows why per-candidate Core-verified attribution, pending clarification and
partial-success/idempotence guards still need implementation before activation.
Additional bounded readback now checks Core's actual canonical Markdown
fact markers by request ID, fact ordinal, stable Note ID and exact plan text.
It distinguishes confirmed physical writes from cross-request duplicate
suppression, `unproven` source candidates, ambiguous candidates and unknown
source coverage, and explicitly
forbids reporting the whole request as complete on Core fact markers alone.
An **opt-in Core preflight** now rejects missing candidate coverage or
unreviewed complex writes before any mutation, without touching Router v0.
If synthetic independent writes succeed while a candidate remains unresolved,
opt-in Core marks the request `PARTIAL` and explicitly reports that the
candidate continuation is **not durably resumable yet**. Structural attribution
is not proof that the right semantic fact was written; the new conservative
Core preflight now rejects a deliberately swapped pan/milk mapping, but does
not certify semantics. A Core-owned model-approved
mapping/semantic proof, safe reference handling, durable partial clarifications,
new request-detail projections and a true provider→verified attribution→Core
write vertical path, plus separate final live GPT-6 Router / GPT-5.6 Luna
semantic gates, remain required. Router v0 remains operational. The
isolated Core candidate preflight additionally rejects obvious mismatched
item evidence, a newly invented negation, and unverified source pronoun
references **before persistence**. Passing these vetoes is not semantic
attestation: mixed-clause negation, date ownership and grounded canonical
identity still require independent verification.

The human-approved partial clarification lifecycle now has an isolated v2
nonknowledge state store under `state/pending/candidates/`, leaving v1 planned
pending records and all canonical Notes intact. The opt-in Core callback
records a real pending candidate **only after** verifying written Markdown,
including original request/ordinal/target/fact digests; selections remain
Core-grounded, request-ID scoped and replay/staleness guarded. Synthetic
`Eric y Luis → él` tests now cover `con Luis`, cancellation (including after
selection), unrelated/multiple clarifications, restart, option changes and
previous fact changes. A guarded Core continuation with a pre-reviewed plan
writes only the outstanding cinema Day link, with original capture clock and
all previously saved facts unchanged. These remain **provider-free fixtures**;
no live model has produced an accepted continuation, no auto-close-to-resolved
semantic contract is claimed, and the v2 route is not wired into runtime.
Final model semantic gates plus the historical release hash/operator blockers
remain before any DEV activation.
Initial authorized GPT-6 Router/GPT-5.6 Luna live smoke (2026-10-10):
4 frozen synthetic source cases, **6** real zero-retry read-only model calls,
**$0.004006 estimated** standard-rate input/output cost; F11/F01/F13 passed
Router candidate counts/states, but F14 grouped `hablé con Eric y Luis`
into one conversation (2 units total), while the frozen oracle requires
3 independently accounted source facts. Pronoun remained explicitly ambiguous.
F11 Core attribution passed local source/fact checks and a real Core Luna
planner returned a nonexecuted validated 1-action plan, without semantic
execution proof. This is an **evidence-backed readiness FAIL**, not a model-
quality acceptance gate or permission to silently alter the human fixture.
The coordinated-participants granularity requires product adjudication; full
held-out model/continuation gates and historical release failures remain.

**Approved 2026-10-10 candidate granularity:** One coherent event may have
multiple canonical participants without inventing simultaneity. F14 now has
one linked Eric+Luis event plus a pending ambiguous `él` (2 source candidates).
F27 preserves the earlier distinct-conversation/ambiguous-pronoun behavior
using explicit "después" (3 source candidates). The immutable v1 design matrix and its frozen benchmark test stay at
26 cases / 56 candidates. The separately versioned approved v2 oracle has
27 cases / 58 candidates. In the **isolated Core pilot only**, a review-gated
one-event/two-named-reference plan persists one actual Day fact and two valid
canonical backlinks; this is also tested for two project Notes. Current guarded
Core write readback checks real rendered wikilinks and saves their digest for
pending continuity. A synthetic pre-reviewed follow-up writes only the
outstanding cinema fact and reuses original captures; no duplicates. The
user-approved semantics resolved the F14 unit-count disagreement in the prior
live smoke, not its still-unverified `plan` vs oracle `occurrence` kind,
or any held-out model quality gate. The separate Core-only Luna-attribution
proposer now accepts **only the same bounded two-name, two-link Core plan**
for untrusted source/fact matching; its existing model JSON and instructions
are unchanged and it cannot authorize a write. Provider-fake negative tests
prove omitted/swapped/extra helpers still fail closed. No normal runtime or
DEV activation yet.

**Experimental F14 semantic-plan compilation, 2026-10-10 (feature branch):**
The Core semantic compiler and Temporal evidence validators now support a
**strictly source-scoped omitted future date** when and only when an opt-in
unverified candidate is explicitly ambiguous and uniquely owns that exact
Temporal text plus original date/time role. The ordinary full-source Temporal
input remains unchanged; only a non-authoritative, Core-owned validation copy
excludes the pending mention. Missing safe dates, incorrect target days,
ambiguous repeated date text and absent scoped role still fail closed.
A frozen provider-shaped semantic WRITE now passes the actual Luna semantic
decoder and Core plan compiler and, subject to an **independently reviewed**
Core coverage manifest, persists one safe Eric+Luis linked Day fact with
`2026-10-03` anchor while durable v2 pending state retains the cine clause for
`2026-10-05`. No plan generated by a real provider has passed this new shape
or its semantic acceptance gate; no DEV activation, provider expense or changes
to model-facing prompts, output schemas, canonical NoteSchema or Router v0.

**V2 live gate blocker and offline cost decomposition (2026-10-10):**
The attempted large remote operation to author a second live evaluator was
blocked by the ChatGPT platform before remote execution; neither API nor Pi
reported an error. The separate offline-only audit
`benchmarks/fact_candidate_v2_preflight/check.py` now computes the actual
provider-request envelopes from fake-client production constructors for
F14/F27/F09/F10, with no API, secrets, writes or deployment. The conservative
full 9-call envelope is ~USD 0.0848571, above the user-authorized USD 0.02;
a potential limited 6-call Router/Temporal wave totals ~USD 0.013495.
Only an explicitly security-permitted and reviewed live-gate workflow may
execute that wave; the file is not an alternate live runner or circumvention.
See issue #151 for the historical blocked inline operation, which was
not retried.

**Actual v2 Router-only GPT-6 live evidence (2026-10-10):** A separate
versioned/snapshot-checked runner was accepted through the ordinary Pi user
service without changing the model, prompt, schema or user vault. Four synthetic
Router calls F14/F27/F09/F10 completed (2,134 input and 1,575 output tokens;
pinned standard-rate cost estimate **$0.0010009**, conservative pre-call bound
**$0.01181875** vs previously approved $0.02). The strict frozen fixture
comparison failed for all four because of shape differences, **but the
semantic split itself failed clearly on F09** (two independent residences
wrongly grouped into one relationship). F10 returned a correct single mutual
relation with different grounded spans. F14/F27 correctly distinguished one
coherent vs two sequential contact events and left `él` ambiguous, but
misclassified the future as `plan`, supplied noncanonical date role labels
and lacked Core-required participant/reference evidence; offline replay of
the **real model replies** is rejected by Core's canonical source coverage
preflight before any write. Saved synthetic responses and regression tests
are versioned under `benchmarks/fact_candidate_v2_live/`. **The limited
real-model evaluation is now unblocked and completed; Router v1 is still
NOT READY for DEV**, pending contract/prompt semantic corrections and a
reviewed new regression gate. That success does not determine the cause of
the older rejected remote shell command or authorize bypassing it.

**Second focused GPT-6 Router gate, opt-in prompt v2 (2026-10-10):** The
entire previous source-only prompt was retained and supplemented with generic
independent-property, mutual-relation, date, pronoun and future-event rules
without changing the model/schema or runtime. Four synthetic live calls
completed with 3,634 input / 1,389 output tokens and an estimated standard
USD **0.0010579** charge. F09 now separates Marta and Luis into **two**
independent property candidates; F14/F27 now distinguish exact `date`,
ambiguous `reference` and future `occurrence` roles. F10's mutual event
remains **one candidate** but was misclassified `occurrence` instead of
`relationship`. The F14/F27 model spans are more informative, but the
current **narrow opt-in Core source-evidence pilots reject their alternative
anchoring/role inheritance** before writes; this does NOT prove a problem
with their underlying event segmentation. Preserve these real observed
outputs offline and review whether Core should accept equivalent proven
source spans rather than overconstraining GPT-6 to one handwritten template.
Router v1 remains inactive; focus on **F09/F10/F14/F27 only** until both
semantic type accuracy and Core-reviewed coverage pass. The remaining 23
approved design cases are deliberately deferred until this four-case gate
is settled. No DEV/PROD or vault changes.

**Third focused real Router-only gate (2026-10-10):** With v3's opt-in
general distinction for reciprocal relationships, **all four actual GPT-6
responses now have the approved semantic candidate counts, core kinds
and ambiguity**: F09=two `property`; F10=one `relationship`;
F14=two `occurrence` (second pending); F27=three `occurrence`
(third pending). Strict exact-fragment comparison remains non-identical,
but each shown source role is grounded. Saved v3 synthetic responses:
`benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json`.
Pinned-rate estimated total for **three** four-call Router-only gates:
USD **0.0032356** (not billed total). Tested general, Core-owned source-span
guards now safely admit alternate original reference/participant/event
spans with reviewed lexical/date/sequence evidence. **Actual v2/v3 saved
Router outputs** complete disposable Core write/readback, durable pending
and the guarded `Con Luis` continuation for F14/F27, using the existing
provider-shaped *fake* GPT-5.6 Core planner output; F10's link source proof
also passes but its full Core planning/persistence is untested. This is
**focused Router success, not production activation or complete Core live
model acceptance**. Keep normal Core GPT-5.6 and Router v0 unchanged.

**F09/F10 separate Core model gate preflight (2026-10-10):** The saved
GPT-6 v3 F09 response now exercises real Core coverage and physically
writes **two distinct Person facts** to two pre-seeded synthetic Markdown
notes. Each candidate receives its own readback-confirmed fact; swapped,
duplicated or omitted writes are rejected before mutation. F10's single
mutual relationship passes the literal source/participant guard, but the
undated target and real Core-chosen write plan remain to be demonstrated.
A separate offline-by-default GPT-5.6 Luna/low Core-only two-call
evaluation is pinned at `benchmarks/fact_candidate_core_live/`. It
preserves the production planner prompt and JSON schema and cannot read
personal notes or execute write actions. The conservative two-call cost
envelope is **USD 0.06344020**, requiring **explicit new cumulative
approval of USD 0.07**, beyond the historical USD 0.02 Router test
authorization. **No real GPT-5.6 Core provider calls have yet run**;
do not infer model readiness from offline preflight. After approval,
evaluate its actual two Core plans/clarifications without assuming an
undated event belongs to today's Calendar Day. Leave F14/F27 and the
23 other Router design cases untouched for this distinct Core gate.

**F09/F10 real-model Core acceptance after explicit new budget approval
(2026-10-10):** The pinned, unchanged experimental **GPT-5.6 Luna/low**
Core planner returned two locally valid real `PLAN` outcomes for the
saved GPT-6 v3 Router sources: F09 chose two different existing
`person` targets and one `Vive en Lyon.` fact each; F10 chose
**one linked fact** on Marta's Person Note and one canonical
reference-only lookup to Luis. No invented historical date and no
duplicate reciprocal fact. The user explicitly expanded the cumulative
focused-testing authorization to **USD 0.07**. Core calls used
**21,004 input / 651 output tokens**, estimated **USD 0.0049820**
at pinned standard rates; including previous three Router gates, the
estimated focused-testing total is **USD 0.0082176** (not an
invoice). Core's narrow source evidence guards initially rejected
the valid implicit-subject F09 and one-reference mutual F10 plans;
they now require an exact source subject-to-target link plus original
location proof for independent properties, or exact two-party reciprocal
source evidence, one directed Person write and one immutable-reference
helper for F10. Full **offline replay of real provider-generated**
F09/F10 plans now physically writes the correct facts to two isolated
seeded Person Markdown Notes / one isolated Marta Note with a Luis
wikilink, verifies physical fact readback and the **backlink visible
from Luis**, and rejects wrong targets, other subjects, negation,
invented location/date, duplicate relationship facts and helper
mutations. This validates only **these four already-agreed
synthetic Router cases**, not the remaining 23 or a live request
pipeline; no normal Router activation, real vault write, model
migration or consent to additional spending is implied.

**F14/F27 live Core-model acceptance failed conservatively
(2026-10-10):** Four real GPT-5.6 Luna/low, strict-schema Core
calls completed on synthetic F14/F27 source plus actual saved
GPT-6 Router v3 candidates and deterministic Temporal
date interpretation: two with the unchanged Core prompt and two
with a separately hash-pinned, opt-in partial-fact planning
clarification. **All four returned `ESCALATE` without a plan**.
This is a Core model semantic refusal, not an API error, wrong
canonical write or an identity guess. The opt-in prompt did
not fix it, so stop paid wording tweaks. Frozen synthetic
responses and 21 provider-free regressions live under
`benchmarks/fact_candidate_core_live/results/` and
`tests/benchmarks/test_fact_candidate_core_temporal_observed_live.py`.
Estimated Router+Core focused-testing spend is USD
**0.0185276**, under the explicitly authorized USD 0.07;
these are pinned rate estimates, not billed totals.
The next design experiment should be **Core-owned scoped
planning for independently source-proven clauses**, with
the complete untouched source, context and correction vetoes
retained, mandatory pre-write candidate coverage and durable
ambiguous pending. Purely splitting at sentence punctuation
does not prove semantic independence; no unsafe source
truncation or Router-provided write authority is allowed.
**The existing mechanically successful injected-plan F14/F27
tests do not constitute real GPT-5.6 acceptance.** No DEV/PROD
activation or personal Notes writes. Keep Core GPT-5.6.

**F27 exact sequential-source Core pilot (2026-10-10):** The two separate
conversation facts for `hablé con Eric y después con Luis` now also pass a
real (fake-model) semantic Core compilation, source-before-write candidate
coverage, per-fact canonical reference verification, two true Markdown
backlinks, durable pending state and a guarded `Con Luis` continuation.
Core checks the explicit "después" distinction and two independent dated
atomic facts; F14 continues using the different one-event/two-participant
contract. Incorrect order/name/helper/time and invented pending pronoun scope
fail closed. This is a narrow regression with injected frozen model responses;
no provider-quality proof or DEV activation is claimed.

**Request-wide F14/F27 continuation safety (2026-10-10):** Added an
opt-in before-any-action Core guard for the selected `Con Luis` continuation.
A single source-anchored cinema fact, the original `mañana` date and one
existing canonical helper are required; extra RequestPlan actions and
mismatched event/date are rejected without writing. Last-moment identity
checks remain intact. This is a narrow disposable-vault pilot with synthetic
planner outputs, not general semantic certification or live activation.

## Current functional work — explainable clarification

[Performance / Latency / Cost P1](performance-cost-p1.md) is complete. Its baseline found that the
universal Luna → Sol route was a local Luna planner-result validation mismatch after successful
provider completion, not a provider failure. The envelope repair restored direct valid Luna planning.
The one measured avoidable contributor was duplicated Structured Outputs schema material: PR #129
reused local `$defs` / `$ref` definitions without changing the planner language or semantic validators.
The Luna schema fell from 35,662 to 9,694 serialized bytes (72.8%), planner input from roughly 11.87k
to 7.15k tokens, and the representative Luna-only READ / WRITE / CLARIFY gates took 2.963 s / 2.143 s
/ 1.934 s with no Sol fallback. Small later prompt/capability probes did not establish a reliable
input-size/latency relationship; provider/model base latency and variance now dominate the remaining
roughly 2–3 seconds. P1 therefore stops here: no request-type-specific schema or fast path is planned.
PR #129 merged at `1c2f0c45672e8d1d917cf6abd271a85123100b8e` and was explicitly deployed to isolated
DEV, where runtime and DEV n8n health and provenance were `MATCH`; PROD was untouched.

The provider-free [Reference & Relationship Resolution v1 Slices 1–2](post-ui2-note-creation-and-schema-evolution.md#proposed-implementation-slices)
are implemented. Slice 3 now has a Draft implementation of the relational planner contract and
minimal Core read/write bridge on a feature branch; its frozen ten-case production model gate is
**pending review** after three bounded attempts. Attempt 1 at
`2405b136fc9abe686efb49599ba6368e479fe71a` stopped before provider construction because its shell
had not exported the protected `OPENAI_API_KEY`; its retained evidence has zero rows. Attempt 2 at
`e17b5f750573e39aebf8477e933902e083ad7f9f` used the verified same-shell export procedure and
reached three Luna-only cases within the $0.455998 ceiling: R01/W01 passed, then W02 safely clarified
instead of producing the required complete-set shared-fact write (`FAIL_CLOSED`). It stopped with no
Sol fallback; actual recorded cost was $0.00250944. The follow-up added one non-evaluation Luna
complete-set source-write teaching example without changing the frozen W02 case/oracle or
deterministic Core. Attempt 3 at `0c28855f35b39f4429ae2fc60db180a38fe3b9d6` then passed R01,
W01, W02, C01, P01, S01, and S02 Luna-only; W02 used the required complete-set source-write shape.
S03 required one Sol fallback after Luna's local `KNOWLEDGE_UNIT` / `INVALID_FIELDS` validation
failure. The runner retained the passing fallback row and stopped as required: 8 attempted cases,
8 Luna calls, 1 Sol call, $0.05772924 actual cost, and the expected W02 `source_selector_review`
flag. Review accepts that W02 selector as natural-language source intent (`ayer`) and accepts S03
as a passing production fallback: its final Sol plan preserves ordinary Marta/Airbus
`KnowledgeReference` semantics. S04/S05 were not attempted. A fixed, unexecuted continuation for
only S04/S05 has a $0.36979880 ceiling for at most three calls and requires separate explicit human
authorization. That $0.37 authorization was recorded at
`828672cc4597c1931853cf32d1fa90330eccf25b`; the continuation ran once at the same HEAD and passed
S04/S05 Luna-only. S04 preserved ordinary `all_matching` tag-add semantics and S05 preserved two
independent ordinary Marta facts. It made 2 Luna calls, no Sol calls or fallbacks, and cost
$0.00216274. All ten frozen cases have reviewed evidence, so the focused Slice 3 model gate
passed within the bounded v1 contract. Slice 3 and v1 merged in PR #133. A subsequent DEV smoke
exposed the generic read-path gap: one canonical shared fact was visible in UI-2 backlinks but was
absent from ordinary entity-answer context. The merged Core request-aware, one-hop source-fact
enrichment keeps direct entity notes primary; current canonical incoming/outgoing snippets are
locally ranked and serialized with actual source provenance, without graph traversal or copied
member prose. The existing
current-Markdown, one-source, one-hop evidence boundary, shared-fact home, inverse/symmetric
evidence policy, and all-or-clarify rule remain the v1 contract. UI-1 request detail is complete in PROD;
its production promotion evidence is in [UI-1 production promotion](ui-1-production-promotion.md).

[Semantic set resolution and evidence](semantic-set-resolution-and-evidence.md) is complete and merged in
PR #142. The approved simplification keeps ordinary single-topic answers, matching Notes as objects via
`presentation_intent=note_set`, and canonical-fact collections via `RetrieveAction.result_shape=collection`
distinct. The planner preserves a lossless query while Core owns bounded evidence, collection discovery,
grounding, completeness, ambiguity, stale checks, and fail-closed behavior; no generic Note/type,
automatic entity promotion, recursive graph inference, or keyword/domain router is introduced. The narrow
clarification-continuation slice (#137) is included; broader staged/multi-action continuation remains deferred.

The focused Luna/low live-regression gate for PR #142 is **closed**. Collection-shape, Note-set/singular,
linked-selection, write, clarification, escalation, and mixed-action sentinels now have passing evidence on
the final behavior-bearing HEAD `8f99a1197cfaaf7c5a640f1749926fa8a2155a96`; the remaining five closeout
sentinels passed 5/5, and a one-call SM01 diagnostic reproduced the previously reviewed valid plan. Two earlier
DNS-resolution failures were pre-provider infrastructure evidence only. A real Structured Outputs/Core mismatch
was also closed by requiring non-empty `WriteAction.units`, and bounded write diagnostics were refined without
relaxing validation. No additional Luna calls are required. Detailed retry/evidence history is retained in the PR
and benchmark artifacts rather than duplicated here.

Real DEV smoke after #142 exposed #140/#137 behavior: duplicate self facts could falsely appear
ambiguous, singular multi-member facts did not yield safe identity choices, and collection
planning dropped authenticated-self scope. The observed 22-source/55-fact/13,162-byte DEV scan
stayed within its former bounds; those limits were a separate vault-size cliff.
The [corrective architecture challenge](semantic-set-resolution-and-evidence.md#corrective-architecture-challenge-after-real-dev-evidence-140137)
revised the contract and is implemented on `fix/semantic-self-clarification`: minimal
`self | query` collection subject, Core-bound self evidence, exact relational target
deduplication, reuse of existing pending identity clarification, bounded progressive canonical
scanning, and distinct user-safe failure reasons. Deterministic Core/runtime coverage is complete.
The frozen v8 Luna/low gate ran once at `32585c47bab0a90159ce2fc05339aa1c1c22ce5b` and stopped
fail-fast after two calls: SSET01 passed; SSET02 failed because it emitted
`collection_subject=self` instead of the unchanged required `query`. The two-row immutable artifact
has SHA-256 `cf4b5b9295f35149840105cca8fc02a2fae6abc066bdfb3307a83123bc7fe35e`. The frozen v9 gate
then ran once at `e86de53dabdd8b628d7918fdda647f629d4862a1`: SSET01 through REG02 passed, including
SSET02 as `collection_subject=query`, then NOTE01 failed closed at `RETRIEVE_ACTION` /
`SELECTION_MODE_CONFLICT`. Its seven-row immutable artifact has SHA-256
`edaeaa65885d7340efb821a9013aaac367031fa60ad4066d9b31ebe453762bcf`; neither run reached selector
rows, retried, or used Sol. Core validation remains fail closed. The current structural correction
partitions `collection_subject` by retrieval shape in the provider schema and prepares frozen v10,
which reuses all 21 planner and 4 selector rows with a 25-call maximum and `$0.41144` conservative
no-cache ceiling. V10 requires separate Luna/low authorization before production model-facing
adoption.

[UI polish + Notes editing lite](ui-polish-notes-editing-lite.md) merged in PR #144, the
Luna-only Semantic WRITE compiler simplification merged in PR #147, and Explainable Clarification UX
merged in PR #148. The clarification phase is complete: the user validated the candidate/evidence UI
and natural-language continuation in isolated DEV, deterministic validation remained green, and the
final reviewed Luna/low planner evidence fixed the blocking ownership regression while retaining the
approved fail-closed degradations. PROD has not been promoted to #148.

[Notes grouped browsing UX](notes-grouped-browsing.md) is implemented and user-validated in isolated
DEV. Runtime-composed Notes capabilities own the visible type descriptions/properties; ordinary
feed/local browsing has independent bounded type cursors, while intelligent and historical result
sets preserve one global deterministic authority. Calendar Day remains outside Notes-visible groups.
The follow-on [Calendar rich month view](calendar-rich-month-view.md) replaces dot-only monthly
indicators with a bounded four-row semantic preview while preserving one month request and the
existing Day navigation boundary; compact/expanded month modes and per-Day `Ver más` are now
user-validated in isolated DEV. The next [Calendar multi-day schedule view](calendar-multiday-schedule-view.md)
adds a read-only 1/3/7-day hourly projection over existing exact Task planning coordinates and semantic
fact anchors, with window-sized swipe navigation; implementation is complete and isolated-DEV mobile
review is next.

[Temporal Foundation v1](temporal-foundation-v1.md) is provider-free complete. Calendar v0 and
Application Boundary + Router v0 have completed their earlier focused live gates and isolated-DEV
adoption, and the shared Temporal contract now adds timezone-validated `EXACT_DATETIME` without
introducing app-to-app routing. The bounded Journal/Temporal convergence follow-up remains the active
closeout before Tasks. Router v6 first passed its 17/17 successor matrix, Temporal passed 5/6 with the
sole missing-offset result subsequently canonicalized deterministically, and the `complete_set`
fact-reference correction then passed its consumed Core successor gate 4/4 at `$0.01135904` regional
estimated cost. A later disposable full-runtime user-path check intentionally went beyond those isolated
model gates and found two additional integration/model-boundary issues: the exact Ana/Luis request
completed correctly but Router did not split it on that call, while `Mañana a las 15:35 viene el
fontanero.` failed closed with zero mutation after Luna semantic-write validation and bounded Sol
fallback. Review found provider schemas still admitted managed Calendar Day shapes that deterministic
Core rejects. The candidate now aligns Luna's Day operation branch with Core's `one + record +
facts-only` rule and constrains Sol Day selection to trusted exact dates. The explicitly authorized
eight-call Router/Core successor was then consumed with zero retries/mutations at `$0.00932448`:
Core passed 3/3, including the exact-time fontanero case, while Router passed 3/5. The three repeated
Ana/Luis splits all passed; the two failures were the dependent no-split sentinels (shared temporal
scope and ellipsis/specialization). No live retry was performed. Router's current candidate therefore
strengthens exact-span semantic completeness and selects specialized capabilities from requested
lifecycle semantics rather than surface resemblance, without phrase-specific rules. Disposable
provider-free user paths now preserve Ana/Luis as two Day writes and render exact Day time canonically
as `15:35 — ...`; the full deterministic suite is green. **Tasks** remains next after a small isolated-
DEV user-visible validation of this post-gate Router revision.

```text
20.0  consumer contract + architecture challenge             ✅ complete
20.1A offline grounded-answerer benchmark preparation        ✅ complete
20.1B focused live answerer model evidence                    ✅ complete
20.2A mobile web source + offline deterministic checks        ✅ complete
20.2B real n8n serving + Chrome Android validation            ✅ complete
20.2C planner incident hardening + focused live gate          ✅ complete
20.2D Luna-first planner experiment preparation               ✅ complete
20.2E Luna prompt-parity + atomicity validation               ✅ complete
20.2F Luna-first semantic planning + same-contract Sol fallback   ✅ complete
20.2G contextual reasoner Luna replacement                    ✅ complete
20.3  protected Raspberry/Cloudflare deployment + E2E        ✅ complete
21A   isolation architecture challenge                       ✅ complete
21B   isolated DEV checkout/data + transient runtime proof   ✅ complete
21C   persistent DEV runtime/operations + DEV n8n decision   ✅ complete
21D   synchronized DEV n8n/routing pilot                     ✅ complete
Phase 21 production/development isolation                    ✅ complete
22A  self-identity architecture contract                    ✅ complete
22B  typed actor boundary + principal mapping foundation     ✅ complete
22C  explicit self-person binding                             ✅ complete
22D  authenticated human provenance propagation                ✅ complete
22E  deterministic self resolution                              ✅ complete
22F  focused isolated-DEV adoption gate                         ✅ complete
23A  production repository + live boundary inventory             ✅ complete
23B  trusted principal projection                                ✅ complete
23C  explicit production self binding                             ✅ complete
23D  reboot-safe production operator + provenance                ✅ complete
23E  read-only human-authenticated production SELF E2E            ✅ complete
UI-1 request detail / advanced inspector                         ✅ complete in PROD
UI-0 durable main conversation/continuity                        ✅ complete in PROD
UI-0 explicit production promotion                              ✅ complete
UI-2 read-only Notes                                              ✅ merged in PR #124
Performance / Latency / Cost P1                                  ✅ complete
Reference & Relationship Resolution v1 Slice 1                    ✅ complete
Reference & Relationship Resolution v1 Slice 2                    ✅ complete
Reference & Relationship Resolution v1 Slice 3                    ✅ merged in PR #133
Semantic WRITE intent/Core compiler simplification                ✅ complete — v8 accepted at 12/13; GPT-5.6 Luna retained
Semantic set resolution and evidence                             ✅ merged in PR #142
Semantic self scope and clarification correction                   ✅ complete
UI polish + Notes editing lite                                     ✅ merged in PR #144
Explainable Clarification UX                                       ✅ merged in PR #148; DEV validated
Temporal Foundation + Calendar v0                                  ✅ Attempt 8 Calendar low live gate 10/10; DEV adopted
Application Boundary + Router v0                                    ✅ Attempt 5 Router live gate 8/8; DEV adopted
Temporal Foundation v1 — shared date/date-time contract              ✅ provider-free complete; Calendar artifacts unchanged
Journal/Temporal convergence follow-up                              ➡️ isolated DEV user-visible validation pending
Tasks — first lifecycle-heavy domain application                  ⬜ after DEV user-path recheck
Notes grouped browsing UX                                         ✅ isolated DEV user-validated; future authoring controls deferred
Calendar rich month view                                          ✅ isolated DEV user-validated
Calendar multi-day 1/3/7 schedule view                            ➡️ implementation complete; isolated DEV mobile review next
Events — timed occurrence semantics on Calendar                   ⬜ after Tasks
Reminders — lower-level delivery for Tasks / Events               ⬜ planned as needed
Maintainability checkpoint — bounded cleanup after calendar path  ⬜ planned
Projects — compose over Tasks                                     ⬜ planned after checkpoint
```

Merged PR #147 contains the first reversible offline Luna-only semantic WRITE frontend.
Provider-free assertions keep Sol's 25,474-byte prompt and 47,418-byte provider schema identical to
baseline while Luna compiles each ordered semantic write action immediately into the existing
`WriteAction` / `RequestPlan` boundary. After the v6 regression review, the teaching data is restored
semantically to the last stable checkpoint that passed SWR01-SWR07. The current Luna prompt is 32,281
bytes (from 32,076), the whole schema is 18,539 bytes (from 22,521), and the WRITE branch is 3,378
bytes (from 7,343); these are size measurements only, not latency evidence. Historical v8 assets remain
immutable and old-contract v9 is retired unexecuted. The authorized v6 gate passed SWR01-SWR03 but
regressed on SWR04 after example retuning. Rather than continue that non-monotonic tuning, frontend-v7
is retired unexecuted. Offline frontend-v8 restores the known-best teaching semantics and changes only
the semantic source vocabulary: provider-facing `EXISTING_DESCRIPTION` becomes `SOURCE_DESCRIPTION`.
This no longer asks Luna to assert source existence; it describes the user-supplied source and Core
must ground it as existing canonical evidence or clarify. The same 13-case gate collected the complete matrix in one authorized run: **12/13 passed**. SWR08 and SWR10 passed; only SWR07 failed because Luna kept the full qualified participant description but omitted its source-bounded candidate scope. This makes the remaining weakness explicit rather than hiding later results behind fail-fast. The v8 lineage is now permanently consumed at `MAX_COST_USD=$0.00`. The project accepts that bounded degradation rather than adding case-specific prompt complexity. A frozen model-only comparison then ran the identical matrix on `gpt-6-luna` / low: **11/13 passed**. GPT-6 Luna fixed SWR07 but regressed SWR08 and SWR10 by dropping event-source bounds on fact references. Its estimated cost was `$0.00419596` versus `$0.00912232` for GPT-5.6 Luna, but the planner retains **GPT-5.6 Luna** because it is more accurate on the frozen regression matrix.

Earlier latency observations motivate P1 but do not predetermine its bottleneck or authorize a fast path.

### 20.1B — answerer adoption gate

Complete. Frozen live evidence selected the inexpensive grounded answerer without weakening the bounded evidence contract. See [Phase 20.1 grounded-answerer benchmark](phase-20-1-grounded-answerer-benchmark.md).

### 20.2B — real browser integration

Complete. The checked-in `odyssey_web/` surface is served through the private n8n-facing product boundary. Raspberry-backed integration evidence covers the narrow request/response routes, and the physical Chrome/Android checkpoint covers the mobile UI, bounded delivery failure, restored controls, and explicit same-`request_id` Retry behavior.

### 20.2C — planner incident hardening

Complete. The production planner has explicit clarification, a bounded output envelope, zero automatic retries, and bounded post-parse validation diagnostics. See [Planner incident hardening](planner-incident-hardening.md).

### 20.2D–20.2F — Luna-first planner adoption

Complete. Luna/low is the production first pass. Safe PLAN/CLARIFY returns directly; structured fail-closed may invoke one bounded Sol/low fallback through the **same semantic prompt/schema/compiler**, so the fallback differs only by model rather than by planner language. Separate provider-call evidence preserves the real Luna/Sol usage split. See [Phase 20.2F — Luna-first production planning](phase-20-2f-luna-first-production.md).

### 20.2G — contextual reasoner Luna replacement

Complete. The full frozen 90-case Luna/medium benchmark produced 88/90 frozen-label accuracy, 35/35 correct `RESOLVED` decisions, zero clear false `RESOLVED`, and zero invalid outputs. Production now uses Luna/medium with the same canonical ten-example calibration prefix. See [Phase 20.2G — contextual reasoner Luna replacement gate](phase-20-2g-contextual-luna-gate.md).

### 20.3 — protected deployment

Complete and merged in PR #103. The protected Cloudflare boundary, disposable mobile E2E, production-vault Git bootstrap/index rebuild, and bounded real-runtime activation were all verified before merge.

```text
20.3A deployment/security inventory                          ✅ complete
20.3B protected hostname + Access + tunnel JWT enforcement   ✅ complete
      exact Odyssey-path bypass closure on n8n hostname      ✅ complete
20.3C disposable protected mobile E2E                        ✅ complete
      protected login / UI / CSS / JS                        ✅
      disposable WRITE                                       ✅
      disposable READ                                        ✅
      fail-closed clarification                              ✅
      inspect disposable Markdown/Git evidence               ✅
      reconcile deployed n8n workflow drift                  ✅
      final protected browser clarification                  ✅
      stop disposable runtime / close test state             ✅
20.3D real-vault activation                                  ✅ complete
      exact /data/odyssey/vault Git root + baseline          ✅
      rebuildable production indexes reset/rebuilt           ✅
      private production runtime health/listening verified   ✅
```

20.3B originally established the dedicated `odyssey.ragdehl.com` Access application with the approved user identity, tunnel-side Access JWT validation, and a separate deny-by-default Access application covering the then-current five Odyssey paths on `n8n.ragdehl.com`; unrelated n8n root/admin behavior remained unchanged. UI-0 later expanded that alternate-host Access set to seven by adding `/api/environment.js` and `/api/conversation`, with unauthenticated redirect evidence for both. The Cloudflare/certificate/Docker-DNS recovery details belong to the Phase 20.3 deployment document rather than this roadmap.

20.3C used an isolated disposable vault/runtime/pending root before any real-vault product test. The protected mobile E2E has successful WRITE, READ, and explicit clarification evidence, plus request-correlated Markdown/Git evidence. During clarification testing, a deployment-drift bug was found: the active n8n Odyssey product workflow had fallen behind the checked-in `workflows/odyssey-online.ts` contract. The existing active workflow was reconciled and republished without creating a second active endpoint, and the final protected browser clarification passed. At the 20.3C close the disposable runtime and test state were stopped/removed and port `8765` was free; 20.3D subsequently activated the separate real production runtime after the authorized vault bootstrap.

20.3D initialized `/data/odyssey/vault` as the exact production Git repository root with empty baseline commit `465773757427597b1f6036e94e670c8dd360d882`, reset only the guarded rebuildable `context.sqlite3` and `semantic.sqlite3` indexes, rebuilt them from the empty canonical vault, and started the private production runtime. Post-start evidence showed HTTP 200 on `172.18.0.1:8765/healthz`, with no listener on `127.0.0.1:8765`. No synthetic personal WRITE was used for activation.

The first mobile E2E exposed the need for bounded immediate conversation continuity: a follow-up such
as `¿Dónde vive?` safely abstained after discussing one person. UI-0 later implemented that need with
one bounded recent-turn window while keeping canonical notes/facts authoritative. The durable
conversation/context contract is owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md) and [UI-0 durable main conversation](ui-0-durable-conversations.md).

## Phase 21 status — production and development isolation

Phase 21A–21D are complete. Odyssey now has a persistent isolated DEV source/data/runtime boundary, an on-demand separate DEV n8n stack, a fixed Access-protected DEV browser endpoint, deployment provenance/drift checks, and verified production non-interference.

The first real personal production cycle is complete. On 2026-09-11 the mobile UI wrote `Me llamo Edgar, soy data engineer y trabajo en Alten para Airbus`, producing one canonical `person` note for Edgar with two atomic facts and a request-correlated Git commit/index refresh; the subsequent mobile READ `¿Dónde trabaja Edgar?` returned `Edgar trabaja en Alten para Airbus.` No synthetic benchmark request was used for this milestone.

```text
first real personal use                               ✅ complete
        |
        v
production / development isolation                    ✅ complete
        |
        v
user self-identity binding to ordinary person note    ✅ complete
        |
        v
UI-1 request feedback / advanced inspector            ✅ complete in PROD
        |
        v
UI-0 durable main conversation / continuity           ✅ complete in PROD
        |
        v
UI-2 read-only Notes                                   ✅ merged
        |
        v
Performance / Latency / Cost P1                       ✅ complete
        |
        v
Reference & Relationship Resolution v1 Slice 1        ✅ complete
Reference & Relationship Resolution v1 Slice 2        ✅ complete
Reference & Relationship Resolution v1 Slice 3        ✅ merged in PR #133
Semantic set resolution and evidence                  ✅ merged in PR #142
Explainable Clarification UX                           ✅ merged in PR #148
        |
        v
Temporal Foundation + Calendar v0                     ✅ Attempt 8 Calendar low live gate 10/10; DEV adopted
        |
        v
Application Boundary + Router v0                     ✅ Attempt 5 Router 8/8 + Calendar Attempt 8 10/10; DEV adopted
        |
        v
Temporal Foundation v1                               ✅ shared EXACT_DATETIME contract complete
        |
        v
Tasks — first lifecycle-heavy domain application
        |
        v
Notes grouped browsing UX
        |
        v
Calendar rich month view
        |
        v
Calendar 1/3/7-day read-only schedule projection
        |
        v
Events — timed occurrence semantics on Calendar
        |
        v
Reminders as needed by Tasks / Events
        |
        v
bounded maintainability checkpoint
        |
        v
Projects / Activity / editing / analytics by real use
```

The production/development split now precedes substantial new feature development so future disposable tests cannot affect real personal knowledge. See the [Phase 21 evidence](phase-21-development-isolation.md).

The self-identity implementation is complete and Phase 23 production adoption is closed. The person note stays in the normal vault/search/statistics surface; only the account/actor binding is separate identity state. The tracked reboot-safe `odyssey-prod` operator is human-gated, and cloudflared lifecycle remains outside it. See [Phase 22 contract](phase-22-self-identity.md), [Phase 23 production adoption](phase-23-production-self-identity-adoption.md), and [Future user self-identity binding](future-user-self-identity.md).

## Committed post-MVP directions

These are real product directions; exact implementation should remain incremental.

### Production and development isolation

Once real use depends on Odyssey, maintain a stable production deployment and a separate development/staging deployment so feature work and disposable tests cannot affect users or personal knowledge. `main` remains the production-ready source by default; feature branches feed development/staging before promotion. A permanent `develop` branch is optional and should be introduced only if repeated parallel integration work justifies it. See [Development Pipeline](development-pipeline.md#production-and-development-isolation).

```text
21A architecture/isolation decision                         ✅ complete
21B transient isolated runtime proof                        ✅ complete
21C persistent isolated DEV runtime/operator workflow       ✅ complete
21D on-demand DEV n8n + fixed protected browser endpoint    ✅ complete
Phase 21 production/development isolation                   ✅ complete
```

The DEV environment has fixed source/data/runtime identities and an on-demand separate n8n
database/container. It is not a permanent Git branch. The fixed protected endpoint and human
browser checkpoint are complete; ordinary feature work should continue through isolated DEV before
explicit human-gated production promotion.

### Natural conversation and history

Conversation continuity is a concrete post-MVP requirement, delivered first as one persistent main
chat rather than chat management. A deterministic bounded recent-turn window accompanies the current
request in the existing Luna-first planner call. It may resolve conversational wording but never
becomes a current-fact source or retrieval expansion; the validated plan continues to route to
canonical Markdown only. Historical knowledge questions belong to canonical notes, fact-capture
chronology, and canonical Git/request history. Transcript search, summaries, topic splitting, and
multiple-chat UX are not UI-0 follow-on roadmap work; any such product would require separate
justification. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).

### Composable applications and capabilities

Applications should reuse shared Odyssey knowledge and lower-level capabilities rather than creating isolated stores or duplicate semantics. A useful target is composition such as:

```text
Projects -> Tasks
             |
             v
         Reminders

Events ------+
```

The approved user interaction model is **automatic routing by default, explicit routing when useful**. Ordinary users should speak naturally in the main conversation; the relevant capability is selected internally and only that selected capability should execute/respond. Optional syntax such as `@Tasks` may direct or disambiguate a request but must never be required. A capability-specific surface may exist only when a concrete need justifies it, while reusing the same knowledge, identity, and application state rather than becoming a silo. Applications may show a small capability identity in the UI, but should not become independent personalities that all listen to every message. Nested threads and branching chat management are not committed directions.

The approved order now starts with **Temporal Foundation + Calendar v0**, followed by the small
**Temporal Foundation v1** extension: date/Day identity and Calendar-managed daily capture remain
lower-level behavior, while the shared normalized contract now also supports timezone-validated exact
date-times for Tasks and later Events. **Tasks** remains the first lifecycle-heavy domain application.
**Events** follows Tasks and projects timed occurrences onto the same Calendar surface. **Reminders**
should provide only the lower-level notification/delivery semantics Tasks and Events actually need; it
must not collapse tasks and events into one model. **Projects** remains a committed consumer of Tasks
but can follow the calendar path and the bounded maintainability checkpoint rather than blocking
Events. See [Temporal Foundation + Calendar v0](temporal-foundation-calendar-v0.md),
[Temporal Foundation v1](temporal-foundation-v1.md), and
[Future Events / Calendar capability](future-events-calendar.md).

Do not build a generic plugin platform before Tasks proves what the common application contract actually needs.

Planner/model extensibility must stay configuration-driven where semantics are already supported. The current planner derives note-type/property capabilities from `config/note-schema.json`; downstream model boundaries are generic with respect to concrete note types. The remaining application gap is executable manifest/registry routing for `DelegateAction`, not hard-coded app selection in the base planner. See [Architecture Overview](overview.md#configuration-driven-model-boundaries), [Future Odyssey product interface](future-product-interface.md#application-interaction--automatic-by-default-explicit-when-useful), [Future Extension Points](future-extension-points.md), [Future Events / Calendar capability](future-events-calendar.md), and [Odyssey Platform Direction](odyssey-platform-direction.md).

Once application work becomes repetitive, evaluate a bounded **agent-assisted delivery loop**: human + assistant approve a feature contract and validation criteria, an implementation agent works only in isolated DEV, deterministic checks run first, an independent validation agent reviews from fresh context, and only a final evidence-backed PR returns to the human for acceptance. This automation should not be introduced during Core architecture work and must never autonomously merge/promote production. Detailed guardrails and scheduling direction live in [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).

### Maintainability checkpoint after the calendar/application foundation

Maintainability is a continuous acceptance concern during every phase, but Odyssey should not pause
useful product work now for speculative restructuring. The near-term priority is the approved Temporal Foundation + Calendar v0 plus the bounded Temporal v1 date-time extension, then Tasks and Events with the minimum Reminder semantics those capabilities need.

After that path has exercised the application boundary in real code, schedule a **bounded
maintainability checkpoint** before substantial secondary-app expansion. The checkpoint should use
actual change pain and duplication as evidence: retire proven legacy, consolidate genuinely repeated
contracts, split modules that have accumulated unrelated responsibilities, and strengthen fragile
contract tests. It is explicitly **not** a rewrite, architecture reset, or demand to DRY across
intentional trust-boundary validation.

Current watchpoints and the per-phase reuse/refactor discipline are owned by the
[Development Pipeline](development-pipeline.md#maintainability-guard-during-feature-work).

### Multi-user shared knowledge

Support private and selectively shared knowledge only after authentication, authorization-before-retrieval, synchronization, conflict, and storage boundaries are explicit. A shared household list is an early concrete validation scenario. Each authenticated actor should be able to bind to its own ordinary canonical `person` note without creating a special `user` knowledge type or per-application profile copy.

See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) and [Future user self-identity binding](future-user-self-identity.md).

## Later / conditional directions

The detailed index is [Future Extension Points](future-extension-points.md). Important preserved directions include:

- 💡 **Retrieval refinement from real misses:** first test query-decomposed multi-fact/entity-coverage retrieval; only then add candidate reduction or compact evidence if measured cost/volume justifies it. See [Future retrieval refinements](future-query-decomposed-retrieval.md).
- 💡 **Pending-reference evolution / schema coaching:** safely relink exact attributable occurrences and use repeated unresolved patterns only as advisory evidence for future schema proposals. See [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Historical canonical-knowledge retrieval:** extend note/fact chronology and canonical Git/request-history access only when a concrete historical knowledge question requires it; do not substitute chat-history search. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).
- 💡 **Usage/cost observability:** project already-collected safe operational/provider evidence into simple and advanced product views without creating a second tracing authority. This now explicitly includes integration/deployment provenance and a `MATCH | DRIFT | UNKNOWN` view of checked-in workflow source versus the active deployed workflow. See [Future product usage observability](future-product-usage-observability.md).
- 💡 **Capture-context provenance:** optional location/context belongs to fact/request provenance, not entity properties. See [Future capture-context provenance](future-capture-context-provenance.md).
- 💡 **Platform/local-first portability:** keep Core/data contracts usable by self-hosted, future local/mobile, app, and agent clients without making a central Odyssey server semantically mandatory. See [Odyssey Platform Direction](odyssey-platform-direction.md).
- 💡 **Notes authoring and schema coaching:** grouped Notes should eventually support per-type Note creation, structured type/property editing with optional bounded conversational help, and manual editing of user-editable Note properties while keeping system provenance/identity and application-owned lifecycle fields protected. See [Future Odyssey product interface](future-product-interface.md#ui-4--safe-note-editing).
- 💡 **Product-wide localization:** a future language switch must translate the complete interface and onboarding/help copy—including type/property presentation—without changing canonical schema semantics or stored knowledge. See [Future Odyssey product interface](future-product-interface.md#deferred-product-decisions).
- 💡 **Direct Markdown/Obsidian edit ingestion:** eventually recognize authorized external edits, avoid self-trigger loops, validate only required normalization, refresh derived state, and audit accepted changes.
- 💡 **Structured analytics:** deterministic counts/sums/grouping over rebuildable structured/index data; do not load the whole vault into an LLM for arithmetic.
- 💡 **Agent-assisted app delivery:** after application work becomes routine, queue only human-approved feature contracts and let bounded implementation/validation agents work in isolated DEV with deterministic gates, explicit budgets, no autonomous merge/promotion, and final human acceptance. See [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).
- 🔄 **Cost-aware model routing:** Luna-first production planning and Luna/medium contextual reasoning are active; retain bounded Sol fallback only where the validated production contract requires it and continue optimizing from measured telemetry rather than assumption.
- 💡 **Proactive resurfacing:** non-disruptive reminders/context suggestions only after direct usage demonstrates value.
- 💡 **Performance/index optimization:** optimize from measurements, not anticipated scale.

## Roadmap rule

This file records **current status and intended sequencing**, not every implementation detail. When a phase completes, update the status here and leave its detailed contract/evidence in the phase document, ADR, tests, and benchmark records. Do not duplicate those historical narratives back into the roadmap.


**F14/F27 real Core per-fact acceptance (2026-10-10, isolated
opt-in contract, NOT runtime-enabled):** After confirming all four
earlier full-message GPT-5.6 Core requests escalated, Core now
constructs exact-source-proven individual tasks from the validated
GPT-6 Router v3 candidates and separately trusted Temporal date:
F14 → 1 task, F27 → 2 ordered tasks. **All three real GPT-5.6 Luna/low
responses returned PLAN**, correctly targeted to the past
`calendar_day` with Eric/Luis as existing Person identities.
The original full message is retained out-of-band for Core safety
but is no longer passed as one all-or-nothing model planning task.
The F27 one-fact plans are safely joined by a Core-owned mechanical
same-Day merger (no invented identity/date/fact) and the **full
original candidate-to-fact/pending coverage guard passes**. Frozen
real provider JSON is in
`benchmarks/fact_candidate_core_live/results/*--F14--candidate-1.json`
and `*--F27--candidate-{1,2}.json`. Offline isolated canonical
Markdown E2E physically verifies 1/2 past facts, durable `él`
pending, `Con Luis` follow-up and no Day duplication. Observed
cumulative focused live GPT-6 Router/GPT-5.6 Core estimated spend
is **USD 0.0259652**, under the user's existing USD 0.07
authorization (not an invoice). **The opt-in path has not been
connected to production/DEV runtime; the other 23 Router cases,
general cross-clause dependencies and broader release gate remain.**


**Remaining 23 real GPT-6 Router design cases evaluated (2026-10-10):**
The untouched Router v3 prompt was run once each against all 23
additional original synthetic source scenarios. Every response completed
and passed source-evidence JSON validation; 22 of 23 returned the
expected number of separate candidate facts. However, **F19**
(self-correction) wrongly emits both the cancelled park plan and its
replacement, **F20** (rain conditions) wrongly uses unconditional
`occurrence` kinds, and **F25** (house needs roof repair) wrongly
creates a `task` interpretation from a descriptive maintenance need.
These are unsafe to promote to Core writes. Confirm inherited same
time in F08, pronoun bindings in F13 and F26, and incomplete object
inheritance in F23 before enabling the generic Core flow. F06, F16,
F24 and F13's `purchase_item` / `occurrence` differences may be
valid alternative classifications; do not equate every fixture
difference with a failure. The complete reviewed table and original
real responses are under
`benchmarks/fact_candidate_v2_live/README.md`,
`review_remaining_20261010.json` and `remaining_results/`.
23 added Router calls cost ~USD **0.00777** estimated at pinned
standard rates; total focused testing cost ~USD **0.0337352**
estimated (not billed) against the explicit USD **0.07** ceiling.
No Core live calls, DEV/PROD activation, canonical Markdown writes or
model migration occurred in this gate. Keep PR #152 draft; fix
F19/F20/F25 in general source-only prompt/contract, then separately
validate Core/Temporal relationships for the reviewed concerns.


**Block 4B33 local-first dependent write concurrency (2026-10-11):**
A **Core-owned opt-in stable logical operation admission** now
exists in `candidate_dependency_admission.py`. The outer client
must pass one stable, authenticated/actor-root-scoped message ID
**unchanged across retries**; the Core-generated technical request
ID may differ without admitting a duplicate. A root-local
`flock` lock spans both normal Core actions, authoritative
Markdown readback and an atomic/fsynced non-knowledge journal record.
Only digests + ID + status are stored outside the vault. Tests show
two threads and two OS processes cannot concurrently admit the
same logical operation, and an abrupt process death leaves a durable
reservation that blocks unsafe automatic replay. An injected
failure of the second original-source fact leaves state `partial`
and even another technical request ID cannot rewrite the first
fact; same message text with two distinct intentional message
IDs is not conflated.

This is still an **experimental Core facade**, not connected to
the normal app/chat dispatcher, and does not replace the
existing Core planner, identity/write/coverage guards. Core GPT-5.6
remains unchanged. No rollback or automatic resume is claimed.
To prepare a DEV activation, the existing runtime must reliably
deliver the durable per-message stable key from the authenticated
outer boundary, configure its isolated state directory, and
ensure all relevant dependent writes cooperate with the root
admission lock. A caller using a *different* key to retry the
same logical message remains unsafe. Failure after Note creation
but before the first marker requires manual recovery. Neither
F19/F20 prompt semantics nor complete generalized candidate
routing are solved by this block.


**Block 4B35 — experimental full Router/Temporal/Core semantic
assembly (2026-10-11, still private):** Real source-adapter
`OpenAIFactCandidateRouter` v3 validates original source roles
and dependencies; existing `OpenAITemporalInterpreter` reads
the FULL original message only when required; existing
`bind_temporal_to_fact_candidates` source-proves each date
or time before providing per-unit
`DomainInterpretation` evidence to the unchanged
GPT-5.6-low `OpenAILunaExperimentalPlanner`. Two separately
validated Core `RequestPlan` objects enter the already tested
original-source global coverage and durable local-operation
admission. The private chat preview returns the original outer
message ID; full F23/F26 Markdown readback and restart replay
succeed with frozen REAL Router+Core provider replies via
fake SDK clients. **F26 Temporal model response remains a
deterministic synthetic exact-date fixture, not a genuine paid
provider reading in this evaluation.**

All candidate dates/time scopes are now checked **before any
Core planning call** so a missing second relative date does not
consume a first Core provider request or allow a partial
planning state. F19/F20 correction/condition cases, inaccurate
original Router provenance, unsupported or nonexact dates,
and Core escalation all abstain before granting Core write
authority. No extra provider calls occurred.

The private preview now explicitly rejects an authenticated
multiuser actor/external principal until the runtime has a
verified per-actor canonical vault selector. Two isolated
local instances may reuse the same outer client request ID
without sharing the durable journal or knowledge root.
On partial previous writes the private chat preview refuses
**before any model call** to plan the same request again.
Normal HTTP `/execute` remains untouched, and the real
n8n/route planner is NOT configured to invoke this preview.

Before DEV adoption, review a non-default, authenticated,
actor-root-aware integration of the actual source-only
Router/Temporal/Core provider factory into the existing
runtime/n8n composition, including independent model-call
budget/telemetry, failure after creating a typed Note but
before its first fact, true per-user vault isolation,
normal chat response serialization/recovery and at least
one separately approved real provider regression covering
any material new provider contract. Never substitute this
bounded coordinated two-fact pilot for general handling of
all user free-form messages; expand from abstract invariants
and new-vocabulary negative tests, not F23/F26
word-specific rules.


**Fact interpretation refactor status (2026-10-11, Draft PR #152):**
Retired the experimental exactly-two-facts runtime/Core attestation
branch, keeping its frozen real-model evidence and historically
scoped benchmark tests. The replacement is a **read-only full-source
Router → independent Temporal → ordinary Core planner** handoff
that supports the existing bounded variable candidate collection,
backward role provenance, and arbitrary Core action/fact cardinality.
It does not alter the production planner, provider prompts or Notes.
Actual normal Core Markdown persistence has been mechanically tested
with 1/3/5/8/13 synthetic facts and real source coverage/readback.

**Not complete:** Generic Core-owned semantic source-to-plan attribution
is still needed for many-to-one and one-to-many mappings, shared
subjects, references and conditional/corrective statements, without
phrase-specific validators. The existing opt-in source coverage
preflight remains conservative and does not certify these cases,
so the new generic adapter is NOT a write-enabled chat path. Before
DEV, require comprehensive candidate/plan/readback correctness on
novel 1/3/5+ fact messages, explicit ambiguous/pending accounting,
focused live GPT-5.6 Core regression evidence, and independent
architecture/PR review. No PROD changes, no Core model switch.


## 2026-10-13 — Hybrid Core source/context/renderer verification (feature branch only)

**Latest measured strict physical acceptance: 18/27**, independently grounded
against the same versioned 13-note fake vault. Set:
F03 F04 F05 F06 F07 F08 F10 F11 F12 F13 F15 F16 F17 F19 F20 F21
F23 F24. This is an increase of eight accepted cases over the previous
10/27 2026-10-12 checkpoint; it does **not** rewrite or relabel historical
live receipts. F13 now has a clean genuine-model Markdown capture (no
orphan leading punctuation).

- General Core hybrid Planner interpretation: keep every event in its
  own fact, inherit only unambiguous source-shared verbs and dates; copy
  typed Temporal source_text/value pairs exactly, with a conservative
  data-preserving renderer for duplicated time phrases and extra
  source-fragment punctuation.
- Core's independent source/fact reviewer now sees read-only validated
  Temporal interpretations for each source group, separate from candidate
  hints and proposed targets. Passing reviewer suggestions never grants
  mutation authority; existing Core source, canonical-identity, writer and
  readback checks continue to run independently.
- Bounded **canonical name hints**: Core supplies only existing, valid
  NoteSchema-v3 note names with exact source-role matches and unique
  canonical identities. It never invents a self-Person, family members,
  or resolves ambiguous pronouns from a name hint. Current experimental
  implementation scans at most 5000 canonical Notes and returns at most
  16 names; indexing this read-only lookup is a **performance follow-up**.
- Source-proven clock co-reference such as a second event 'at the same
  time' is Temporal evidence, not a person-identity pronoun. Core validates
  the original exact source spans, Temporal day/clock owners, individual
  participant roles, unique non-mutating canonical reference helpers and
  exact final per-fact clock/date readback. It also recognizes one
  Core action with multiple independent single-reference units rather
  than requiring precisely two total units.
- Mixed property and occurrence facts targeted at the same canonical
  Note (for example, a present state followed by a future event) are
  reviewed per source/fact edge without loosening whole-plan checks.
- The NoteSchema v3 canonical types were checked against fixture Notes:
  `concept`, `project`, `document`, `person`, `calendar_day`,
  and legacy non-writable `journal_entry`; Tasks is provided by a
  separately registered app-specific schema extension. No fictitious
  core `relationship` Note type was introduced.

**Genuine full-model outputs captured:** F07 in
`hybrid_semantic_live_v4`; F10/F12 in `v6`; F13 in `v2`;
F15 in `v5`. For the final F05 and F08 facts, the authentic
previous Router, Temporal and Core Planner responses from `v7` were
replayed with **two fresh actual GPT-5.6 independent reviewer calls**;
the final four authentic results and exact canonical Markdown appear in
`hybrid_core_review_v1/`. They were not synthesized and the reviewer
saw the finalized fact wording. F24 uses the genuine original `v6`
four-model replies, now successfully replayed through the corrected
general mixed-fact coverage gate. The F08 *synthetic-reviewer* negative
tests are explicitly labeled artificial and are NOT counted as a live
provider acceptance.

Exact final examples:
- F05: two separate canonical Day facts:
  'Cenaremos con [[Ana|Ana]] en Toulouse.' on 2026-10-09 and
  '10:00 — Cenaremos con [[Luis|Luis]] en Albi.' on 2026-10-10.
- F08: one Day containing '10:00 — [[Marta|Marta]] irá al médico.'
  and '10:00 — [[Luis|Luis]] irá al dentista.' on 2026-10-05.
- F10: 'Marta y [[Luis|Luis]] se conocieron en Lyon.' in Marta.md.
- F12: Bea and literal collective 'mis hijos' both cleaned the garage
  and then assembled furniture, in two independent facts in Bea.md.
- F15: all three independent actions written, no unproved family links;
  Bea's canonical Note gets a verified Day link; Day stores literal
  'mis hijos' and 'yo' actions.
- F24: present car-at-workshop state and future service on the canonical
  concept Note, with a valid Day link and two physical fact receipts.
- F13: conversation with Eric, future cinema with Core-proven antecedent,
  and independent clean bread fact in three correct Day Notes.

**Still not accepted**: F01 family-group event ownership, F02
approximate/shared time and ellipsis, F09 semantic duplicate, F14 true
ambiguous pronoun after two people (safe partial, not erroneous guessing),
F18 negative/positive scope, F22 three-Task lifecycle coverage, F25
house repair-need vs mandatory Task confusion, F26 cross-route document
object pronoun, F27 Router source dependency and ambiguous pronoun.
These are not marked passed just because the writer returned COMPLETED
or the graph produced a plausible result. A strict count is not the
sole product acceptance gate.

**Safety and budget:** No DEV/PROD/n8n deployment or real user Note
mutation. No migration of Core GPT-5.6 to GPT-6. Provider calls
were explicitly capped; cumulative estimate **USD 0.59769438 / 1.00**
approved (NOT a billing receipt). All local tests use fake, fresh
canonical Markdown; frozen outputs remain intact. Compare against
ten historical suite failures without relaxing their snapshots.


## 2026-10-13 — Generality/approximation validation checkpoint (later than 18/27)

**23/27 accepted on isolated genuine-model outputs and physical Markdown**
after F01 and F02 reached all four model/reviewer gates and Canonical Writer.
This supersedes the earlier 18/27 count, without altering earlier receipts.
F01 uses genuine v5 Router/Temporal/Planner responses and a fresh genuine
GPT-5.6 independent reviewer, frozen under hybrid_core_review_v3; its
three events now retain all originally inherited family-participant text
and source-verified time/date, without guessed family-member Notes. F02
uses original genuine Router/Temporal/Planner replies, with a fresh genuine
independent review, frozen under hybrid_core_review_v4, yielding three
separate Day facts. The approximate phrase 'sobre las 16h' remains LITERAL
and is NOT recorded as a 16:00 exact instant; unrelated Sunday 11:00
remains a certified exact clock.

The fixed-form Spanish two-contact checker was removed from the **hybrid**
execution path (its source file survives only as historical non-hybrid
compatibility). Hybrid coverage relies on source-owned participant spans,
inherited source roles, unique Core helper mappings, independent reviewer
and canonical readback, regardless of how many participants or source
facts share an interpretation group. The reviewer source_quote is now
checked against an exact original source slice enclosing a real Router
anchor instead of comparing only literal equal strings. A same-Day
date-only typed reference is redundant with the selected Day target;
only that redundant fragment is discarded before the normal compiler,
preserving the real clock and all event wording.

The independent approximate-time adapter requires a unique exact-match
Router time_approx span and a genuine Temporal UNSPECIFIED result for the
same source. It allows other exact Temporal mentions to be transferred
and reused without converting the approximate mention into an exact
calendar coordinate. Core's deterministic coverage requires that
approximate wording appear literally in its owning fact. Prompt
instructions explain the distinction, but no prompt can bypass these
validators. The new no-provider tests replay genuine F01/F02 Markdown
and attempt adversarial missing/wrong approximate evidence.

**Still not accepted**: F09 (redundant existing information; a technically
COMPLETED duplicate cannot count as product-quality success), F14/F27
(genuinely ambiguous 'él' after mentioning two people; the safe partial
behavior MUST remain), F22 (three Task Notes exist but the middle Task
does not link to the known canonical Luis Note). Avoid per-example
code, falsely reporting safe partials as full understanding, or special
caps on number of Notes. The old read-only canonical hint scanner has a
5000-Note performance cap; replace it with indexed bounded retrieval
before relying on this feature for large vaults. This is explicitly NOT
a limit on user knowledge storage.

**Cumulative estimated provider experiment cost: USD 0.64794381/1.00**
authorized. Not a billing ledger. No DEV, PROD, Notes or infrastructure
deployment in this checkpoint. Source repo only.

Future opportunistic Clean Architecture direction is documented in
clean-architecture-incremental-direction.md and AGENTS.md; no rewrite
is planned now. Working precedence: complete general hybrid gates and
give the user a testable DEV build before refactoring architecture.


## 2026-10-13 — Auditoria general y F22 completo (24/27)

F22 ya finaliza con tres Task Notes reales en boveda de pruebas, enlaces
canonicos Ana/Luis y fechas 04/10, 04/10, 05/10. F14/F27 conservan
correctamente hechos previos y dejan el pronombre ambiguo pendiente.
F09 continua con duplicacion semantica pese a corregir la concordancia
verbal: pendiente contrato Core de hecho ya representado y readback.
La auditoria por llamadas efectivas a los validadores y sus contratos
activos/historicos esta en hybrid-source-validator-audit-20261013.md.
Eliminadas restricciones arbitrarias 4 referencias / 6 eventos y
conjunciones espanolas como garantia. No DEV/PROD. Clean Architecture
sigue diferida e incremental.


## 2026-10-13 — Later checkpoint: 25/27 completed and two safe pending

The earlier 24/27 count is now historical. F09 writes only the new
property in Luis; two genuinely independent GPT-5.6 verifier calls
recognize Marta as ALREADY_KNOWN without modifying her Note. Proof
is current-note-guarded, can be invalidated by changes and is checked
again on readback. No rule for particular person, city or verb.

F14 and F27 have true ambiguous pronouns and therefore cannot safely
be reported as 27/27 *resolved*. Core keeps the previously written
conversation facts and now stores the exact dependent cinema clause
as durable v2 source pending, with original captured time and unique
Core-verified Eric/Luis options. A later explicit reply like "Con Luis"
records the selected identity and uses the existing freshness-checked
Core continuation guard to write only the cinema event; both genuine
provider-replay and deterministic continuation tests are present.
No automatic person guessing and no old-fact re-execution.

These feature-branch hooks still require wiring into the authenticated
DEV application. No DEV or PROD activation has happened.
