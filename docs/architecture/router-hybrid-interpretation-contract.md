# Contrato de interpretación híbrida Router → Temporal → Core → Writer

**DECISIÓN DEL USUARIO: arquitectura objetivo APROBADA el 12-10-2026.**
**ESTADO DE IMPLEMENTACIÓN: componentes opt-in en rama experimental; NO activada en DEV ni PROD.**
Este es el ÚNICO contrato normativo objetivo para este flujo. Sustituye la
obligación del 11-10-2026 de enviar a Core cada candidato atómico por separado.
Los documentos antiguos describen implementaciones o pruebas históricas,
pero no son instrucciones alternativas a este contrato.

## Regla principal

**Separar hechos no equivale a separar llamadas al modelo.** Router recibe
el mensaje original íntegro una vez e identifica candidatos semánticos atómicos
con roles, polaridad, modalidad, posiciones de texto y dependencias verificables.
El agrupador forma unidades de INTERPRETACIÓN compuestas por candidatos
semánticamente interdependientes; Core puede producir múltiples hechos/notas
independientes a partir de UN grupo. El grupo nunca se convierte en un hecho
fusionado o una escritura conjunta obligatoria.

Un grupo puede incluir toda la entrada original SI TODOS sus candidatos están
relacionados. Nunca incluir un hermano independiente solo porque comparta un
sujeto, fecha, verbo o tramo de texto. La proximidad no demuestra dependencia.

Original → Router (candidatos atómicos) → agrupador local (grupos coherentes)
  → Temporal solo si hay fechas/horas → Planner ordinario de Core por grupo
  → revisor independiente de cobertura candidato↔hecho → validación Core
  → Writer / Markdown / auditoría por hecho

## Contratos por componente

1. **Router** solo propone segmentación y dependencias lingüísticas con
   evidencia exacta en el mensaje original. No infiere identidad canónica,
   tipo de nota, resultado ISO, hechos finales, acciones o permisos de escritura.
   Conservar negaciones, condiciones, rectificaciones y ambigüedad.
2. **Agrupador** mantiene el texto original exacto de cada grupo, sus límites,
   todos los candidatos originales y sus posiciones verificadas, sin fabricar
   frases. Divide intenciones comprensibles independientemente (F06, F22) y
   reúne contextos imbricados (F04, F16, F23). Contabiliza TODO el mensaje
   y no duplica una acción independiente entre grupos. El mensaje completo
   queda disponible únicamente como procedencia/auditoría si contiene grupos
   independientes; NO se reenvía a Core como otra solicitud de planificación.
3. **Temporal** interpreta cada grupo con contenido temporal y devuelve
   evidencia tipada atribuible a CADA candidato/evento: fecha compartida,
   varias horas, varios días, orden y condiciones. Sin convertir por intuición
   rangos, aproximaciones, horas sin anclaje o tiempos cancelados en fechas
   exactas. Un grupo sin datos temporales omite Temporal.
4. **Core Planner** recibe el texto íntegro DE SU GRUPO, no una proposición
   atómica aislada por defecto ni hermanos independientes. Core mantiene
   autoridad exclusiva sobre semántica, referencia, sujeto, destino canónico,
   selección, hechos y acciones; puede planificar 0..N hechos y notas.
   Sigue GPT-5.6 hasta la migración aparte ya aplazada.
5. **Revisor Core + validadores** exigen contabilidad explícita de CADA
   candidato y CADA hecho planificado. La relación candidatos→hechos es N:M,
   sin convertir ordinales de Router en ordinales de escritura. Se puede
   justificar un sujeto, predicado o condición compartido DENTRO del grupo
   sin exigir una escritura previa, pero nunca copiar identidad no verificada.
   Validar por hecho destino, fecha/hora, polaridad, modalidad, corrección y
   alcance. Una propuesta del revisor no es autorización de escritura.
6. **Writer** conserva preflight canónico, identidad, permisos, estabilidad
   de Markdown, marcas request/fact, idempotencia y readback físico.
   Varios hechos del grupo pueden terminar en notas distintas.
   Los hechos seguros pueden completar y otros quedar pendientes SOLO cuando
   los contratos actuales garantizan esa separación. Si no, bloquear el
   grupo que no pueda separarse de forma segura. No prometer rollback
   transaccional global ni declarar completado lo que se omitió.
7. **Entre grupos** mantener carriers temporales, referencias canónicas y
   pruebas de eventos previos derivados de Core/Markdown; comprobar vigencia
   antes de escribir. Dentro de un grupo se interpreta conjuntamente el
   texto original, sin que cada hecho dependa de persistir el anterior.
   La referencia ambigua permanece sin resolver; otro grupo independiente
   puede completarse. No crear un Planner alternativo en Router o Temporal.

## Ejemplos y controles

- F03: parque + cine con mis hijos juntos; dos actividades, misma fecha;
  la identidad del grupo permanece pendiente si Core no puede acreditarla.
- F04: parque 12:00 + cine 18:00 juntos; dos hechos y horas separadas.
- F16: Ana compró entradas + Luis también juntos; dos compras, dos personas.
- F21: clase lunes y miércoles a las 18h juntos; dos días y una hora
  compartida; no inventar las horas que Temporal no pueda autorizar.
- F23: dos fallos en Odyssey juntos; dos propiedades de un proyecto;
  «Temporal» como componente no es una expresión de fecha.
- F06: vio a Ana / compró pan en grupos separados aunque compartan «hoy».
- F13: conversación con Eric y cine con «él» pueden agruparse solo con
  antecedente inequívoco; comprar pan aparte.
- F14/F27: «él» tras Eric y Luis sigue ambiguo, nunca escoger al azar.
- F19: corrección agrupada; no guardar el plan sustituido.
- F20: alternativas de lluvia agrupadas; no tratarlas como sucesos ocurridos.
- F22: tres tareas independientes, tres grupos.

## Cinco pruebas con modelos reales: 12-10-2026

Se reutilizaron las respuestas auténticas de Router GPT-6. Temporal GPT-6
cuando procedía; Core Planner y revisor independiente GPT-5.6 auténticos.
Todas las escrituras se intentaron SOLO sobre 13 notas Markdown ficticias.

| Caso | Estado real | Observación |
| --- | --- | --- |
| F04 | COMPLETED | dos horas correctas; dos readbacks verificados |
| F16 | COMPLETED | Ana y Luis, dos destinos canónicos; dos readbacks |
| F03 | NEEDS_ATTENTION | Core planteó dos actividades; revisor declaró ambigua identidad «mis hijos» |
| F23 | NEEDS_ATTENTION | Core planteó dos fallos, revisor los relacionó; validador actual bloqueó referencias múltiples |
| F21 | BLOQUEO TEMPORAL | lunes y miércoles reconocidos; «a las 18h» quedó UNSPECIFIED; Core no se ejecutó |

Resultado exacto: 2/5 completas, 2 pendientes en Core, 1 detenida en
Temporal. Es evidencia para escoger el diseño, NO validación de implementación
general. Coste adicional estimado: 0,0135635 USD; acumulado 0,2789394 de
0,50 USD autorizados (estimación, no extracto de facturación).
Pruebas aisladas históricas: ruta local externa
/home/ragdehl/projects/odyssey-experimental-receipts/hybrid-probe050/
Este resumen documental es independiente de que esa ruta siga existiendo.

## Implementación: compilador híbrido opt-in (primer bloque aislado)

**CÓDIGO IMPLEMENTADO en esta rama de experimento, NO desplegado en DEV/PROD:**

- `odyssey_runtime/hybrid_group_compiler.py`: reutiliza Router v1,
  las posiciones y roles existentes, la validación de fuente original y
  los contratos `CandidateRouteBundle`. Agrupa dependencias semánticas
  explícitas, preservando todos los candidatos independientes por ID.
- `execute_candidate_routed_message(..., bundle_compiler=...)`: habilita
  exclusivamente por selección explícita el agrupador híbrido, con el
  **mismo** Temporal/Core/revisor/Writer existente. Sin esta opción, el
  compilador atómico anterior sigue siendo el predeterminado. No se ha
  activado ninguna ruta nueva en DEV/PROD.
- Se reforzó el validador compartido de procedencia: los límites exactos
  de cada ruta/grupo deben reproducir la partición original; no basta con
  que el texto de una ruta aislada coincida. Los resultados históricos
  mantienen su propio compilador y se revalidan sin reinterpretarlos.
- Con los 26 resultados antiguos estructuralmente compilables de Router:
  **53 rutas atómicas → 37 grupos conservadores** (reducción del 30,2 %
  en unidades de interpretación potenciales; NO medición de ahorro real).
  F27 sigue rechazado por dependencia incoherente; no se repara a ciegas.
- Se han reproducido sin nuevas llamadas de pago las cinco respuestas
  **auténticas** anteriores de Temporal/Core, ahora entrando por el nuevo
  agrupador: **F04 y F16 completan** con notas ficticias verificadas;
  F03/F23 siguen pendientes por validadores canónicos y F21 mantiene el
  bloqueo Temporal. Las salidas originales se han congelado como fixtures
  bajo `benchmarks/application_router/hybrid_grouped_v1/`.
  F06 demuestra además que si el primer hecho independiente queda pendiente,
  la segunda compra puede persistir sin copiar al actor anterior.
- La suite de regresiones en el repositorio es obligatoria antes del
  merge. Ningún cambio de prompt ni modelo se ha producido en esta etapa.

**ACTUALIZACIÓN POSTERIOR (2026-10-12): F03/F21/F23 implementados y
validados en la rama experimental, NO desplegados.** La descripción de los
cinco resultados fallidos/parciales arriba es la PRIMERA prueba, y sigue
siendo evidencia histórica. Después, nuevas llamadas reales al modelo,
revisiones independientes de Core y readback físico en vault ficticio han
confirmado las tres correcciones en sus formulaciones positivas:

- **F03**: `odyssey_core/candidate_group_participants.py` conserva la
  descripción colectiva literal `mis hijos` en AMBOS hechos, sin inventar
  personas, identidades ni enlaces; exige que la participación y cada acción
  estén justificadas en los roles originales. Si la pertenencia del grupo
  completo se puede demostrar canónicamente en otro caso, la ruta normal de
  Core seguirá siendo la autoridad para el enlace; este piloto no lo afirma.
- **F21**: `odyssey_core/temporal_group_composition.py` compone un reloj
  postpuesto explícito con dos fechas EXACT_DATE ya verificadas por Temporal,
  tras comprobar roles compartidos, día de la semana, rango, zona y DST.
  `candidate_grouped_temporal.py` verifica por separado que cada Core Note
  de día coincida con su fecha/instante y que la frase no invente palabras.
  El Planner emplea los segmentos originales de Temporal; nunca fabrica
  `el lunes a las 18h` concatenando dos textos no adyacentes.
- **F23**: `odyssey_core/candidate_grouped_property.py` atribuye dos
  propiedades afirmativas distintas a UN sujeto explícito/verificado.
  Cuando `Router` y `Temporal` sean nombres de componentes sin identidad
  segura, Core guarda los textos LITERALES; no fuerza enlaces, ni crea notas.
- Se conserva el **control antiguo** para contextos no híbridos;
  `context.scoped_route_source` y la prueba tipada de Temporal restringen
  las nuevas validaciones y no convierten las rutas atómicas en grupos.
- Respuestas auténticas positivas, sin claves ni notas personales,
  congeladas en `benchmarks/application_router/hybrid_grouped_v2/`.
  Pruebas de ejecución/revisión/escritura reproducidas sin nuevas llamadas
  de pago en `tests/runtime/test_hybrid_repaired_real_provider_replay.py`.
  Coste total estimado de todos los experimentos hasta esta etapa:
  **USD 0.2951979 de USD 0.50 autorizados**. No equivale a factura de API.

**SIGUIENTES BLOQUES, TODAVÍA NO IMPLEMENTADOS:**

1. Ampliar y contrastar semántica multihecho general (N:M, negaciones,
   condiciones/correcciones, tareas, identidades singulares/plurales,
   estados parciales y pronombres ambiguos F14/F27), con todos los mensajes
   originales y pruebas adversariales ajenas a los casos del piloto.
2. Repetir los gates de regresión y calidad con variaciones reales acotadas,
   preservar la suite histórica y medir precisión, gasto y latencia.
3. Pedir aprobación separada antes de activar la ruta híbrida en DEV y luego
   en PROD. GPT-5.6 Core se conserva durante esta fase.

## Precedencia / documentación histórica

AGENTS.md y functional-roadmap.md apuntan a este contrato como objetivo.
router-unit-dispatch-contract.md (11-10-2026), router-fact-units-v1.md,
router-scope-27-live-regression-20261011.md y application-boundary-router-v0.md
son evidencia de diseños, prototipos y comportamiento legado, NO políticas
competidoras. No borrar fixtures, afirmaciones históricas de fallos/éxitos,
ni enunciados que documenten cómo funciona el v0 todavía activo.


## Auditoría documental y precedencia

Para el inventario de contradicciones corregidas, orden de lectura
entre chats, separación entre OBJETIVO/IMPLEMENTADO/DESPLEGADO y regla
de prevención, consultar la
[auditoría de coherencia 2026-10-12](router-hybrid-documentation-audit-20261012.md).
El registro es documentación de esta decisión, no otra autoridad normativa.


## 2026-10-12: Sensitive-scope source regression checkpoint (NOT a functional release)

The approved hybrid grouping is unchanged. Five fresh real-provider probes
were run on disposable canonical Notes with the previously saved authentic
Router GPT-6 source proposals. **Results are fail-closed evidence, not five
successful semantic writes:**

| Case | Fresh model result | Safe physical result |
| --- | --- | --- |
| F17, common negation of Ana and Luis | Core proposed one joint negative fact; independent reviewer could not authorize specialized negative coverage | NEEDS_ATTENTION, 0 writes |
| F19, cancelled park then cinema correction | Core attempted unsupported temporal wording/evidence; date-scoped planner validation rejected before reviewer | FAILED, 0 writes; do not save the cancelled park |
| F20, mutually exclusive Saturday alternatives | Core proposed a combined condition with an unsafe personal destination; reviewer declined | NEEDS_ATTENTION, 0 writes; not two confirmed occurrences |
| F18, no Ana / yes Luis | Two independent groups, each Core/reviewer declined unproven person binding; second group must not guess previous date/actor | NEEDS_ATTENTION, 0 writes |
| F22, three independent task intents | Core declined first two, historically stored the third "preparar la factura" as a Day fact | PARTIAL in **original provider receipt**, one Day write which is **not a Task** |

A corrective opt-in hybrid guard has now been added:
`CoreCandidateContext.hybrid_interpretation_mode` is marked **only** by the
hybrid source compiler. The Core candidate coverage gate blocks all ordinary
`WriteAction`s involving `task` candidates in this mode until a reviewed
specialized Task lifecycle contract exists. Hence replaying the unchanged F22
authentic model outputs with the new guard must produce **no false completed
Tasks or Day facts**. F25 (house repair need) is similarly prevented from
being silently promoted to a Task. Older atomic contexts are untouched.

Real provider outputs in
`benchmarks/application_router/hybrid_sensitive_v1/F17.json`,
`F18.json`, `F19.json`, `F20.json`, `F22.json` remain immutable,
with the historical captured statuses preserved (do not relabel F22's actual
original partial outcome). Regression tests in
`tests/runtime/test_hybrid_sensitive_boundaries.py` and
`tests/runtime/test_hybrid_multi_route_sensitive_replay.py` check
source-group coverage, sensitive-write refusal, F14 ambiguity, F27 invalid
dependencies, independent Task scopes, replay of real model outputs, and
forbidden generic Day writes. No user Notes, DEV/PROD, model versions,
Task schema or plugin/app internals were changed.

Current cumulative **estimated** provider spend after these probes was
**USD 0.3193113 out of the approved USD 0.50**. Do not count as official
billing. No additional model calls are required to replay these results.

**Next technical work:** establish a distinct reviewed Core semantics for
negative/hypothetical/corrected plans (the resulting Note content must
explicitly preserve modality and polarity), plus actual specialized
Tasks ownership with completion state and date/modality inheritance.
An unsafe broad exception in the ordinary fact coverage validator is
not an acceptable way to make these tests green. Continue F14/F27
source/identity gates and test an independent negative-plus-positive
case before considering DEV/PROD promotion.


## 2026-10-12: Corrected future plan and Tasks app delegation (opt-in only)

A **later implementation checkpoint** supersedes the earlier F19 "failed"
status for the new code path, while preserving that earlier genuine model
observation as history. DEV and PROD remain unmodified.

**F19 - Source-grounded rectification.** The narrow Core validator in
odyssey_core/candidate_corrected_plan.py requires an arbitrary-length,
source-grounded **linear** sequence: the first candidate owns explicit date,
predicate and polarity; every successor has its own object/time, an exact
`replacement` span for the immediately preceding object, and immediate typed
predicate/date inheritance. It rejects skips, forks, cycles, reused exact source spans for objects/clocks,
conditions, modalities and mixed polarity rather
than guessing a chain. Temporal must certify the final exact date/clock; the
final fact excludes every discarded unique object/clock. The independent
GPT-5.6 Core attribution reviewer must mark the old action unsupported
and map **only** the final action to one factual write; every ancestor becomes
`superseded_by_correction` only after that complete graph is independently
validated. Only after the full
source, actor, target and temporal checks pass may Core classify the
ancestors as "superseded_by_correction", which is an accounted-for non-write
rather than outstanding work. The Writer writes one future intention to its
canonical Day, never a cancelled object or clock. A fake "superseded" claim
without the reviewed final fact and physical readback fails closed. The
stored historical model attempts and the now-successful authentic
GPT-6/GPT-5.6 replay are frozen in
benchmarks/application_router/hybrid_correction_v1/F19.json.

This generalizes only structural source evidence, tested deterministically at
2/3/5/9 candidates and with a synthetic three-step Markdown readback. It is
not a claim that Router can recognize arbitrary correction grammar, that a
new model prompt was evaluated, or that negation/conditional semantics beyond
this exact linear final-intention shape are supported.

**F22 - Tasks app reuse.** An explicit enable_tasks=True switch on the
existing hybrid compiler routes only PURE Task groups to the registered
Tasks application, not to generic Core. The scoped route executor needs
a separately injected trusted Tasks executor; absent registration there
is no fallback to ordinary Calendar-Day writes. The existing Tasks-owned
TaskCorePlanner, TaskLifecycleGuard(CREATE), Tasks schema and ordinary
Core Writer created a real canonical Task Note with state pending and a
target date in a disposable deterministic end-to-end test. Its other
two F22 routes remained pending; a real live Tasks interpreter was NOT
tested in that path. Mixed property/repair descriptions such as F25
are not automatic Task creations. The old default source compiler is
unchanged and all previous authentic outputs remain frozen.

Estimated cumulative experimental provider spend:
**USD 0.3263055 / USD 0.50** (estimate, not an official invoice).
No personal Notes, n8n, DEV, PROD or model versions were changed.

**Open work:** F17/F18 negative statements and canonical singular
identity links, F20 conditional branches, more complete F22 shared
date/modal semantics through live Tasks interpretation, F14/F27
ambiguities and broad 27-case N:M regression quality. These must not be
described as functional successes merely because unsafe writes are
blocked. Promotion to DEV and PROD remains separately gated.

### Auditoría de cardinalidades acotadas (2026-10-12)

El literal sensible de Day ya usa el presupuesto técnico ordinario de Core
(candidatos, bytes, claims y hechos) y una revisión N:M, no un número de
cláusulas. Mantiene un único hecho literal idéntico a la fuente, sin enlaces ni
afirmación de ocurrencias, y exige evidencia Temporal para el único Day.

Dos límites siguen cerrados deliberadamente:

- `candidate_corrected_plan.py` modela una rectificación binaria: una acción
  descartada y una sustitución final. Generalizarla a cadenas o bifurcaciones
  requeriría un contrato explícito de alcance, precedencia y contabilidad de
  cada acción sustituida; no basta relajar `len(...)=2`.
- El adaptador histórico `validate_candidate_attribution` mantiene su propuesta
  1:1 para compatibilidad con sus pruebas de referencias. El camino híbrido
  usa el revisor de grafo N:M y después el validador de cobertura canónico. No
  se debe convertir el adaptador legado en permisivo sin una revisión separada
  de sus helpers de identidad y readback.

## Actualizacion posterior 2026-10-12: correcciones y Tasks (solo rama experimental)

F19 ya tiene un contrato de Core delimitado: ante una rectificacion
explicita del plan futuro, Temporal demuestra la fecha y la hora de la
alternativa final, y el revisor independiente vincula solo esa alternativa
a un hecho. El antecedente descartado se marca internamente como
`superseded_by_correction`, nunca como un acontecimiento ocurrido ni
como una solicitud pendiente. La clasificacion solo es valida si existe
el hecho final, con actividad, destino y horario demostrados; si no,
la escritura se bloquea. La prueba de extremo a extremo con respuestas
autenticas congeladas de GPT-6 y GPT-5.6 concluye COMPLETED con una
unica escritura y readback fisico en un vault sintetico. Los tres intentos
reales historicos estan en
`benchmarks/application_router/hybrid_correction_v1/F19.json`.

En F22, `compile_hybrid_candidate_bundle(..., enable_tasks=True)`
puede enviar exclusivamente grupos puros de tareas a la capacidad
`tasks` ya registrada. El ejecutor de Tasks se inyecta de forma explicita;
si falta, no hay alternativa que guarde el contenido como fact de Day.
La integracion determinista con `TaskCorePlanner`, `TaskLifecycleGuard`
y el Writer crea una nota real de tipo task con estado pending y fecha
objetivo en el vault de prueba. Las demas rutas F22 siguen pendientes.
NO se ha ejecutado una prueba completa con modelos reales para Tasks.
F25 (propiedad de la casa y necesidad de reparacion) no se convierte
automaticamente en tarea. Por defecto, el compilador sigue desactivando
esa delegacion; DEV y PROD no cambian.

Siguen abiertos los contratos de negaciones F17/F18, condiciones F20,
el extremo a extremo real del interprete Tasks con fechas/modalidades
heredadas, y la ambiguedad F14/F27. La evidencia de F19 no los autoriza.
Presupuesto estimado acumulado: USD 0.3263055 de USD 0.50 autorizados.


## 2026-10-12: Literal shared-negation/conditional statement — independently verified

**Feature branch only, still not DEV/PROD.** Following the earlier original
F17/F20 fail-closed model attempts, an opt-in `verified_sensitive_temporal`
context was added for source-grounded candidates sharing one negative
predicate (F17) or explicit conditions (F20).
The bounded `candidate_sensitive_statement.py` checks the ENTIRE exact
original sentence, original role spans, complete N:1 candidate
coverage, a single canonical Day destination proven by Temporal, and no
canonical references, new entities, changes of polarity, dropped clauses,
extra event claims or hidden mutations. The group reviewer must attribute
**both candidates to the SAME fact**. The approved write is an
**informational literal statement**, not a completed occurrence, calendar
event or a claim that either conditional branch happened. The original
source text remains unchanged within the Day Note.

Fresh GPT-6 Temporal + GPT-5.6 Planner/independent graph-reviewer calls
for both F17 and F20 **COMPLETED** on disposable synthetic Markdown with
one physically verified source-identical statement each. Freeze and
replay from `benchmarks/application_router/hybrid_sensitive_literal_v1/`
and `tests/runtime/test_hybrid_sensitive_literal_real_replay.py`.
The old `hybrid_sensitive_v1/` NEEDS_ATTENTION receipts remain valid
historical observations. F18's separated affirmative/negative person
claims and ambiguous canonical links remain unresolved; do not promote
them by the literal group exception.

**Standalone negative literal extension (2026-10-12, provider-free):** the
same opt-in contract now accepts one or more negative candidates within the
ordinary bounded Core candidate budget. Each candidate must carry its own
exact polarity, predicate, and exactly one `object` or `participants` source
scope; the whole routed source must still be the only persisted fact, and
Temporal must prove the one Day. This covers a standalone negative participant
scope without creating a person link or an occurrence. Deterministic coverage
uses 1/3/5/9 candidates plus malformed scope/target/date/reference cases.
No Router prompt or provider output changed. An independent audit of the
ORIGINAL frozen F18 GPT-6 Router proposal established that its second
affirmative candidate already carries an exact source-anchored DATE role
pointing to `Ayer`, despite having no explicit inheritance edge.
The existing hybrid source compiler correctly retains that external role as
read-only original provenance, and ScopedTemporalHandoff authorizes its
date-only reuse after the first route's Temporal proof. No negation is
inherited. A new provider-free test using that UNMODIFIED frozen F18 proposal
shows two separately reviewed synthetic Core plans writing exact-source
`Ayer no vi a Ana` to the canonical Day as non-occurred informational
text and `Hablé con [[Luis|Luis]].` as an affirmative Day fact after
canonical person lookup, with real isolated Markdown readback. Removing
the original affirmative DATE role makes the cross-route date proof
unavailable. This is deterministic architectural acceptance, NOT fresh
GPT-5.6 Core Planner/independent reviewer model acceptance for F18.
The immutable historical real-provider F18 replay still remains pending;
new model validation is required before counting F18 as complete.

**Real Tasks model gate (F22 third route only):** an opt-in GPT-6 Tasks
interpreter selected `CREATE`, GPT-6 Temporal resolved `mañana` to
the fixture's 2026-10-05, and GPT-5.6 Core with existing TaskCorePlanner
and TaskLifecycleGuard created one actual Task Note with
`type: task`, `status: pending` and `target_date: 2026-10-05`.
The receipt `benchmarks/application_router/hybrid_tasks_v1/F22-last.json`
is reused in a provider-free three-route hybrid dispatcher replay:
**first two tasks stay pending**, third succeeds. No false Day fact,
no claim of a fully completed F22, no deployment.

**Scoped Tasks evidence bridge (2026-10-12, deterministic only):** the
experimental dispatcher now offers a closed `execute_scoped` hook for an
explicitly injected Tasks executor. It transfers only an original-source
digest, route order, exact predecessor `TemporalInterpretation` results and
source-checked modality wording. A four-argument existing executor remains
compatible for local routes, but a route requiring inherited Temporal proof
stays `NEEDS_ATTENTION`; Router wording cannot supply a date. The hook's
receipt must return the actual local Temporal interpretation before a later
route can reuse it, even if the predecessor Task itself did not persist.
Modality remains read-only wording and never selects `CREATE`, Task type, or
write authority. Deterministic synthetic-vault coverage creates three
independent pending Task Notes with two verified inherited/local dates and no
Day facts, while checking forged hash/role provenance. The current
`TaskInterpretation` provider contract has no field by which a live model
selects an inherited temporal role, so this is not fresh three-route provider
acceptance. That model-facing contract and a bounded live gate remain open;
the immutable third-route receipt is unchanged.

Accumulated **estimated** API spend at this checkpoint:
USD **0.3356791 of the 0.50 approved**. No new DEV/PROD routes, real
personal Notes, schema, or Core model migration were made.


## Verification update — 2026-10-13 (not a DEV deployment)

The normative HYBRID architecture above is unchanged: atomic candidate
source hints grouped into whole grammatical interpretation units, typed
Temporal per owned event, ordinary Core Planner, independent read-only
Core graph review and unchanged canonical Writer guards.

The latest strict accepted artificial-corpus count is **18/27**.
New Core-only bounded verified-source context and multi-event coverage
fixes have genuine GPT-6 Router/Temporal, GPT-5.6 Planner and reviewer
receipts with actual Markdown readback. Exact individual case/source
evidence, the nine still-unaccepted cases, API budget, and files
are in `docs/architecture/functional-roadmap.md`.
All code remains on the experimental feature branch; DEV/PROD and n8n
are untouched, and any activation still requires a separate gated rollout.


## 2026-10-13 — Subsequent generic-validator and approximate-time proof

The **latest measured strict corpus is 23/27** in an isolated synthetic
vault. The older counts above are historical, not competing architecture
instructions. Hybrid Core MUST NOT call the legacy two-contact literal
template; use independently reviewed source/actor/fact ownership.
Temporal may carry an unresolved time phrase only as read-only literal
evidence, source-matched to a time_approx role, and may still provide
independent exact date/time anchors. No approximate time ever becomes
an exact timestamp, and no unsupported identity is linked.

Evidence, pending four cases, technical budget, no deployment and the
incremental Clean Architecture future direction are recorded in the
canonical functional roadmap.


## E5 — Correlación explícita de una aclaración fuente v2, 30-10-2026 (solo rama fuente)

La infraestructura de pendiente **ya existía**: `CandidatePendingRepository`
guarda por actor/conversación fuente original, spans, instante con huso horario,
opciones de Core y sus guards físicos, sin crear un `RequestPlan`. La
elección se registra con `CONTINUATION_REVIEW_REQUIRED` y no escribe
ningún hecho nuevo; la validación semántica de la continuación debe seguir
separada de la elección.

La UI antigua generaba una elección textual sin el ID de su tarjeta. Tras
otra respuesta del chat, la regla de seguimiento inmediato bloqueaba esa
elección (`CANDIDATE_EXPLICIT_REQUEST_REQUIRED`), aunque el pendiente
estuviera intacto en disco. El cliente HTTP ya preveía un campo opcional
`reply_to_request_id`, pero no estaba conectado. Ahora:

- Core solo añade `source_pending: true` a sus propias tarjetas de
  pendientes fuente v2, **no a aclaraciones v1**. n8n lo proyecta
  únicamente en listas básicas verificadas y el cliente exige tipo
  booleano literal y forma compatible.
- Los botones «Elegir» y «Cancelar» de esas tarjetas envían el
  `reply_to_request_id` original. El compositor conserva intacto un
  mensaje nuevo sin marcador. n8n valida que el ID sea acotado antes
  de transmitirlo y el HTTP privado repite la validación. Un `reply_to_request_id`
  exige también ID de entrega nuevo y conversación explícita; el servidor
  **omite** el argumento opcional para llamadas antiguas sin correlación.
- El runtime reutiliza la **misma** `CandidatePendingRepository.reply`
  y sus protecciones: actor, conversación, ID exacto, respuesta nueva con
  ID propio, opciones y revisiones canónicas vigentes, hecho anterior
  verificado y replay idempotente. Un ID inexistente o de otro actor
  devuelve un control seguro, nunca cae al writer ni al router.
- **No** se activa la continuación semántica ni se vuelve a escribir la
  petición original automáticamente. La identidad seleccionada queda
  almacenada para una revisión posterior; las notas anteriores permanecen
  intactas. El guard experimental F14/F27 sigue sin generalizarse a
  peticiones arbitrarias.

Evidencia: pruebas con bóveda temporal y servidor HTTP auténtico para
selección tras un turno no correlacionado, respuesta repetida, actor ajeno,
IDs inválidos y ausencia de nuevas escrituras; contratos JS del
cliente, tarjeta y validador n8n. Son pruebas offline con datos
sintéticos, **no** aceptación navegador desplegado/Cloudflare/GPT real.


**Recuperación tras recarga, añadida en fuente:** el endpoint actor-autenticado
`conversation/main` consulta los registros v2 `open` en la raíz privada ya
existente, verifica **otra vez** los guards de todas las identidades y los
hechos previamente escritos y proyecta como máximo cuatro tarjetas con
`source_pending: true`, sin enviar fuente completa, guards ni datos de
otros perfiles. Las tarjetas usan el mismo botón correlacionado y el
frontend valida la forma del resultado antes de mostrarlo. La consulta
no crea planes ni toca Markdown. Si la lectura del estado resulta
corrupta/no verificable, no bloquea el histórico; comunica que la
recuperación requiere atención. Una identidad obsoleta no se ofrece
como opción válida. La paginación antigua del chat no repite tarjetas.

**Límites aún reales:** no se muestran todos los pendientes si existen
más de cuatro; los pendientes sin opciones canónicas actuales requieren
revisión en vez de una tarjeta; una elección ya guardada sigue esperando
una continuación semántica para convertirse en hecho. El recorrido
completo con navegador autenticado/HTTPS y la reanudación de escritura
todavía no están aceptados. Pruebas actuales con Runtime reiniciado,
bóveda sintética, HTTP privado y DOM/cliente simulado, no GPT real.
**Gate fuente del cambio:** 2.465 Python (+7 subtests), 292 JS,
Ruff/Docs Guard PASS. La seguridad de selección se vuelve a validar
cuando el usuario responde, no solo cuando se dibuja la tarjeta.

**Siguiente bloqueo funcional:** `selected_for_core_review` ya da
identidad seleccionada, fuente literal y reloj original; el guard de
continuación actual aún compara frases concretas del corpus F14/F27.
No convertir ese guard en una autorización genérica mediante búsqueda y
sustitución de pronombres. Hacen falta propuesta Core con semántica
revisada independientemente (fechas, polaridad, participantes, hechos
N:M, roles y referencias), guardas de CAS e idempotencia antes de E3,
más evaluación real acotada del prompt cuando se autorice gasto.

## E5 — integridad de replay de la aclaración correlacionada (30-10-2026)

Antes, el digest de una entrega asociaba solo el texto de respuesta y la conversación. Dos tarjetas diferentes enviadas accidentalmente con el mismo ID de entrega y el mismo texto podían intentar compartir el resultado de una elección con otro registro pendiente. El contrato de replay ahora incorpora el identificador original de la aclaración, **solo cuando está presente**, conservando exactamente el digest histórico de todas las entregas anteriores. El mismo ID con distinto pendiente se rechaza como conflicto, no se interpreta de nuevo, y una respuesta correlacionada sin almacén de pendientes configurado no puede pasar al Router o al Core legacy como una petición ordinaria.

Pruebas con dos pendientes sintéticos y reintento conflictivo; la ruta sin dependencia de aclaraciones sigue siendo compatible y conserva su digest original. Esto fortalece la seguridad de la respuesta, **no** acredita la continuación semántica del hecho pendiente. Sigue faltando una propuesta Core genérica, revisión independiente de significado/temporalidad, E3/readback con semántica revisada, prueba GPT real autorizada y aceptación en DEV.

## E5 — Handoff Core fuente-exacto tras elegir identidad (30-10-2026, solo fuente)

Se reutiliza el registro duradero v2 existente con `prepare_selected_candidate_continuation`
(`odyssey_core/candidate_continuation_context.py`). El compositor ejecuta esta
preparación después de registrar una elección, pero **no llama al Planner ni escribe
ninguna nota**. Solo admite un candidato `ambiguous_identity` seleccionado,
con las posiciones originales exactas de su fuente y referencia, identidad actual
Core `id + guard + nombre canónico`, reloj con zona horaria original y el
conjunto inmutable de marcadores físicos ya escritos. No reconvierte los hechos
anteriores en operaciones de un nuevo plan. Una solicitud con candidato pendiente
sin seleccionar, cancelada, identidad obsoleta o hechos previos alterados se
rechaza como no preparada.

`CoreCandidateContinuationContext.review_payload()` ofrece al futuro revisor
semántico una vista acotada: fuente completa original, subfrase pendiente, spans
exactos, referencia literal, nombre canónico seleccionado, tiempo original y
ordinales de hechos ya almacenados. No expone ids/guards físicos al modelo.
La estructura Core conserva por separado hashes y marcadores de origen, estado
y hechos, y `validate_selected_continuation_current` revalida todo con el
registro/vault actuales antes de que pueda existir una futura vía E3.

Este handoff **no** es un dictamen semántico y `may_execute=False`: faltan
proponer un plan que cubra toda la parte pendiente con el reloj original,
verificar independientemente que preserva polaridad, participantes, fecha,
tipo, destino y cardinalidad, aceptar solo los hechos no escritos, validar el
plan exacto y su identidad elegida y conectar E3 con recibo y readback.
No activar el guard piloto F14/F27 basado en la frase de cine como sustituto.
No se ha hecho una campaña nueva GPT ni prueba desplegada.

Pruebas offline con hechos E3/Git reales en bóveda desechable y recuperación
tras reinicio; rechazo de selección inexistente o cancelada, conversación
distinta, cambio de identidad o de hechos anteriores y tamper de fuente;
contextos en español, inglés y francés, con subfrases y referencias de tamaño
variable, pero sin afirmar semántica revisada por modelo.

## E5 — inspección de la propuesta Core antes de revisión semántica (30-10-2026; fuente)

`odyssey_core/candidate_continuation_plan.py` introduce
`inspect_selected_candidate_plan(context, plan)`, una comprobación
**read-only** de los `RequestPlan/WriteAction` tipados del Core existente.
No invoca un proveedor, no sustituye el Planner, no autoriza E3 y no cambia
el contrato público/DEV. Conserva cardinalidad variable: un único candidato
pendiente puede producir varios hechos y varios `WriteAction`, con
`plan_fact_ordinals` como autoridad de numeración de la nueva propuesta,
no con ordinales de candidatos ni de hechos ya persistidos.

La inspección rechaza recuperación/delegación mezclada, planes con
limitaciones, modificaciones de propiedades/etiquetas, creación forzada,
helpers que escribirían o no se utilizarían, y referencias al elegido que
no apunten a un helper Core read-only con su nombre canónico. Exige que
la referencia original aparezca de verdad como marcador en algún hecho
propuesto y comprueba que ningún nuevo hecho duplique **literalmente**
el digest normalizado de una anotación Core ya confirmada. Este filtro
de duplicados exactos **no** detecta paráfrasis; esa es responsabilidad del
revisor semántico. Ninguna de esas comprobaciones demuestra quién es
el actor, la fecha correcta o el significado de la frase.

`CoreContinuationPlanInspection.review_payload(context)` entrega fuente
original y fuente pendiente, spans, hora original, nombre elegido, hechos
nuevos, tipos/destinos, anclas temporales y menciones de referencias,
con digest de fuente/plan. No envía stable IDs, guards canónicos ni digest
privado del registro pendiente al proveedor; este último sí se conserva
internamente para una futura comparación de estado. La salida siempre
tiene `may_execute=False`, incluso si hay varios hechos plausibles.
La comprobación `validate_inspected_candidate_plan_current` compara de
nuevo el registro v2, la selección canónica y los hechos físicos con la
instantánea preparada y vuelve a inspeccionar el `RequestPlan` exacto.
Rechaza cualquier cambio entre inspección y el eventual prewrite; **no
evalúa la semántica ni habilita E3**, incluso si todas las guardas pasan.

**Matriz mínima de evaluación semántica antes de activar escritura:**
frase pendiente simple con persona elegida; referencia a otra persona que
no coincide con la elección; dos hechos distintos apoyados por una cláusula;
dos cláusulas con contexto compartido; corrección explícita; negación;
condición; fecha relativa con respuesta al día siguiente; día/hora
aproximados; uso de pronombres en ES/FR/EN y variantes morfológicas; actor
`SELF` implícito; mezcla con evento/tarea; propuesta que repite una
anotación previa reformulada; cambio de identidad entre revisión y E3;
replay de delivery ID y conflicto de otro actor. Contrastar textos,
identidades, polaridad, destinos, fechas y cobertura sin añadir un parche por
frase. El siguiente trabajo debe reutilizar, y adaptar solo si es preciso,
los contratos existentes de revisión Core/cobertura N:M y el Planner de Core;
el revisor debe evaluar el **plan completo** y devolver abstención ante
cobertura incompleta o sospecha de tergiversación. Sin esa evidencia, la
selección sigue terminando en `CONTINUATION_REVIEW_REQUIRED`.

No existen prompt de continuación ni aceptación de modelo nuevo ni ruta
automática de escritura. Los tests de esta inspección prueban exclusivamente
estructura y read-only con datos desechables, no confianza semántica.

## E5 — dictamen semántico independiente y acotado de continuación (30-10-2026, fuente inactiva)

**Contrato reutilizado, no nuevo proveedor:** se parte del prompt
`PROMPT_SOURCE_REVIEW_CORE_ANCHORED` y esquema JSON
`REVIEW_CORE_ANCHORED_SCHEMA` de `whole_source_model_contract.py`.
`odyssey_runtime/candidate_continuation_review.py` prepara solamente la
entrada, añade una explicación de alcance que diferencia **hechos fuente
ya confirmados por E3** frente a **hechos pendientes** y devuelve el esquema
existente. El original entero, reloj de captura original, candidato exacto,
referencia y nombre elegido se conservan para poder comprobar correferencias
sin reescribir la solicitud ni reutilizar un plan inicial ambiguo.
El *modelo* tiene que dictaminar la totalidad de hechos de la parte pendiente
y revisar su dependencia de contexto previo; no debe solicitar duplicar los
hechos ya persistidos. En esta fase no se crea cliente/proveedor activo ni se
cambia la versión aceptada del prompt general: el prompt de continuación
es una variante **NO aceptada en producción**.

`odyssey_core/candidate_continuation_semantic.py` valida de forma cerrada
el resultado del revisor independiente, manteniendo idéntico formato
`approved,complete,reason,facts` con orden de ordinales, `record`,
`reviewed_text`, `date`, `reference_names` y `supported`. Exige
`approved=true`, `complete=true`, revisión de **cada** hecho nuevo,
texto, fecha y referencias congruentes con las del `RequestPlan`, y no
admite actores mencionados en otra cláusula, participantes extra, falso
`supported`, pérdida de un hecho, órdenes cambiados ni `source_quote`
inventado por el reviewer. La inspección estructural reforzada verifica
todas las apariciones de `{{ref:N}}` y las vincula al helper Core
de solo lectura que le corresponde, sin asumir un número fijo de hechos.
Fechas múltiples/parciales no representables en el campo temporal escalar
de este revisor se **rechazan** hasta tener evidencia equivalente.
La validación adicional `validate_independent_continuation_verdict_current`
recomprueba registro pendiente, plan, identidad, hechos físicos y digest del
dictamen si se usan más adelante.

**Límite explícito:** el dictamen + checks deterministas **no certifican
verdad semántica**; un modelo que responda falsamente `approved=true`
puede seguir equivocándose en negación, fecha relativa, cardinalidad,
completitud o paráfrasis. El resultado `may_execute=False` siempre.
`validate_whole_message_coverage` no puede aplicarse sin cambios:
presupone que todas las aserciones del mensaje entero son hechos *nuevos*,
mientras que la continuación contiene recibos de hechos ya escritos.
No migrar su autorización E3 por copiar un esquema JSON. Esta etapa no
habilita automáticamente el revisor ni crea otra cola/Writer.

**Matriz obligatoria del prompt de continuación antes de activar un
proveedor/modelo y luego escritura** (evidencia por caso con modelo,
esfuerzo, prompt hash, respuesta del proveedor, coste y latencia):
(1) sujeto/identidad elegida sin cambio y misma cláusula pendiente;
(2) correferencia errónea a nombre de otra frase; (3) pasado vs futuro;
(4) fecha relativa resuelta contra captura original, no fecha de respuesta;
(5) dos acciones separables en el mismo candidato y referencia compartida;
(6) un solo hecho con apoyo N:M de varias cláusulas; (7) negación;
(8) condición; (9) autocorrección; (10) fecha parcial/duración/franja;
(11) intención de tarea vs experiencia pasada/evento; (12) SELF implícito
en ES, FR y EN; (13) duplicación literal y paráfrasis de hechos previos;
(14) fuente ambigua o cambio de target; (15) selector de otro actor;
(16) replay, modificación de fuente, plan, Markdown o guard de identidad.
El conjunto incluye positivos, abstenciones obligatorias y adversariales;
no cambiar esperados para ocultar falsos positivos.

**Pruebas de este corte:** entradas sintéticas, dictámenes congelados
(aceptado/no admitido/malformado/extra/reordenado), referencias simbólicas
inválidas, drift de plan, elección y notas físicas. No se ha consultado
ningún GPT en vivo; los dictámenes son entradas controladas por las pruebas.
El adaptador de llamada `review_selected_candidate_with_provider` reutiliza
el método estricto `WholeSourceLightExecutor._ask` sin otro cliente ni
otro servicio; recibe explícitamente el modelo, valida el dictamen y
devuelve la copia del JSON junto al sello inejecutable. Tests con cliente
Responses simulado prueban sobre HTTP lógico la envoltura strict/store=false,
el reloj original, resultado incompleto y dictámenes inválidos, sin escrituras.
**No está conectado a la ejecución de producción, y no ha llamado al modelo real.**
**Revisión de reutilización (30-10-2026):** el piloto F14/F27 ya
persistía el cine enlazado en Core/E3 desde los commits `89cffb5` y
`1df352d` del 10-10. No era una funcionalidad nueva del ensayo actual.
La diferencia de éste es el contrato de plan completo + dictamen independiente
para otros enunciados, todavía sin aceptación semántica real. El piloto
`SelectedCandidateWriteGuard` no está conectado a runtime ordinario y
continúa exclusivamente como centinela histórico, sin autorización general.
Ambos guards comparten ahora exactamente la misma función de comprobación
canónica de helpers y la identidad seleccionada, sin duplicar la resolución
de targets, la autorización ni el Writer Core/E3. Sus comprobaciones del
significado difieren por el límite de seguridad: frase fija antigua frente
a dictamen revisado general. No ampliar ni activar el piloto.

**Ensayo Core/E3 aislado de continuación revisada (sin activar, 30-10-2026):**
`ReviewedCandidateContinuationWriteGuard` conecta solo en tests sintéticos el
plan inspeccionado y el dictamen completo con el guard de Core existente.
Recomprueba el mismo plan (una acción para evitar escrituras parciales fuera
del futuro recibo), la selección/nota y los hechos previamente persistidos
antes de la primera escritura y de nuevo tras preflight de targets; exige
que helpers reference-only sean actualizaciones verificadas y que la
referencia elegida resuelva al ID de la persona seleccionada. Una acción
puede llevar varios hechos sin fijar una cardinalidad. El Writer Core/E3
real ha creado Day Markdown con el enlace canónico; se comprobó el texto
físico, que el diario anterior quedaba intacto, que un segundo hecho puede
compartir la identidad y que replay y cambios de plan/dictamen/identidad
no autorizan una escritura extra en la bóveda temporal.
Estos ensayos NO prueban que el revisor entienda el lenguaje; su dictamen
es sintético y puede afirmar falsamente `approved`. El guard no se
inyecta en Runtime/n8n/DEV/PROD ni concede permiso general para escribir.
**Siguiente bloqueo operativo único:** campaña semántica real y acotada
del prompt heredado; después conectar el flujo de autorización, recibo
duradero de terminación y readback confirmado con el E3 ordinario,
auditoría final y aceptación desde navegador en DEV matching-SHA.
