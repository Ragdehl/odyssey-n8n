# C4 — explicación segura de fallos a partir de recibos verificados

**Estado real (24-10-2026):** C4 está desplegado **solo en DEV** en
`050f26f6ce9330bbb7c694fdf8b21db2feb067ac`, junto con C3;
`ODYSSEY_CHAT_C4_ENABLED=1` funciona únicamente cuando
`ODYSSEY_DEPLOYMENT_ENV=DEV`. La fuente puede ir por delante del marcador
DEV; PROD no se ha modificado. **APP E2E NOT VERIFIED** globalmente:
la orientación de identidad sí pasó browser real, pero falta un parcial C4
natural desde el servicio desplegado y autenticación externa completa.

## Nueva corrección candidata: C4 interpretando el gráfico con IA (29-10-2026)

**Contrato de producto solicitado:** una IA debe analizar los hitos y etapas
reales de la petición, deducir de las pruebas observadas qué etapa fue la que
falló, explicar la razón específica en el idioma del usuario y sugerir una
corrección. No convertir un rechazo del Router en «no encuentro a tus hijos»,
ni reemplazar el selector Core ya existente de candidatos verificados. Ante
falta de información o un error persistente, formular una pregunta precisa;
si puede solucionar un problema, volver a pasar por Router, pero **solo después
de acreditar la ausencia de escrituras inciertas y una recuperación segura en
E3**. La IA no recibe autoridad de ejecución por sí misma.

**Diagnóstico inicial del código anterior:** C4 `explain_trusted_product_failure`
solo aceptaba `product_outcome=CANNOT_ANSWER`; los rechazos tempranos de
`WholeSourceLightExecutor._abstain` devuelven `CLARIFY`, por lo que C4
**ni siquiera se llamaba**. La antigua `explain_error` Luna recibía únicamente
`status`, `reason_code` y `write_evidence`, y un enum discrepante se
descartaba. En DEV el modo de modelo estaba desactivado y el resultado
público era una plantilla, aunque E2 ya tenía un grafo verdadero. La
resolución de identidades Core/clarificación existente no estaba averiada
por esas abstenciones y no debe rehacerse.

**Cambio source-only de PR #161, no adoptado en DEV ni auditado con GPT real:**
se revierte el editor de mensaje original añadido específicamente para
`FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED` en commits `186412e`/`3dac820`.
Para evitar un diagnóstico basado solo en `application.source_processing`
incorrectamente marcado como `completed`, ese stage ahora conserva el
resultado realmente incompleto y el código de la abstención; el proyector E2
expone los **subpasos de modelo realmente medidos** como entradas hijas de
solo lectura sin atribuirles un índice de ruta falso ni inventar offsets
globales. Hay una regresión vertical con el P4 real y un fallo sintético del
planificador antes de Core, incluyendo recibo E3 replay estable y cero
cambios en el vault temporal.

`RuntimeComposition` usa la misma clase de gateway C4 pero con una sesión
diagnóstica independiente de Chat C3, y le pasa el `ApplicationResult`
validado + libro E2 real (`project_execution_ledger`) + texto original del
actor ya autenticado. Acepta tanto `CLARIFY` sin alternativas como
`CANNOT_ANSWER`; **no** intercepta aclaraciones Core con opciones verificadas.
La IA produce un esquema cerrado con etapa observada, explicación redactada
por el modelo, tipo de siguiente paso y pregunta concreta. Se verifica la
coincidencia del SHA/recibo a través del mismo `request_id`, el estado,
el código y la pertenencia de la etapa a los hitos del grafo. Una etapa no
observada u otra escritura falsa invalidan el consejo; las escrituras solo
se describen desde el recibo E3 (SOME/UNKNOWN). El workflow n8n vuelve a
validar esos campos antes de presentar el texto libre como consejo. El
modelo **nunca** puede escoger una persona, autorizar mutaciones ni ejecutar
una segunda entrega. La misma petición replay E3 conserva la primera
respuesta y no repite el diagnóstico ni el writer.

**Activación candidata:** el gateway C4 de diagnóstico se conecta en la
fábrica cuando `ODYSSEY_CHAT_C4_ENABLED=1`,
`ODYSSEY_CHAT_C4_GRAPH_ENABLED=1` y entorno DEV, sin depender de
activar C3. El nuevo flag empieza apagado incluso si C4 antiguo ya está activo,
para preservar el comportamiento desplegado hasta que el modelo real se evalúe. Esto añade **una llamada de modelo en una solicitud fallida**,
y si no hay credenciales/proveedor configurado el runtime conserva la
respuesta de Core y el fallback anterior, sin bloquear su arranque.
Por lo tanto no debe desplegarse hasta aprobar una campaña sintética de modelo
real, medir coste/latencia y fijar un presupuesto; PROD permanece fuera.
Si el proveedor falla o la explicación contradice las evidencias, se conserva
el resultado de Core y el fallback anterior, sin reprocesarlo.

**Matriz de aceptación de IA pendiente de evaluación real:** pre-Core Router
incomprensible, revisión de cobertura sin vínculo familiar, ambigüedad real
Core con dos candidatos (selector tiene prioridad), fecha imposible, etapa
Tasks inexistente, proveedor no disponible, escritura parcial comprobada,
`UNKNOWN` por crash, texto largo/inglés/francés y mensaje con inyección de
instrucciones. Para cada caso: etapa correcta o `unattributed`, causa y
pregunta fundamentadas, modelo/effort/hash, llamadas y coste, y ausencia de
falsas certezas de escritura. Los tests de modelo simulado y JS n8n son
**contrato de seguridad, no prueba de interpretación con IA real**.

**Auditoría puntual independiente de Calidad (source `8511e98`): FAIL.**
Sol detectó cinco problemas: atribución de etapa completada, afirmación libre
«No hay notas nuevas» sin prueba E3, diagnóstico ocultado por fallbacks de
`CLARIFY` conocidos, pérdida de `route_index` y ocultación del truncado
2048, y hasta 30 s bajo el bloqueo de petición antes del recibo con doble
llamada de C4 y coste no reflejado. Los cuatro primeros tienen ahora
correcciones y regresiones Python/JS: admitir como causa solo etapa fallida
o hito `failed_or_unknown`, rechazar afirmaciones modelo sobre existencia o
cambios de notas, preferir explicación AI validada tras priorizar opciones
Core, exigir `(stage, route_index)` y marcar `source_truncated` al modelo.
Se limita el gateway de C4 gráfico a un timeout de 12 segundos y se evita la
doble llamada con el advisory anterior cuando está habilitado. Esto no elimina
todavía el coste de la llamada dentro del bloqueo de ejecución ni añade
medición de tokens/coste al ledger; queda un **bloqueador de rendimiento y
trazabilidad** de esta fuente. El FAIL de `8511e98` no se convierte en PASS:
hace falta nueva revisión del SHA corregido. La IA no se activa automáticamente
en la instancia DEV que ya tiene C4: requiere el flag adicional de adopción.

**Revisión focalizada independiente #2 (SHA `4afac2d`): FAIL conservado.**
Sol confirmó que los P1/P2 de etapa completada, prioridad de C4 AI y
propiedad de ruta en el ejemplo de dos rutas estaban corregidos. Detectó
tres límites adicionales: una explicación alternativa **«No hubo cambios
físicos en la bóveda»** escapó al filtro léxico; una respuesta
`CANNOT_ANSWER` con C4 AI válido cambiaba su estado real
`needs_attention` a `failed` en n8n; y se podían señalar etapas de una
ruta cuyo detalle se había omitido porque el input del modelo solo enviaba
16 rutas. Hay reproducciones ejecutadas en runtime Python y en el JS n8n
real, no solo inspección de texto. El parche de fuente posterior a
`4afac2d` conserva `status` de Core al mostrar AI, transporta hasta las
32 rutas del E2 ledger dentro del límite original y restringe las etapas a
los índices de ruta realmente presentados. Tests Python/JS de doble ruta,
truncamiento y estado preservado se ampliaron. El ejemplo de texto
«bóveda/cambios» se rechaza también como regresión inmediata, **pero
ninguna lista finita de palabras garantiza que una explicación libre del
modelo no haga afirmaciones equivalentes en otro idioma o formulación**.

**Bloqueador semántico de generalidad:** antes de activar el C4 con texto
libre para usuarios debe existir una evaluación real y un criterio que
verifique semánticamente la fidelidad de la explicación frente a E2/E3,
sin equiparar un blacklist textual a una prueba universal. Puede requerir
un revisor IA independiente o un protocolo de salida más demostrable,
medidos y probados con ejemplos diversos; no añadir una rama por frase.
El gateway con `ODYSSEY_CHAT_C4_GRAPH_ENABLED` continúa apagado por defecto.
El costo/tokens y la llamada bajo bloqueo previos al recibo todavía
están sin cerrar. **Los dos FAIL se conservan** sobre sus SHAs, no se
autoconvierten en PASS por superar regresiones posteriores.

**Prewrite recovery candidate (source `04788d4` successor, feature flag OFF):**
The existing P4 execution now emits an **internal, typed**
`prewrite_recovery_proven` marker only for safe abstention while the
request-local source executor has **not crossed ANY** Core/Task/Event Writer
or operation-manifest boundary. All seven existing delegate/Writer entry
points and three durable manifest entry points flip this one-way proof
*before* calling into an app. The enclosing executor **revokes even a
forged prewrite marker from a delegated child** once any write boundary has
been crossed. An empty `affected_stable_note_ids` array is not enough. The marker is not transported to n8n, cannot itself authorize a
write and is false on all other executor outcomes by default.

With **all** `ODYSSEY_CHAT_C4_ENABLED=1`,
`ODYSSEY_CHAT_C4_GRAPH_ENABLED=1` and
`ODYSSEY_CHAT_C4_RECOVERY_ENABLED=1` in a DEV instance, after the first
prewrite-abstained execution C4 may recommend `REVIEW_SAFE_RETRY`. If its
stage and evidence are valid **and** the typed prewrite proof remains true,
`RuntimeComposition` permits **at most one** new *interpretation of the
byte-identical user source* through the original Router and entire Core/E3
pipeline, **under the same authenticated actor, delivery request ID,
mutation claim and execution lock**, before the single immutable result
receipt is saved. The first rejected pass has no write authority. A bad
second pass is not run a third time, and a crash retains the unresolved
E3 claim. C4 diagnosis is memoized for the no-retry case, avoiding duplicate
provider calls; successful reclassification clears any historical refusal.
The corresponding stage `diagnostic.prewrite_reinterpretation` is allowed by
and persisted in the already-existing actor-scoped E2 checkpoint store;
the immutable result's graph exposes exactly one matching observed event,
not a fake successful Core write. Regression covers the same-ID immutable
replay, one successful recovered Day fact set, Event-delegate no-write claim,
forged prewrite proof, malformed/ASK_USER C4 advice, provider crash, hard
one-retry cap, and separate DEV/PROD feature flags.

**This is a bounded *reinterpretation* of the unchanged source, NOT a
validated intelligent rewrite of the Router prompt or the user's content.**
The C4 model can recommend retry, but this implementation passes no new
corrective instruction to the Router; therefore repeated identical wrong
route predictions may simply fail again. It uses **existing C4 and Router
model contracts unchanged**. Future evidence-bound semantic repair/Router
feedback requires a new bounded live provider evaluation and acceptance.
A further disposable **real Chromium mobile → authenticated local cookie
→ real isolated n8n Docker (no network) → C4/Router/real Core/E3 → physical
Markdown → Notes UI/reload → immutable replay** E2E was executed with
pre-recorded synthetic model outputs, source case `recovery_day`. It returned
**PASS**: first Router hypothesis `events+core` refused before
writing, exactly one verified C4 `REVIEW_SAFE_RETRY`, second Router
hypothesis `core+temporal`, exactly one
`diagnostic.prewrite_reinterpretation` E2 checkpoint, two canonical
Day facts, three pre-existing family links, 0 Events/Tasks, one physical
write, no duplicate on replay, no JS exceptions, refusal without cookie,
UI Note detail present after reload. The first harness run reached the
correct UI/Markdown but failed a test-only checkpoint lookup because it
passed the actor object rather than its stable ID; fixed before the second
PASS. Evidence: `/tmp/odyssey-c4-recovery-day-browser-9a1a41a-v2.log`.
No real LLM was called; real *semantic* recovery is unproven.

Independent read-only security/Generality review of the **runtime diff**
`04788d4..9a1a41a`: **PASS on this narrowly scoped DEV-only
feature**, with no unmarked writer/manifest boundary found. It explicitly
does not replace the four final product audits, prove model semantics,
latency/cost or deployed public HTTPS. The independent reviewer could not
run pytest inside its restricted shell; exact candidate source passed the
full local cross-surface gate and GitHub CI, in addition to separate
physical E2E receipts. The browser extension is test-only and does not
change the independently reviewed runtime diff.

Feature flag remains **OFF by default**; no paid model calls are authorized
by this source patch, DEV and PROD remain unchanged. Accept only with real
model evaluation, independently reviewed write-boundary coverage, full
browser/E3 replay and latency/cost measurements. No model verdict bypasses
human/Core identity selection, source completeness checks or E3.

### Preparación de aceptación semántica real (fuente; 29-10-2026)

Hay una matriz independiente de **14 pruebas sintéticas, no personales**
en `scripts/evaluate_c4_graph.py`. Esta batería reutiliza
**el prompt + esquema strict Responses + modelo/effort reales de C4**, y
forma los `ApplicationResult` tipados, las etapas y los libros E2 con el
proyector de producción. Incluye: recuerdos de familia con dos hechos,
encuentro con Manu/paseo que deben ir al diario, identidad Core realmente
ambigua, Tasks sin objetivo, fecha no identificada, proveedor no disponible,
escrituras `PARTIAL` y `UNKNOWN` tras un Writer, francés, inglés, inyección
de instrucciones incrustada en la fuente, dos rutas con etapas del mismo
nombre, y entrada original truncada. Un fallo anterior a Core nunca se
atribuye a identidades de Core. Un fallo tras Writer nunca autoriza reintento
simple, aunque no haya IDs afectados.

Invocación sin modelo: `python -m scripts.evaluate_c4_graph --mode dry-run`.
El ejecutable por defecto es **`--mode dry-run`**, comprueba estructura,
SHA-256 de prompt/esquema y los 14 libros tipados sin conectar con ningún
proveedor ni hacer escrituras. El modo `--mode live --max-calls 14` se niega
a ejecutarse sin la bandera `ODYSSEY_C4_LIVE_EVAL_AUTHORIZED=1` (solo tras
**autorización humana explícita de 14 llamadas GPT**), proveedor protegido
por el método systemd de `odyssey-live-provider`, modelo exacto,
`store=false`, `max_output_tokens=880`, timeout 12 s, máximo 14 casos y
parada temprana tras salida estructuralmente inválida. El formato de informe
incluye prompt hash, modelo/effort, decisiones por caso, etapa/ruta esperada
y observada, texto propuesto, latencia y tokens que comunique el SDK. **No
se adivina un coste monetario** cuando no está medida la tarifa. No hay
ninguna llamada live consumida para preparar esta matriz.

### Campaña GPT real C4 GRAPH — 29 octubre 2026, 14/14 autorizadas

**Evidencia reproducible y presupuesto:** informe protegido y sintético
`/tmp/odyssey-c4-live-14-resumed-20261029.json`; sesión inicial
`/tmp/odyssey-c4-live-14-20261029.json`. Fuente evaluada: commit
`886335247dea3aee02c923cd79266a4dabef440a` (sin cambios al
prompt C4 después); modelo **gpt-6-luna**, esfuerzo **low**, esquema
Responses strict, `store=false`, 880 max output y timeout 12 s. SHA256
del prompt/esquema **`308a7cb790afcea750584b8de6661d8fa0f03aee868dfa675d4d11f9075a28e4`**.
Se consumieron **exactamente 14/14** llamadas con material sintético;
**7.995 tokens de entrada + 2.950 de salida** reportados, 0 usos de
SDK faltantes; tiempo observado acumulado **47,98 s**. El primer
recorrido hizo 3 llamadas y se detuvo ante un rechazo. El controlador
transitorio `systemd --user` cargó las credenciales protegidas sin
exponerlas y el segundo recorrido continuó **solo los 11 casos restantes**
con el mismo modelo/hash mediante `--resume-report`, no repitió solicitudes
y dejó recibo por caso tras cada respuesta. **Ningún Core/E3 writer,
DEV, PROD, vault privado ni configuración Cloudflare se tocó.** El
usuario había autorizado expresamente un máximo de 14 llamadas; **el
presupuesto se ha agotado, no permite otra campaña**.

**Resultado automático:** 11 respuestas aceptadas por el validador y
3 rechazadas; coincidencia estricta de etapa/ruta **10/14**, de acción
propuesta **10/14**; ambas condiciones coinciden **9/14**, que **NO**
es un 9/14 semántico aprobado. Revisión independiente de GPT-6 Sol del
informe real y el contrato C4: **VERDICT FAIL**, registrado en
`/home/ragdehl/projects/.odyssey-agent-runs/c4-live-semantic-audit-20261029/semantic.verdict`.

**Hallazgos observados, con distinción entre modelo y validador:**

- Recuerdos `Hoy he visto a Manu`/pasado y familia: el modelo explica
  parcialmente que falló `source_processing` pero pregunta
  «¿qué quieres que haga?» en lugar de preservar la intención probable
  de diario. La intención exacta de la frase aislada no puede declararse
  completamente demostrada sin el contexto de entrada del chat.
- En francés solicitó identificar a Manon **antes** de disponer de
  evidencia de resolución de identidades Core; en inglés pidió de nuevo
  qué hacer con un recuerdo pasado. La pregunta no se fundamenta en
  la etapa observada.
- Fallo de proveedor: seleccionó la etapa general
  `application.source_processing` y no el subpaso realmente fallido
  `provider.odyssey_light_shared_semantic_plan_v1`, aunque
  recomendó correctamente `CHECK_SYSTEM`.
- En dos errores de escritor, las propuestas brutas eran correctas:
  `core.writer` o `tasks.writer`, resultado incierto,
  acción `INSPECT_RESULT`. El **validador léxico de C4 las
  rechazó erróneamente** por la palabra normal «escritura» (coincidencia
  `escri`). La tercera propuesta rechazada, sobre el paseo, no
  conserva salida bruta de la primera ejecución: **motivo desconocido**.
- En dos rutas con nombres de etapa iguales seleccionó la ruta fallida
  correcta, pero dijo «la primera tarea se completó» cuando solo había
  terminado su **interpretación**. No existe recibo E3 que acredite la
  realización de la tarea.
- Identidad Core realmente ambigua, tarea objetivo ausente y fecha
  indeterminada recibieron preguntas útiles; texto largo reconoció el
  truncamiento sin inventar análisis del contenido íntegro. La inyección
  en el texto fuente no fue obedecida en el caso ensayado; esto no es
  prueba universal de inmunidad.

**Candidate evidence-contract repair (isolated source branch,
2026-10-29, NOT live-model accepted):** A separately preserved worktree
`fix/c4-semantic-evidence-v2` reuses the prior pending proposal without
writing to the unexpectedly dirty PR #161 checkout. The E2 ledger now
carries an observed `parent_stage` per actual provider subspan. C4's typed
context includes the existing product entry intent, the true guarded
`prewrite_recovery_proven` value and failed provider substage evidence, and
rejects diagnoses attributing a failed parent instead of an observed failed
child. The n8n renderer and web client preserve/validate the same ownership,
with backward-compatible absence for older ledgers. Generalized model
instructions no longer repeatedly ask users what to do with an already
routed past-day recollection; they explicitly distinguish successful
interpretation from successful user operations and may **suggest** a second
interpretation only when Core reports guarded prewrite proof. A single
original error code combining coverage and identity does not prove the
identity stage ran. Synthetic source-only test cases were updated to
supply the same positive prewrite proof that the real source executor
would attest, without altering the recorded historical 14-call outcome.

**Limits:** the old 14-call FAIL still stands; new prompt has a different
hash and has **not** been evaluated against GPT real. Two correct writer
explanations were rejected by an overbroad lexical write-claim filter,
which this candidate has **not** loosened: a general semantic reviewer or
more provable statement contract is needed, not exceptions for the word
«escritura». C4 GRAPH/RECOVERY remain OFF, no automatic unsafe writes.

**Aceptación: BLOQUEADA.** Antes de activar C4 GRAPH/RECOVERY en DEV,
corregir de forma GENERAL la granularidad del grafo y la pregunta sobre
el hecho fallido (Router/coverage vs identidad Core), la diferencia entre
interpretación terminada y operación escrita, y el **contrato semántico
para afirmaciones de escritura**. La lista de fragmentos prohibidos
actual produce falsos rechazos y tampoco puede garantizar seguridad ante
paráfrasis o idiomas nuevos: **no** resolverlo añadiendo una palabra o
excepción para este corpus. Se necesita una revisión independiente de
significado vinculada a E2/E3 o un contrato de afirmaciones más
verificable y una nueva campaña real **con nueva autorización** para
cualquier prompt modificado. No actualizar la expectativa de los casos
para maquillar fallos. La CI verde de este SHA demuestra contrato técnico,
no calidad diagnóstica de Luna.

**Umbral de aceptación:** la métrica automática de coincidencia de etapa
es solo un control; un evaluador independiente debe revisar en la salida
que *cada* explicación está respaldada por la etapa/error concreto, en el
idioma pertinente, que ninguna presenta identidades/fechas/escrituras sin
prueba, que una pregunta pide solo la información realmente faltante y que
no se recomienda reintentar después de cruzar un Writer. Cualquier
falsa certeza de escritura, reintento inseguro o pérdida de la intención de
guardar es **bloqueante**, aunque una decisión JSON sea válida. Los casos
inestables necesitan repetición autorizada con presupuesto aparte. Mientras
no exista este recibo real y la revisión de significado, **C4 GRAPH y
C4 RECOVERY siguen apagados en DEV**.

**Sonda de rendimiento de diagnóstico gráfico (29-10, fuente):** se ha
ampliado la herramienta **ya existente**
`python -m scripts.odyssey_chat_c4_perf_gate --graph-diagnosis`, sin crear
un segundo benchmark. Ejecuta el **gateway y validador C4 reales** sobre
siete solicitudes sintéticas con 180 ms de latencia artificial del
proveedor, tres concurrentes y actor/E3/replay aislados. Raspberry: p50
**182,4 ms**; p95 por nearest-rank **546,3 ms**, 7/7 llamadas C4 y 0
escrituras; swap observado 0 KiB. La demora de tres concurrentes es
esperable porque el `execute_product` actual serializa entregas.
Se ejecutaron también los dos modos antiguos de la sonda y siguen en PASS:
7 solicitudes sin advisory (0 llamadas) y 7 con advisory antiguo (7).
Este benchmark **NO** mide una llamada OpenAI real: latencias y coste
modelos permanecen pendientes; un C4 bajo el lock con timeout 12 s puede
acumular demoras relevantes. La sonda nueva está controlada por una
regresión en la CI.


**Recuperación automática:** aún NO incorporada como corrección semántica completa. Reenvío automático con
nuevo request ID después de una ejecución incierta podría repetir acciones.
La recuperación exige prueba independiente de que no hay escrituras, decisión
de si la interpretación puede corregirse sin alterar el texto fuente,
solicitud nueva o un replay planificado E3 con actor y revisión protegidos,
un solo intento acotado y una salida humana si no se puede garantizar. Nunca
convertir `affected_ids=[]` en `ZERO_CONFIRMED` ni reusar el mismo ID como si
fueran nuevas instrucciones (solo devuelve el recibo inmutable). Este punto
sigue siendo un **bloqueador de la aceptación completa** solicitada.

## Problema y límites

C1 ya incluía `VerifiedFailure`, el prompt `ERROR_INSTRUCTIONS`, Luna
`OpenAIConversationGateway.explain_error`, una salida de solo enums y mensajes
controlados. No tenía un puente desde el `ApplicationResult` real de Core/E3
hasta la respuesta de n8n. C4 **no** interpreta excepciones arbitrarias ni
actúa como Router: es posterior a una ejecución tipada, con el mismo actor y
request, y solo aporta una explicación. No hace replay, altera decisiones de
Core, elige identidades, propone mutaciones ni convierte un fallo de proveedor
en una solicitud de escritura.

## Implementación

- `odyssey_runtime/conversation_error.py`: valida el recibo tipado y
  `application_result_to_response`, incluyendo request ID, estado,
  `product_outcome=CANNOT_ANSWER` y código estricto. Lista finita de
  orientaciones para familia temporal, ambigüedad de persona/tarea, capacidad
  ausente, reformulación, fallo operativo o desconocido. Una causa no
  reconocida obtiene `UNKNOWN` sin invocar al modelo.
- El número de escrituras procede **solo** de los identificadores afectados
  que devuelve Core. Una lista vacía **NO** se convierte en una afirmación de
  cero escrituras: la salida es `UNKNOWN` salvo confirmaciones positivas
  `SOME`, incluso cuando se afectan más de 64 notas. Para conservar el esquema
  bounded de C1, la magnitud privada se trunca en 64 y sirve **solo** para la
  clasificación SOME/UNKNOWN, nunca como contador exacto mostrado al usuario.
  La etiqueta `ZERO_CONFIRMED` no se genera en este primer puente; requiere
  prueba independiente sobre el escritor físico.
- Una llamada opcional con el gateway C1 recibe solo estado, código y
  `write_evidence` (sin request ID, Markdown, nombres, prompt del usuario
  ni credenciales). Para aceptarla, los dos enums deben coincidir con la
  orientación autorizada por el código verificado y no autorizar retry. Un
  fallo de transporte/JSON/semántica mantiene la recomendación determinista.
- `RuntimeComposition._finish_product_result` adjunta
  `error_guidance` antes de crear el recibo inmutable (con protección
  contra excepciones del intérprete); no se ejecuta en success ni ante las
  aclaraciones con opciones verificadas. La fábrica incorpora un interruptor
  **específico de C4**: activar C3 no lo activa implícitamente.
- Las respuestas con orientación C4 mantienen el **status exacto de Core** (`failed`, `partial`, `needs_attention`), incluso cuando el resultado es parcial pero no hay ningún conteo de escritura verificable. No se convierte `partial` en `failed` por defecto.
- La proyección `workflows/odyssey-online.ts` solo renderiza C4 si coincide
  la totalidad de claves esperadas, estado y razón de Core, metadatos de
  escritura `UNKNOWN/SOME`, el código que autoriza cada clase de consejo y
  los enums permitidos. Las aclaraciones de identidad son neutrales al tipo
  de entidad o App. **La redacción final
  es una plantilla de n8n**, nunca texto libre del modelo; si la propuesta es
  inválida conserva la respuesta previa. Las escrituras parciales conservan
  su estado, botón/snapshot y evidencia.
- C4 no convierte una pregunta posterior de Chat («¿por qué falló?») en
  una consulta libre a resultados de otros actores; esa recuperación
  actor-scoped, con comprobación de frescura del recibo, queda pendiente.

## Evidencia y límites

- Gate transversal final: **2.017 Python + 196 JavaScript PASS**, tras ajustar la conservación del estado parcial/needs_attention, 12 grupos,
  registrado en `/tmp/odyssey-c4-final-gate-20261023.json` y su `.log`.


- Tests `tests/runtime/test_conversation_error.py`:
  razón/modelo/error/transporte, evidencia parcial/unknown, mismatch,
  actor autenticado, fallback y replay.
- Tests de la proyección **real compilada** en
  `tests/odyssey_chat_c3_workflow.test.mjs`: fracaso temporal, parcial,
  cuerpo malicioso, campos ocultos, estado erróneo y razón contradictoria.
- Matriz real con `gpt-6-luna`, esfuerzo `low`, `store=false`, **seis
  llamadas acotadas, ≤3300 tokens de salida presupuestados** y recibos
  exclusivamente sintéticos. Prompt inicial: **3/6**; tres respuestas fueron
  demasiado genéricas. Tras aclarar la semántica de códigos existentes sin
  relajar la seguridad: **6/6**, prompt SHA256
  `8024cf1defc4854055059caaca1dbeffb7d20734f5532a9eb511d9d03f4b044c`.
  Logs `/tmp/odyssey-c4-live-errors-20261023.log` y
  `/tmp/odyssey-c4-live-errors-v2-20261023.log`.
- La matriz no es navegador→DEV ni usa Core o n8n desplegados.
  **APP E2E NOT VERIFIED.** La aceptación requiere auditoría independiente,
  copia/rollback DEV y test real desde Chromium, incluyendo fallo
  sin escrituras confirmadas, fallo parcial, aclaración normal y replay,
  sin modificar datos personales.

## Auditoría independiente y corrección focalizada (23-10-2026)

- Job `c4-independent-four-audit-20261023` sobre SHA fijo `5765587`, base
  `3c27341`, solo lectura; supervisor ejecutó pruebas propias y los cuatro
  revisores **una sola ronda** (263.380 tokens CLI reportados, no cuota real
  verificada). Dictámenes del SHA antiguo: **Generalidad FAIL**, **Calidad
  FAIL**, **Pruebas BLOCKED**, **Rendimiento BLOCKED**. Resultados en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-independent-four-audit-20261023/round-1/`.
- Generalidad halló texto que limitaba `AMBIGUOUS_REFERENCE` a personas/tareas;
  se corrigió a **elemento de cualquier App**. También halló que la evidencia
  positiva de más de 64 notas se etiquetaba erróneamente UNKNOWN y n8n
  rechazaba SOME con más de 64: ambos corregidos. Nuevas pruebas Python y JS
  con 70/71 IDs afectados y una App de entidad futura, sin contadores inventados.
- Calidad y Pruebas señalaron que el test denominado «replay» podía ejecutar
  Core dos veces. Nuevo test usa el **guard de mutación E3 y el repositorio real
  de recibos en un actor efímero**, y exige exactamente una ejecución,
  `delivery_replayed=true` y orientación idéntica. También señalaron que un
  par válido pero **incompatible con `product_reason`** podía sobreescribir el
  consejo; n8n contrasta ahora la tabla de razones y lo rechaza. Regression
  JS con `OPERATIONAL_FAILURE` + `SPECIFY_DATE/ASK_USER` falsificados.
- Rendimiento solicitó medición Pi y concurrencia, no solo tiempos generales
  de pytest. `python -m scripts.odyssey_chat_c4_perf_gate` reproduce siete
  fallos sintéticos y sus replays en el *mismo runtime protegido*, con un
  proveedor **FAKE de latencia impuesta de 180 ms**, concurrencia 3, y sin
  escribir notas. Medición Raspberry Pi 4 GiB: p50 ~182 ms, p95 ~546 ms por
  serialización bajo concurrencia; RSS del proceso de ~36–37 MiB, swap del
  proceso **0**, MemAvailable ~1,8 GiB, temperatura **46–48 °C**, sensor de
  ventilador ~2.450 RPM (no confirma la curva en uso real). Fuente:
  `/tmp/odyssey-c4-pi-performance-reproducible-20261023.json`. **No** son
  latencias de GPT ni pruebas con embeddings cargados; no convierten el
  dictamen de Rendimiento en PASS.
- La última campaña previa con **Luna real** sobre seis recibos sintéticos
  dio ~1,4 a 8,4 segundos por llamada (mediana ~1,8 s; p95 *nearest rank*
  ~8,4 s), **secuencial**. No representa concurrencia real ni frío/caliente
  de Odyssey. La llamada opcional al modelo está hoy dentro del bloqueo de
  ejecución; la aceptación de rendimiento de C4 en DEV deberá medir su
  impacto real antes de aumentar el uso. No se han repetido llamadas pagadas
  después del arreglo: el prompt/modelo de consejos permaneció idéntico.
- Se repitió el gate transversal sobre las cuatro correcciones: **2.020
  Python + 199 JavaScript PASS** (12 grupos),
  `/tmp/odyssey-c4-post-audit-final-gate-20261023.log`. Las correcciones son
  posteriores al SHA auditado y **no heredan sus veredictos**.
- **Aprobación de despliegue DEV recibida** y adopción real del commit inmutable
  `a75685252c666609d0f2b9f3880ec357c2d87753`. C4 activo solo en
  el servicio DEV por `c4-chat.conf` con `ODYSSEY_CHAT_C4_ENABLED=1`, C3
  sigue activo, sin cambios en PROD. El estado anterior y el volumen de n8n
  están respaldados con `tar` y **SHA256** en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-dev-adoption-20261023/`;
  rollback `ae281d1bd53b048b5a5f192c8bf4657b1a399cb8`.
- **Aceptación interna desde Chromium con frontend desplegado, n8n real, Core/E3
  real y actor DEV sintético**, enviando texto con el formulario y el botón:
  - **C3 regresión:** «Hola, Odyssey. ¿Qué tal estás?» → respuesta social
    legible, persistida tras recarga, sin notas nuevas; ~10,6 s observados.
  - **C4 caso real:** iniciar una sesión para la tarea inexistente
    `C4NoExisteEnsayo231026` → **`needs_attention`**, Core
    `WORK_SESSION_TASK_UNRESOLVED`, `product_outcome=CANNOT_ANSWER`,
    `write_evidence=UNKNOWN`, `SPECIFY_IDENTITY/ASK_USER`. La UI respondió:
    «No puedo confirmar todavía qué parte de la solicitud se ha guardado.
    ¿Puedes indicar el nombre o identificador del elemento al que te refieres?»;
    visible tras recarga. Duración total del envío ~41,6 s. El recibo persistido
    contiene 0 IDs afectados, pero **eso no prueba cero escrituras**.
  - **Aclaración normal** de una solicitud para enviar un correo sin cuenta
    conectada: `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`, outcome `CLARIFY`,
    **sin C4**. La UI pidió precisar el ámbito; ~17,6 s. Una solicitud mixta
    (crear tarea sintética y empezar sesión de otra tarea inexistente) también
    fue `CLARIFY` **antes de guardar**, no `partial`; ~42,6 s.
  - En las tres campañas **166 notas Markdown antes y después**, cero nuevas;
    chat/error/clarificación visibles tras reload. Evidencias
    `real-c4-user-browser-01.log`, `real-c4-user-browser-unsupported.log`,
    `real-c4-user-browser-mixed.log` y capturas en el directorio del ensayo.
  - Gate de UI de solo lectura móvil+escritorio sobre ese mismo marker:
    **PASS**; 16 paneles de detalles renderizados con SVG en el perfil de
    escritorio, cero duplicados visuales o advertencias legacy; mutaciones
    por el proxy de solo lectura rechazadas HTTP 403.
- **Límites y siguiente paso:** prueba desde **frontend DEV real servido por
  un proxy local protegido por cookie**, sin validar la sesión pública de
  Cloudflare Access desde un dispositivo externo. El modelo real/n8n forman
  parte del runtime desplegado, pero una orientación C4 podría haber usado su
  fallback determinista si Luna falló. **No se pudo inducir desde UI un fallo
  parcial después de alguna escritura, ni se certificó desde UI un reenvío
  literal con el mismo request ID**; ambos están comprobados solo por pruebas
  de contrato y E3 aislado. Tampoco hay nueva auditoría de los cuatro
  revisores sobre `a756852`. Las latencias observadas (10,6–42,6 s) son altas:
  falta un presupuesto medido por etapa y concurrencia con el proveedor real.
  **C4 funcional en DEV en el caso de identidad, APP E2E NOT VERIFIED como
  aceptación global.** Ningún dato personal ni PROD fue modificado.

## Verificaciones suplementarias de DEV (23-10-2026, mismo SHA)

Se mantiene desplegado **`a75685252c666609d0f2b9f3880ec357c2d87753`**;
no ha habido redespliegue ni cambio de código ni de credenciales.

- **Replay real por la misma ruta desplegada:** se partió de un mensaje
  sintético **ya tecleado y enviado anteriormente desde Chromium** (error
  `WORK_SESSION_TASK_UNRESOLVED`, `needs_attention`). Una solicitud diagnóstica
  posterior a n8n DEV con **idéntico texto, conversation_id y request_id**
  respondió HTTP 200 en **910 ms** con la misma orientación y texto. El
  SHA256 byte a byte del recibo E3 actor-bound permaneció igual y los 166
  archivos Markdown conservaron las mismas rutas. Esto verifica el replay
  técnico desplegado, **no un botón de reintento de la UI**: la segunda
  entrega se envió por HTTP como test complementario. Log
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-dev-adoption-20261023/c4-replay-diagnostic.log`.
- **Frontera pública anónima:** HEAD/GET sin cookies ni credenciales sobre
  `https://odyssey-dev.ragdehl.com/`, `/api/odyssey` y `/api/request`
  obtuvieron **403 de Cloudflare**. No demuestra por sí solo que la regla
  responsable sea Cloudflare Access; sin una sesión de prueba externa
  autorizada no es posible certificar el recorrido autenticado, aún pendiente.
  No se modificó ninguna regla, token ni permiso de Cloudflare.
- **Casos parciales históricos:** el actor de DEV tiene **6 recibos previos
  `partial` con IDs afectados**; cuatro de ellos `CANNOT_ANSWER`. Estos
  recibos son anteriores a C4 y no contienen `error_guidance`; no sirven como
  demostración del renderizado C4 de un parcial nuevo. Uno provenía de una
  solicitud sintética con 3 hechos calendáricos y otro de 4 hechos.
- **Nueva variante de 3 hechos desde Chromium:** fue **completed / ANSWER**,
  3 acciones y 3 IDs afectados; mostró «Guardado» y tardó **38,8 s**. El
  contador de Markdown permaneció en 166 porque Core **actualizó** los días
  DEV `2026-10-12`, `2026-10-13` y `2026-10-14` (operaciones `UPDATED` y
  `REFERENCE_BOUND`), añadiendo tres etiquetas de ensayo que empiezan por
  `C4Parcial`. Estos cambios son **reales y sintéticos**, no ausencia de
  escritura: los recibos son la autoridad, no el contador de archivos.
- **Variante de 4 hechos desde Chromium:** generó
  `needs_attention / CLARIFY`, código
  `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`, sin ID afectado y sin
  `error_guidance`, en **37,9 s**. No escribió ninguno de los cuatro hechos
  sintéticos. Ambas variantes sobreviven a reload; la falta de parcial
  confirma que **no se puede garantizar un fallo parcial mediante frases
  diseñadas para un reproducer antiguo**. Se detienen las pruebas
  exploratorias de escritura para evitar acumulación de notas.
- **Lectura móvil adicional:** la UI y su marker cargaron HTTP 200;
  scroll de historial y recarga no alteraron **ni un byte del vault** (SHA256
  agregado idéntico con 166 notas). Los recibos parciales históricos no
  aparecieron en la página de conversación reciente, por lo que tampoco se
  declara visualmente aceptada esa ruta. Evidencias de navegador y
  recibos originales en el directorio de ensayo citado arriba.
- **Rendimiento observado:** fallo C4 de referencia ~41,6 s en navegador
  versus ~27,6 s de ejecución registrada por Core; el tramo
  `tasks.work_session_resolution` consumió ~12,2 s. La variante de tres
  actualizaciones consumió ~23,35 s de Core y ~38,8 s desde el navegador.
  Esto **no** identifica una única causa ni separa completamente clasificación
  C1, bloqueo serializado, n8n, modelo y presentación. Se necesita una traza
  de etapas con marcas coherentes para medir el sobrecoste de C4. No se
  cambió la arquitectura de concurrencia ni se eliminó Luna.

**Situación:** caso C4 real de identidad y replay desplegado comprobados,
frontera anónima de Cloudflare comprobada; **APP E2E NOT VERIFIED** como
aceptación completa hasta poder verificar escritura parcial post-C4,
reintento iniciado desde UI si existe ese affordance y autenticación externa
real. PROD y datos personales sin tocar.

## Reproductor aislado de parcial post-escritura (23-10-2026)

- En `tests/runtime/test_c4_isolated_partial_real_core.py` se reutiliza el
  escenario **general F14**, con respuestas auténticas grabadas del proveedor
  en `benchmarks/application_router/hybrid_remaining_diag_20261013/F14.json`;
  la llamada al proveedor **NO** se repite. El Core/Writer real procesa el
  texto sin cambios en un **vault temporal nuevo** con notas sintéticas.
- Se induce solo en el proceso pytest una excepción del **readback posterior
  a la mutación**. El primer hecho queda físicamente persistido en Markdown,
  el dependiente se bloquea y Core devuelve `partial / CANNOT_ANSWER`, un ID
  afectado `date:2026-10-03` y una etapa fallida
  `candidate.postwrite_verification`. **No se ha modificado código Core para
  introducir un interruptor de errores**, ni DEV habitual o PROD.
- RuntimeComposition consume el resultado real por el guard E3 actor-scoped,
  proyecta C4 `status=partial`, `write_evidence=SOME` y orientación
  `UNKNOWN / EXPLAIN` para la causa no reconocida (no inventa diagnóstico).
  `scripts/odyssey_c4_isolated_route_renderer.mjs` ejecuta el **routeCode
  verdadero** de n8n extraído de la fuente y valida su respuesta con
  `odyssey_web/client.js`: estado `partial`, mensaje «ha guardado parte de
  la información», nota afectada disponible en snapshot, **sin prometer que
  toda la solicitud se completó** ni permitir reintento automático.
- Se reenvía el mismo request ID sobre **el mismo runtime y almacén E3
  aislados**. `delivery_replayed=true`, el escritor y las llamadas congeladas
  del modelo siguen con **una única ejecución**, el Markdown original no
  cambia y no se añade otro hecho. El test está incluido en el gate
  transversal `conversation_front_door_contract`; pytest focalizado PASS.
  **Gate global ejecutado tras el cambio: 2.021 Python + 199 JavaScript PASS,
  12 grupos**, artefactos `/tmp/odyssey-c4-isolated-partial-global-20261023.json`
  y `.log`. La presentación con la causa `UNKNOWN_FAILURE` usa la plantilla
  de causa desconocida de C4, sin inventar «reformular» ni una causa temporal.
- Límite explícito: aunque este test une **Core físico → E3 → C4 → n8n JS
  auténtico → validador del navegador**, usa proveedor histórico/fijado y no
  navega por una sesión real de Chromium con n8n desplegado. Por tanto,
  **NO sustituye una aceptación E2E pública de un parcial C4 natural**.
  Las aclaraciones `partial / CLARIFY` legítimas siguen siendo competencia
  de Core y no se reetiquetan artificialmente como error C4.

## Optimización de la interpretación C4 (24-10-2026, desplegada en DEV)

- **Problema medido:** para una causa **conocida y verificada por Core**, la
  tabla `odyssey_runtime/conversation_error.py::_REASON_KIND` ya fija de manera
  inequívoca `guidance_kind/hint`, y `workflows/odyssey-online.ts` valida la
  misma relación. Antes, además se llamaba a `OpenAIConversationGateway.explain_error`
  **dentro del bloqueo de ejecución**, aunque la salida del modelo solo podía
  coincidir con esa tabla o descartarse. El proveedor añadía latencia y coste
  sin poder cambiar la presentación autorizada.
- **Solución sin modificar semántica ni prompt:** `RuntimeComposition` mantiene
  `conversation_error_guidance_enabled` y separa de él
  `conversation_error_model_advisory_enabled=False`. El camino normal devuelve
  la misma interpretación cerrada directamente tras validar el recibo Core;
  **cero llamadas adicionales a Luna por C4**. Se conserva el modo de
  comprobación por modelo con
  `ODYSSEY_CHAT_C4_MODEL_ADVISORY_ENABLED=1`, pero solo cuando además están
  activos **C3 y C4** y `ODYSSEY_DEPLOYMENT_ENV=DEV`; C4 por sí solo sigue
  dando orientación determinista, sin activar inadvertidamente C3. Incluso
  en el diagnóstico, un consejo diferente de la
  categoría verificada se descarta y jamás autoriza guardar o reintentar.
  C1/C2/C3, el Planner y las llamadas de resolución de identidades no cambian.
- **Verificación:** prueba aislada actor-scoped/E3 con `partial`, `SOME` y
  modelo espía: orientación exacta y replay idéntico tanto con modo normal
  (0 llamadas a `explain_error`) como con diagnóstico opt-in (1 llamada,
  resultado malicioso ignorado, 0 en replay). Reproductor Raspberry
  `python -m scripts.odyssey_chat_c4_perf_gate` contra el mismo runtime con
  proveedor **simulado** de retardo fijo 180 ms: mediana **2,1 ms**,
  p95 (nearest rank) **5,0 ms**, cero llamadas al proveedor; con
  `--model-advisory`: mediana **182,4 ms**, p95 **546,2 ms**, siete llamadas.
  Los p95 incluyen tres solicitudes solapadas y bloqueo serializado. Archivos
  `/tmp/odyssey-c4-optimized-default-perf.json` y
  `/tmp/odyssey-c4-optimized-advisory-perf.json`. No son medidas con Luna real;
  la anterior campaña de seis errores con Luna (1,4–8,4 s observados)
  permite estimar el coste evitado por C4, no una ganancia total garantizada.
- **WorkSession:** se conserva `resolve_existing_entity` sin shortcuts ni
  umbrales nuevos. La etapa DEV real `tasks.work_session_resolution` costó
  ~12,2 s, pero incluye búsqueda exacta, semántica y posible decisión
  contextual; los recibos no desglosan esa etapa. No está demostrado qué
  subpaso domina y es **incorrecto reducir candidatos o saltarse el
  razonamiento contextual** sin verificar identidad y ambigüedad. El siguiente
  análisis debe desglosarla en vault sintético con instrumentación acotada y
  comparar exact, sin candidatos, candidatos ambiguos y resultado positivo.
- **WorkSession, perfilado seguro adicional:** `/tmp/odyssey_work_session_safe_profile_20261024.json`
  desglosa cuatro caminos del mismo resolver genérico sobre notas exclusivamente
  sintéticas, indexador fake y contextualizador fake con retraso impuesto de
  180 ms. Resultado: identidad exacta ~0,82 ms / **0 llamadas contextuales**;
  sin candidatos ~0,14 ms / **0 llamadas contextuales**; candidato semántico
  ~181,35 ms / **1 llamada contextual simulada**; ambigüedad de alias
  ~183,32 ms / **1 llamada contextual simulada**. La búsqueda exacta y
  semántica local fue submilisegundo **solo en estas fixtures**; no permite
  atribuir los 12,2 s observados en DEV a Luna porque el indexador y el
  modelo reales no estaban cargados. Se conserva la decisión contextual para
  evitar confusiones entre entidades. Perfil de producción sin privados y
  sin escrituras todavía pendiente.
- **Revisión independiente del commit `add3814`** detectó un defecto
  de adopción (P2): activar diagnóstico C4 sin C3 marcaba el modo como
  habilitado, pero no había gateway. En vez de crear uno nuevo que pudiera
  activar C3 inesperadamente, ahora el opt-in exige también C3. Las seis
  combinaciones relevantes de DEV/PROD/C3/C4 se verifican en pruebas.
  Resultado de revisión: **hallazgo corregido**, no una aprobación de los
  cuatro auditores sobre este nuevo commit.
- **Gate transversal de código corregido:** **2.029 Python + 199 JavaScript PASS**,
  12 grupos; `/tmp/odyssey-c4-opt-reviewed-gate-20261024.json` y `.log`.
- **Adopción en DEV (24-10-2026):** `75404428e085b70b3dbce0c29a972b50af3a9bb3`
  desplegado solo en DEV por el procedimiento existente, tras CI independiente
  **PASS** (`40032888073`), segunda revisión independiente sin nuevos hallazgos,
  backup SHA256 del estado/notas (~2,3 MB) y n8n (~113 MB), rollback conservado
  en `a75685252c666609d0f2b9f3880ec357c2d87753`. Frontend, runtime,
  marcador y n8n coinciden; DEV y PROD health HTTP 200. Ninguna configuración
  de red, credenciales o PROD fue modificada.
- **Chromium con aplicación DEV auténtica (proxy local de prueba actor-bound,
  NO Cloudflare Access externo):** un usuario sintético envió por el formulario
  una instrucción para iniciar WorkSession sobre una tarea inexistente
  `C4EnsayoRapidez241026`. Fue **`needs_attention`** con
  `WORK_SESSION_TASK_UNRESOLVED`, `CANNOT_ANSWER`, `write_evidence=UNKNOWN`,
  `SPECIFY_IDENTITY/ASK_USER`; el navegador mostró la explicación esperada y
  la recuperó tras recargar. Runtime/n8n y modelo de clasificación reales,
  sin segunda llamada Luna por C4 (`MODEL_ADVISORY` desactivado).
  **37,890 ms observados** desde el envío en Chromium, frente a **41,649 ms**
  de la muestra anterior; los mensajes, historia y carga difieren, de modo
  que **NO es un A/B controlado ni acredita un ahorro fijo de 3,8 s**.
  El recibo de Core registró **22.747 ms** frente a ~27.600 ms históricos;
  `tasks.work_session_resolution` tardó **8.851 ms** frente a 12.184 ms
  anteriores, por lo que **WorkSession sigue siendo el cuello de botella**.
  Las tres advertencias genéricas del proxy de ensayo aparecieron también
  en la prueba anterior; la prueba de UI terminó PASS, sin errores JS,
  pero no se atribuye ni se ignora ese ruido sin más diagnóstico.
- **Integridad:** SHA256 combinado del contenido de **166 Markdown** idéntico
  antes del despliegue, antes del navegador y después del navegador; ninguna
  mutación accidental. Copias y resultados en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-optimized-dev-adoption-20261024/`;
  logs `deploy.log`, `optimized-browser-e2e.log`, `backup-sha256`, huellas de
  vault y captura de Chromium. RAM disponible ~1,5 GiB, swap usado ~738 MiB,
  temperatura ~48,5 °C (instantánea posterior, no pico).
- **Pendientes:** el resultado aislado de `partial / SOME` sigue probado por
  Core físico, E3, n8n JS y browser-validator, pero NO en Chromium público
  sobre un fallo parcial natural con Luna real; sesión Cloudflare Access
  externa autenticada, trazas detalladas de WorkSession y **aprobación formal
  de los cuatro auditores sobre el SHA desplegado** siguen pendientes.
  **No promover a PROD.**

## Diagnóstico seguro de WorkSession (24-10-2026, SOLO FUENTE)

La aceptación DEV de `7540442` mostró `tasks.work_session_resolution` a
**8.851 ms**, con otra muestra de **12.184 ms** y resoluciones de otras tareas
sintéticas en **23, 59 y 61 ms**. Estos tiempos son etapas completas, no
una separación de consulta local, embedding y razonador contextual. No está
justificado saltar la validación semántica ni fijar un umbral de confianza.

- Core `resolve_existing_entity` admite ahora un `SpanRecorder` opcional que
  mide `exact_lookup`, `semantic_search` (incluye embedding e índice),
  `candidate_validation`, `relationship_context`, `provider_evidence`,
  `contextual_provider` y `decision_validation`. El resolvedor conserva
  íntegramente su selección, candidatos, límites, respuesta y excepciones.
  Cada subetapa registra **nombre cerrado, estado, desplazamiento temporal y
  duración**; ante una excepción marca el span fallido sin ocultar la causa.
  No registra texto fuente, títulos, IDs, puntuaciones, contenido de candidatos,
  prompt, respuesta del modelo ni credenciales.
- La composición de Tasks lo inserta **solo** si
  `ODYSSEY_DEPLOYMENT_ENV=DEV` **y**
  `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED=1`. No hay llamadas extra
  a proveedor, escrituras nuevas ni cambios de reglas de identidad. Las
  mediciones cuelgan de la etapa original como **substeps nativos**; no se
  duplican los milisegundos en el tiempo total, el donut ni las coberturas.
  PROD no puede activarlo por una única bandera.
- Regresiones con notas de personas y tareas **sintéticas**: coincidencia
  exacta sin consulta semántica, ausencia de candidatos sin razonador,
  candidato semántico con resolución contextual, fallo de proveedor que
  sigue propagándose, nombres fijos, aislamiento de la proyección, conservación
  de `OperationalEvidence.total_duration_ms` y cobertura de intervalos anidados.
  Una revisión independiente detectó que se usaba inicialmente el reloj global
  en vez del reloj inyectado del `SpanRecorder`; corregido y cubierto con
  un reloj determinista que verifica offsets, tiempos y etapa fallida.
  Se añaden al gate transversal de Work Sessions; no requieren IA de pago.
  Gate global tras la corrección: **2.051 Python + 199 JavaScript PASS**, 12
  grupos (`/tmp/odyssey-worksession-reviewfixed-gate-20261024.json` y `.log`).
  La segunda revisión independiente del diff con la corrección del reloj
  terminó **sin hallazgos accionables**; no sustituye la futura auditoría
  formal de los cuatro roles de la etapa completa.
- **Estado final 24-10-2026:** instrumentación de `7cade85566d536f32abf74075aa186e41d9479e1`
  **desplegada solo en DEV**, revisada y CI `40067639565` aprobado.
  Bandera `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED=1` **habilitada
  solamente durante las dos pruebas** y después retirada con reinicio de
  runtime, salud DEV/n8n/PROD HTTP 200. No se modificaron reglas de identidad,
  modelo, prompt ni configuración de PROD. **No promover a PROD.**

### Aceptación desde la app y aislamiento del arranque en frío (24-10-2026)

- **Precondiciones:** fuente limpia fijada en `7cade85`, gate transversal
  **2.051 Python + 199 JavaScript PASS**, CI GitHub `40067639565` success,
  revisión independiente detectó fallo de reloj inyectable y su segunda
  revisión tras corregirlo no tuvo hallazgos accionables. Antes de desplegar,
  se detuvieron solo servicios DEV y se guardaron **backups verificados SHA256**
  del vault/state (~2,3 MB) y volumen de n8n (~113 MB) en
  `/home/ragdehl/projects/.odyssey-agent-runs/worksession-timing-dev-adoption-20261024/`.
  **Rollback**: `75404428e085b70b3dbce0c29a972b50af3a9bb3`.
- **Prueba usuario real desde Chromium ARM64 móvil → app desplegada → n8n
  auténtico → proveedor → Core/E3 → recibo → navegador y recarga** usando
  una petición sintética de WorkSession sobre una tarea inexistente,
  sin autorizar su creación. Proxy localhost restringido con cookie de prueba;
  **no** se probó autenticación pública Cloudflare Access. Dos ejecuciones
  secuenciales con IDs nuevos, ambas `needs_attention`, código
  `WORK_SESSION_TASK_UNRESOLVED`, `write_evidence=UNKNOWN`, consejo
  `SPECIFY_IDENTITY/ASK_USER`, UI correspondiente y recuperación tras recarga.
  El contenido **de los 166 Markdown fue idéntico antes/después/tras retirar
  la bandera**, comprobado con SHA256. Los logs del proxy conservaron 2–3
  avisos de peticiones canceladas; no invalidaron la aceptación del flujo.
- **Recibo en frío** (primera llamada sin proceso ONNX previamente cargado):
  Chromium **44.803 ms**; Core **30.038 ms**; WorkSession **17.473 ms**.
  Subetapas: `exact_lookup` 67,5 ms; `semantic_search` **14.957,4 ms**;
  `candidate_validation` 1,3 ms; `relationship_context` 403,0 ms;
  `provider_evidence` 1,4 ms; `contextual_provider` 2.042,2 ms.
  Cobertura de intervalos WorkSession 99,997 %.
- **Recibo en caliente** (mismo runtime, proceso de embeddings local activo;
  nueva petición autenticada de prueba): Chromium **28.111 ms**;
  Core **21.161 ms**; WorkSession **1.992 ms**. Subetapas:
  `exact_lookup` 102,0 ms; `semantic_search` **153,3 ms**;
  `candidate_validation` 1,4 ms; `relationship_context` 402,9 ms;
  `provider_evidence` 1,6 ms; `contextual_provider` 1.330,2 ms.
  Cobertura de intervalos 99,964 %.
- **Interpretación y límite importante:** `ODYSSEY_EMBEDDING_SUBPROCESS=1`
  y `ODYSSEY_EMBEDDING_IDLE_SECONDS=900` ejecutan FastEmbed en un proceso
  local reutilizable. El proxy de pruebas **ignoraba `presence`**, por lo
  que la primera solicitud cargó el worker de embeddings bajo demanda, y la
  segunda reutilizó el worker caliente. `semantic_search` incluye IPC,
  posible carga del modelo, cálculo de embedding y consulta SQLite: los datos
  **sugieren fuertemente** arranque en frío como factor dominante, pero no
  separan esos subcostes ni prueban el precalentamiento normal de una pestaña
  autenticada externa. No usar una comparación de dos solicitudes como p95.
  No se eliminan llamadas contextuales ni se altera selección de candidatos.
- **Cierre seguro:** tras ambos tests se retiró el drop-in temporal de
  `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED`, se recargó systemd y
  reinició solo runtime DEV. La comprobación inmediata coincidió con un
  instante de arranque (socket aún no listo); comprobación posterior: runtime,
  n8n y PROD **HTTP 200**, source/marker DEV `7cade85`, drop-in ausente y
  flags de unidad sin diagnóstico, backup SHA256 válido, notas inmutadas.
  No se desplegó ningún cambio en PROD.
- **Siguiente prioridad:** investigar los costes de Core restantes y medir
  el precalentamiento en una sesión Cloudflare Access externa autorizada. Las
  verificaciones con proxy local, tiempos de worker y SQLite se documentan a
  continuación; no autorizan por sí solas un cambio en RAM, TTL o modelo.

### Verificación real del precalentamiento sin escrituras (24-10-2026)

**La funcionalidad ya existía; no se necesitó código nuevo ni redespliegue.**
En el marcador DEV `7cade85566d536f32abf74075aa186e41d9479e1` y con
`ODYSSEY_EMBEDDING_SUBPROCESS=1`, el frontend `odyssey_web/app.js` carga
asíncronamente `presence.js`, que avisa `active` al abrir y `inactive` al
cerrar la pestaña. El workflow `odyssey-online.ts` autentica y reenvía a
`/conversation/presence`; `RuntimeComposition.embedding_presence` solo lo
acepta en DEV y delega al adaptador aislado de ONNX. En una sesión normal el
primer aviso no debe bloquear la hidratación ni autorizar escrituras.

- **Chromium móvil, frontend desplegado real, n8n y runtime reales:** un proxy
  localhost con **cookie de prueba** limitó las operaciones a `presence` y
  una lectura de conversación; **no permitió `/api/request` ni mutaciones**.
  La sesión abrió el Chat y emitió `active` a los **129 ms**, con HTTP 200 y
  `{ok:true}` de n8n/runtime; el proceso worker apareció a los **496 ms**.
  Su RSS alcanzó **~651 MB** a los **5.547 ms**. Tras cerrar la pestaña,
  llegó `inactive` con HTTP 200 a los **5.555 ms**. Que el RSS creciera no
  significa por sí solo que ONNX estuviera listo exactamente en ese instante.
  `externalCloudflareAuth=false`: **no** se certificó autenticación pública
  desde Internet. Hubo un aviso del proxy de prueba de una petición auxiliar,
  sin incidencia sobre las dos respuestas de presencia. La prueba no envió
  ningún mensaje al modelo y no modificó Markdown.
- **Medición local, solo entradas sintéticas, modelo cacheado offline:**
  creación de `FastEmbedTextEmbedder` **4.398 ms**; primer
  `embed_queries` **86 ms**, segundo/tercero **23 ms**; lectura SQLite de las
  **31 filas del índice de tareas** **6,8 ms** y cálculo vectorial sobre
  estas filas **1 ms**. Dos consultas completas en índice ya caliente
  ~**22 ms**. Estas medidas no son del recorrido browser→Core.
- **Worker aislado real, nueva instancia, sin proveedor ni índices privados:**
  arranque + precalentamiento mediante el protocolo privado `warm`:
  **4.624 ms**; primera inferencia una vez listo: **73 ms**, segunda **68 ms**.
  En ninguno de estos tests se hizo descarga de modelos ni llamadas externas;
  el modelo se cargó de la caché local en un proceso descartable. No se
  imprimieron IDs, títulos, candidatos o textos de notas.
- **Interpretación:** el efecto **frío 14.957 ms vs caliente 153 ms** en la
  etapa `semantic_search` de WorkSession está bien sustentado. La construcción
  del modelo y del proceso explica varios segundos; **no se puede atribuir
  cada uno de los otros segundos** sin un perfil conjunto bajo idénticas
  condiciones de carga, caché, memoria y concurrencia. Tampoco se ha probado
  que el cliente conectado por Cloudflare tenga el mismo tiempo de prewarm
  que el proxy de prueba. La latencia de la aplicación sigue teniendo
  otros tramos relevantes aun con ONNX caliente.
- **Retención y cierre:** `idle_seconds=900` mantiene el worker cargado hasta
  el plazo de gracia después de la última sesión. Las pruebas con worker
  sintético confirman `heartbeat`, `inactive`, expiración de pestañas perdidas
  y liberación del proceso al vencer el periodo de inactividad; esta prueba
  de navegador **no esperó 900 segundos** para verificar el reaper real.
  No se cambió el TTL ni se volvió permanente el uso de ~650 MB.
- **Evidencias:**
  `/home/ragdehl/projects/.odyssey-agent-runs/worksession-timing-dev-adoption-20261024/dev-presence-browser-acceptance.log`,
  `benchmark-onnx-readonly.log`, `benchmark-worker-warmup.log`, con scripts
  transitorios fuera del Git. Los SHA256 combinados de los **166 Markdown**
  permanecieron idénticos en ambos ensayos. DEV y PROD no han sido
  modificados, ni se han cambiado tokens o permisos.

### Investigación de latencia total con ONNX caliente (24-10-2026; solo lectura)

**Ningún cambio de modelo, prompt, validador o deploy.** Se releyeron **los
recibos sintéticos ya existentes** en DEV (`7cade85`) sin extraer textos,
IDs de notas, prompts ni identidad y se inspeccionó el código activo.

El recorrido `web-19d3335f-...` ya registrado tardó **28,111 s desde Chromium**;
`OperationalEvidence.total_duration_ms` de la ejecución Core fue **21,161 s**.
Las etapas declaradas por Core/P4 fueron:

| Etapa | Tiempo de la ejecución caliente |
|---|---:|
| `application.router` (modelo `gpt-6-luna`, low) | 7,759 s |
| Primer `candidate.scope_prewrite` | 1,936 s |
| Segundo `candidate.scope_prewrite` | 2,063 s |
| `tasks.interpretation` | 2,152 s |
| `tasks.work_session_resolution` | 1,992 s |
| Tiempo de Core no atribuido a esas etapas | ~5,259 s |

**Los dos revisores de alcance no son una repetición involuntaria.** En la
rama *Tasks-only*, `WholeSourceLightExecutor._execute_source` ejecuta primero
un auditor de alcance de `gpt-5.6-luna`; si confirma una sola operación, el
modo de lote habilitado en DEV requiere una **segunda atestación independiente**
con `gpt-6-luna`, recibiendo ambos el mensaje original y no la decisión del
otro. Este contrato evita perder una segunda acción o convertir una transición
de WorkSession en CREATE. Suprimir un revisor o hacer que uno copie la salida
del otro sería una regresión de seguridad. Ejecutar ambos en paralelo **sin
condición** anticiparía gasto en solicitudes ya rechazadas, además de cambiar
orden y concurrencia; requiere diseño y ensayos específicos antes de plantearlo.

**Antes de empezar Router hay otra llamada distinta a Luna**: el clasificador
conversacional `C1` de `evaluate_conversation_entry` decide CHAT / CONTEXT /
ROUTER, sin seleccionar capacidades, entidades ni autorizar escrituras.
Después de ROUTER, la ruta P4 decide Core / Tasks / Events. En los checkpoints
persistidos (resolución de timestamp de **1 segundo**) transcurrieron:

| Intervalo de checkpoints | ONNX caliente | ONNX frío | Muestra DEV anterior |
|---|---:|---:|---:|
| `starting` → `routing.started` | 6 s | 14 s | 8 s |
| `routing.started` → `routing.ready` | 8 s | 3 s | 2 s |
| `routing.ready` → `action.delegate.started` | 5 s | 4 s | 6 s |
| `action.delegate.started` → `finalizing` | 5 s | 20 s | 11 s |

El primer tramo **incluye** C1, acceso a conversación/checkpoints y preparación
local, por lo que 6 s **no son una medida pura de Luna**. El segundo coincide
con Router y el tercero con dos validaciones de alcance. Estos intervalos no
son sumandos exactos de `OperationalEvidence` porque los checkpoints comienzan
antes y sus timestamps tienen resolución de un segundo.

La variabilidad es sustancial: Router fue ~2,49–2,53 s en dos recorridos
anteriores y **7,76 s** en el caliente. El perfil local sin red de
`OpenAITaskInterpreter.from_environment()` con **clave dummy** (sin proveedor)
dio ~1,09 s en la primera construcción del SDK y ~1 ms en las siguientes,
lo que **no justifica atribuir cinco segundos siempre a inicializar el SDK**.
En la muestra caliente hubo ~5,26 s de Core no atribuidos a las cinco etapas,
pero el recibo actual carece de intervalos completos para localizar ese
residual; no confundirlo con los ~6,95 s de diferencia entre Core y Chromium,
que contienen C1, n8n, almacenamiento y recorrido HTTP/UI.

**Orden recomendado de investigación:**

1. Instrumentar opcionalmente en DEV, sin contenido ni IDs, los tiempos de
   clasificación C1 y los límites de `WholeSourceLightExecutor` (preparación
   anterior a delegar, entrada/salida de `task_delegate` y finalización).
   Registrar inicio/fin monotónicos reales y proyección anidada para no
   contabilizar dos veces los intervalos; no cambiar semántica.
2. Medir en varias solicitudes sintéticas con modelo real **solo si se concede
   un presupuesto acotado**, porque una ejecución tiene variación relevante.
   Separar latencias de n8n y UI de las etapas del runtime.
3. Mantener las dos atestaciones de cardinalidad, el clasificador C1 y el
   Router P4 hasta demostrar una alternativa que preserve intención de
   escritura, completitud multiactividad, exact source, negativa, referencias
   ambiguas, idempotencia y replay. Cualquier cambio de prompt/modelo debe
   pasar por `odyssey-llm-stage` y evaluación real, no solo el gate determinista.

**Resultado:** el siguiente foco no es WorkSession ni ONNX caliente, sino el
coste de decisiones lingüísticas **C1 + Router + dos atestaciones**, y unos
intervalos no atribuidos que requieren telemetría más fina antes de optimizar.
DEV, PROD y notas no se modificaron en esta investigación.

### Diagnóstico optativo de la ruta caliente C1/P4/Tasks (24-10-2026, fuente y DEV)

La investigación anterior identificó el intervalo `starting → routing.started`
(~6 s en un caso caliente), sin separar clasificación C1 de preparación. También
faltaba distinguir si el tiempo restante de P4/Tasks estaba dentro de la
llamada efectiva al delegado. Se ha añadido **observabilidad opcional y
sin semántica nueva**, reutilizando la composición y el `WholeSourceLightExecutor`
existentes, sin modificar prompts, modelos, contratos de Core/E3 o rutas n8n:

- `odyssey_runtime.dev_hot_path_diagnostics.timed_dev_hot_path` mide
  exclusivamente las etapas `conversation.classify` (primera llamada C1),
  `conversation.entry` (incluye carga de estado y hasta otras llamadas si se
  selecciona CHAT/CONTEXT), `tasks.delegate` (Tasks + resolución, sin atestaciones
  previas) y `runtime.finish_product` (proyección/recibo del resultado en la
  ruta normal). Las primeras dos **se anidan** y no deben sumarse dos veces.
  `tasks.delegate` contiene `tasks.interpretation` y `tasks.work_session_resolution`,
  no se deben sumar como pasos independientes del tiempo de delegación.
- **Doble activación DEV obligatoria:** `ODYSSEY_DEPLOYMENT_ENV=DEV` y
  `ODYSSEY_HOT_PATH_TIMING_ENABLED=1`. Desactivada por defecto en todos los
  despliegues y no activable en PROD aunque alguien defina solo la segunda
  variable. El resto de caminos conserva resultados, excepciones y autorización.
- Salida en `ODYSSEY_RUNTIME_ROOT/hot-path-timing.jsonl`, con archivo regular
  `0600`, `O_NOFOLLOW`, tamaño limitado, ruta validada fuera de `/data/odyssey`;
  solo `request_digest=sha256(id)[:16]`, etapa de vocabulario fijo, milisegundos
  redondeados y bandera de fallo. No registra mensaje, texto, notas, IDs
  canónicos, actor, respuesta/prompt de IA, contadores privados ni secretos.
  El fichero es **diagnóstico**, no autoridad de ejecución, historial ni UI.
  Un error de escritura del diagnóstico no interrumpe ni reintenta una acción.
- Regresiones sintéticas: desactivación PROD/sin bandera, lista blanca,
  `NaN`, bloqueo de enlaces simbólicos, permisos `0600`, no filtración de texto,
  fallo del delegado y conservación de rutas CHAT/ROUTER y Task. Se incluyen en
  el gate transversal existente. **25 pruebas específicas PASS** y gate global
  **2.056 Python + 199 JavaScript PASS**, 12 grupos
  (`/tmp/odyssey-hotpath-source-gate-20261024.json`, `.log`); revisión
  independiente **sin defectos accionables** en
  `/home/ragdehl/projects/.odyssey-agent-runs/hotpath-c1-tasks-20261024/independent-review.txt`.
  CI independiente del commit `02daa74` completó **PASS** (ejecución
  `40097489239`). La adopción DEV y el E2E se verificaron por separado.

**Adopción DEV acotada, 24-10-2026:** backup verificable SHA256 de vault/estado
(2,3 MB) y volumen n8n (113 MB), rollback fijado en `7cade85`; `odyssey-dev
deploy` de SHA completo `02daa747ff77e9b09e5f27692c7ae9eaf8dee2b7` con
runtime/n8n saludables, identidad de flujos `MATCH` y rutas públicas `MATCH`.
Cuatro mensajes sintéticos enviados **desde el formulario en Chromium** a n8n
DEV, proveedor/modelo real, runtime y respuesta visible con persistencia tras
recarga; dos sesiones de navegador, tres casos iniciales y una repetición de
Tasks. Sus tiempos UI fueron **13,97 / 31,71 / 33,85 / 57,73 s**.
Spans privados asociados por digest, en ese orden:

| Caso | C1 classify | conversation.entry* | Tasks delegate | finish_product |
|---|---:|---:|---:|---:|
| Chat social | 4,22 s | 7,68 s | no aplica | no aplica |
| WorkSession inexistente (1) | 2,05 s | 2,07 s | 14,86 s | 0,018 s |
| Corrección/consulta de sesión | 7,24 s | 7,26 s | no aplica | 0,364 s |
| WorkSession inexistente (2, proceso caliente) | 6,63 s | 6,64 s | 4,63 s | 0,050 s |

* `conversation.classify` está **incluida** en `conversation.entry`; no sumar
sus tiempos. Descenso del delegado entre las dos muestras compatible con
precarga ONNX, **no causalidad demostrada**. La solicitud total de 57,73 s
incluso con delegado 4,63 s demuestra un intervalo grande aún no explicado
por estas cuatro sondas, fuera de Tasks: comprobar Router, atestaciones,
Core/n8n/red y UI antes de cambiar prompts o omitir validaciones.

Vault DEV: **166 Markdown**, huella SHA256 agregada de contenido/ubicaciones
**idéntica antes/después** de los cuatro envíos. Log `hot-path-timing.jsonl`
solo digest/etapa/tiempo/error y modo `0600`; ningún span fallido. El test
Chromium marcó `pass=true`, pero el proxy local restringido anotó tres errores
no caracterizados por sesión (`proxy_error:Error`), por lo que **no equivale**
a aceptar la ruta externa Cloudflare autenticada ni todos los E2E C4. El
interruptor temporal fue **retirado** y el runtime DEV reiniciado saludable;
PROD salud HTTP 200 e intacto. Evidencia operativa en
`/home/ragdehl/projects/.odyssey-agent-runs/hotpath-c1-tasks-dev-adoption-20261024/`.
**Siguiente paso:** instrumentación DEV de tramos faltantes sin contenido ni
identificadores, especialmente P4 y ambas atestaciones; recopilar varias
muestras comparables y conservar las dos comprobaciones independientes.
No hacer optimizaciones semánticas a partir de cuatro casos solamente.

### Segunda resolución del residual P4 y n8n (24-10-2026, fuente)

Objetivo acotado: distinguir el tiempo del Router, cada una de las dos
atestaciones de alcance Tasks y el tiempo del P4 completo antes de atribuir
el intervalo de la interfaz. **No se altera la semántica**: mismo proveedor,
contratos, independencia de revisores, validación de fuentes y E3 Writer.

- En el mismo archivo privado de diagnóstico y bajo la misma doble bandera
  exclusiva de DEV, se admiten `p4.source` (envoltura global de `_execute_source`
  incluidos checks locales), `p4.router` (llamada Router),
  `p4.task_scope_primary` (primera atestación no precomprobada) y
  `p4.task_scope_independent` (segunda atestación realmente ejecutada).
  Las sondas son **anidadas**: `p4.router`, las atestaciones y
  `tasks.delegate` están contenidas en `p4.source`; no sumarlas al total.
  Si una ruta prevalidada o un rechazo no ejecuta determinada etapa, no
  debe generarse un valor cero ficticio.
- Regresiones específicas de no filtración/errores/proveedor y dos
  atestaciones **7 PASS**; gate transversal **2.058 Python + 199 JS PASS**,
  12 grupos (`/tmp/odyssey-p4-phase-timing-gate-20261024.json`); revisión
  independiente `codex exec review --uncommitted` **sin hallazgos accionables**
  (`/home/ragdehl/projects/.odyssey-agent-runs/p4-breakdown-dev-adoption-20261024/independent-review.txt`).
- La medición exterior browser→n8n y la presentación UI se recogerán en un
  harness Chromium sintético restrictivo, sin añadir telemetría a n8n/PROD:
  intervalos de muro de n8n HTTP y botón→respuesta UI, evitando registrar
  cuerpos, nombres, entidades y secretos. `n8nRoundTripMs` puede contener
  Core/IA y nunca se suma a `p4.source`. Tampoco demuestra Cloudflare externo.

**Adopción y ensayo REAL, 24-10-2026:** fuente `050f26f6ce9330bbb7c694fdf8b21db2feb067ac`, CI `40100600431` **PASS**;
backups SHA256 verificados de vault/estado (~2,4 MB) y volumen n8n (~113 MB),
rollback `02daa74`. Desplegado en **DEV** con checkout, marker, runtime/n8n y
rutas `MATCH`. Chromium interactuó en la página real mediante proxy de sesión
sintética local, n8n y proveedor auténticos. Tres acciones por el formulario,
una Chat social y dos peticiones de WorkSession inexistente (IDs diferentes),
respuesta visible HTTP 200 y persistencia tras recarga. Tiempos observados:

| Solicitud | UI total | n8n HTTP total | C1 entry (incluye classify) | P4 source | Router | scope primaria | scope independiente | Task delegate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chat social | 13,36 s | 12,07 s | 10,44 s | — | — | — | — | — |
| WorkSession 1 | 37,89 s | 37,40 s | 2,34 s | 31,02 s | 2,99 s | 3,06 s | 3,00 s | 21,80 s |
| WorkSession 2 | 30,99 s | 30,50 s | 1,39 s | 23,22 s | 8,09 s | 2,35 s | 2,20 s | 8,76 s |

`p4.source` contiene Router, ambas atestaciones y `tasks.delegate`:
residual P4 no incluido en esas llamadas ≈**0,17 / 1,82 s** en Tasks 1/2.
Se contrastó además el **recibo E3 físico** de ambas solicitudes sintéticas,
sin exponer cuerpo o identidades: `tasks.interpretation` **10,17 / 5,56 s** y
`tasks.work_session_resolution` **11,63 / 3,20 s**; sus sumas reproducen
`tasks.delegate` (diferencia de redondeo). Los subspans más finos de
WorkSession estaban desactivados durante estas solicitudes; **no** atribuir
sus diferencias a ONNX o al modelo sin esa prueba adicional.
`n8n HTTP total` incluye C1, P4, recibo, Core/puente/otras etapas:
residual no atribuido directamente ≈**4,01 / 5,86 s** en Tasks; **no**
es una medición aislada del coste propio de n8n. Diferencia botón UI→respuesta
frente a HTTP n8n ≈**0,49 / 0,49 s** para Tasks, y 1,29 s para Chat.
El C1 aislado costó 5,36 / 2,33 / 1,38 s: está **incluido** en
`conversation.entry` (10,44 / 2,34 / 1,39 s). Las dos atestaciones
se ejecutaron realmente; no hay justificación para quitarlas. La volatilidad
del Router (2,99→8,09 s) y del delegado (21,80→8,76 s) impide atribuir
causalidad a una única optimización tras dos muestras.

Verificación: **166 Markdown sin cambio byte a byte en el hash SHA256 del
manifiesto antes/después**, log de cuatro claves fijas en modo **0600**, cero
spans fallidos; bandera temporal retirada con reinicio DEV saludable y PROD
HTTP 200. El navegador reportó `pass=true` y recarga correcta, pero el proxy
local siguió reportando tres errores accesorios `proxy_error:Error` sin causa
caracterizada y **NO** se validó sesión Cloudflare Access autenticada exterior.
No representa aceptación E2E global de C4 ni pruebas de escritura/casos parciales.
Resultados y script de navegador con controles de sesión en
`/home/ragdehl/projects/.odyssey-agent-runs/p4-breakdown-dev-adoption-20261024/`.

**Decisión respaldada:** no optimizar la UI ni eliminar atestaciones de fuente.
Siguiente diagnóstico acotado: subetapas Tasks/WorkSession con varios casos
comparables, intervalo Core↔n8n residual (4–6 s) y variabilidad de Router.
No cambiar modelo, prompts o autoridad E3 sin nueva evaluación real específica.

### Presencia auténtica del navegador y efecto en WorkSession (24-10-2026)

**Diagnóstico complementario sin cambios de código de producto ni despliegue.**
La investigación confirmó una distorsión de las últimas medidas: el
harness Chromium/n8n respondía a `presence` con `ignored_test_presence`
sin transmitir el aviso real que `odyssey_web/presence.js` envía al abrir
la aplicación. Así no se precalentaba el worker ONNX en las pruebas, pese
a estar ya implementado en el navegador auténtico.

Se reutilizó el mismo DEV desplegado `050f26f`, mismo recorrido de interfaz,
actor sintético y modelo real, permitiendo esta vez que el proxy de sesión
**reenviara `active`/`heartbeat`/`inactive` a n8n** y comprobando la llegada
de `active`. Worker local RSS al comenzar el primer envío **~584 MB**,
tras ~4,96 s de espera para el precalentamiento; RSS por sí solo no asegura
que las inferencias ya estén calientes. Dos WorkSession inexistentes enviadas
desde el formulario con IDs nuevos, HTTP 200, `needs_attention`, recarga
correcta y **166 Markdown idénticos** en la huella del vault. El proceso
runtime/servicio siguió aislado de PROD. Resultados:

| Sesión con presencia real | UI total | n8n HTTP | Task interpret | WorkSession total | WorkSession semantic_search | WorkSession contextual_provider |
|---|---:|---:|---:|---:|---:|---:|
| Primera | 28,33 s | 27,82 s | 8,62 s | **2,73 s** | 0,540 s | 1,71 s |
| Segunda | 30,54 s | 30,12 s | 7,42 s | **1,98 s** | 0,035 s | 1,47 s |

Referencia anterior **sin presence** (otro par de solicitudes, condiciones
diferentes): WorkSession **11,63 y 3,20 s**. La reducción de la primera
muestra es compatible con eliminar buena parte del arranque ONNX, pero no
prueba causalidad ni percentiles con n=2. No se debe confundir la mejora
**ya implementada** con una nueva optimización de producto; no cambiar el
resolver ni borrar validación contextual. El coste relevante que permanece
es interpretación Tasks (~7–9 s), contextual (~1,5 s), Router y revisiones
independientes, variables por latencia de proveedor. Los recibos reales
anteriores de Tasks (`gpt-6-luna`, low effort) registran 908 tokens de
entrada y 55/107 de salida, pero no justifican cambiar prompt, modelo,
paralelismo o máximo de tokens sin evaluación semántica acotada. Como
contraprueba no facturable, la creación local del cliente OpenAI usado por
Tasks (`OpenAITaskInterpreter.from_environment`) tardó **~0,66 ms de mediana**
tras el primer arranque de importaciones (6 muestras, token ficticio,
ninguna solicitud de red); **reutilizar ese objeto por sí solo no promete
una mejora apreciable** sobre los 7–9 s de interpretación real.

**Hallazgo sobre avisos del proxy:** los tres `proxy_error:Error` de las
pruebas anteriores correspondían a solicitudes GET `/favicon.ico` no
incluidas en los activos locales del harness, no a fallos confirmados del
backend. El harness privado de investigación identificó la ruta sin
registrar payloads de usuario. El procedimiento `odyssey-dev-e2e` exige
ahora mantener el `presence` auténtico en los benchmarks de UX y distinguir
404 de recursos opcionales de errores en las solicitudes de negocio.

Se activaron únicamente durante el ensayo las banderas DEV
`ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED=1` y
`ODYSSEY_HOT_PATH_TIMING_ENABLED=1`; se **retiraron ambas y se reinició solo
el runtime DEV** con salud HTTP 200 en DEV y PROD, marcador de DEV `050f26f`
y vault sin modificaciones. Evidencia y harness controlado en
`/home/ragdehl/projects/.odyssey-agent-runs/p4-worksession-real-presence-20261024/`.
**Próximo trabajo:** optimizar el coste total de llamadas GPT solo con una
prueba de seguridad y comportamiento por idioma/negación/multitarea, y
separar los 4–6 s residuales en Core/n8n; no acelerar poniendo en riesgo
las atestaciones independientes ni la autoridad E3.

### Recuperación efectiva desde el botón de la UI, pérdida de respuesta (24-10-2026)

Ensayo de aceptación **sin cambio de producto** sobre DEV `050f26f`:
Chromium pulsó «Enviar» en la aplicación desplegada con petición WorkSession
sintética inexistente. n8n, el modelo y Core/E3 completaron la primera
petición en **26,461 s**, pero el proxy local devolvió **HTTP 503 artificial
solo al navegador, después** de recibir el HTTP 200 auténtico y un recibo
físico persistido. El navegador mostró «Reintentar»; se pulsó el control
visible. El nuevo envío conservó **exactamente el mismo request ID** y n8n
respondió HTTP 200 en **0,867 s**, en lugar de repetir la llamada al modelo.
El hash SHA256 del recibo físico fue idéntico antes/después; se observó **un
único globo de usuario** y respuesta final tras recuperar. Manifiestos SHA256
de los **166 Markdown idénticos**. Ningún error de JS observado. La sesión
sintética se confinó al proxy de DEV con allowlist de mensajes y cookie; no
se alteró Cloudflare, permisos ni PROD. Carpeta privada de evidencias:
`/home/ragdehl/projects/.odyssey-agent-runs/c4-ui-retry-acceptance-20261024/`,
especialmente `validated-retry.json`, `c4-ui-retry.log`, comprobaciones SHA256.

**Precisión importante:** la primera versión del harness esperaba el campo
interno `delivery_replayed` en el resultado **proyectado por n8n**, aunque el
contrato web actual deliberadamente no lo expone. La aserción originó un
falso negativo (la entrega sí se recuperó); una validación posterior comprobó
11 propiedades observables: ID idéntico, tiempos HTTP, recibo inmutable,
control de UI, un solo mensaje de usuario, resultado visible y vault sin
mutaciones. Esto acredita recuperación observable desde la interfaz, pero no
permite inferir un `delivery_replayed` que el navegador nunca recibió.
Tampoco acredita Cloudflare exterior o un fallo parcial natural desde Chromium.

### Cierre de revisión especializada y decisión de alcance (24-10-2026)

**Candidato de fuente auditado:** `ca0d385ae7eee9b4d21a2b6068e9719dc188f442`
(solo docs/harness desde el desplegado funcional DEV `050f26f`). El gate
oficial ejecutado por `odyssey_agent_cycle.py` dio **PASS** en cross-surface
(**2.058 Python + 199 JavaScript**), aceptación y Ruff; CI GitHub sobre el
commit de documentación `ca0d385` **success**. Copias y SHA256 de los
ensayos DEV documentados arriba siguen intactos.

**Revisión de cuatro especialidades, distinción de procedencia necesaria:**

| Especialidad | Veredicto | Registro | Observaciones |
|---|---|---|---|
| Generalidad | **PASS** | supervisor formal, ronda 1 | Una advertencia: mantener contrato de tabla código/consejo equivalente entre Python y n8n |
| Calidad | **PASS** | supervisor formal, ronda 1 | Un encabezado de estado desfasado (corregido en este cierre) y las pruebas externas conocidas |
| Pruebas | **PASS** | evaluador independiente complementario, sobre mismo SHA | Parcial natural por navegador y sesión Cloudflare externa siguen sin demostrar |
| Rendimiento | **PASS** | evaluador independiente complementario, sobre mismo SHA | Sin p95 representativo en tráfico real; observar memoria y comportamiento del worker ONNX con mayor carga |

El supervisor oficial quedó en fase **`blocked`** por reserva preventiva
de tokens tras los dos primeros PASS (211.804 consumidos frente a presupuesto
de 300.000; reservaba 105.000 para ambas tareas, quedaban 88.196). **No
se alteró el presupuesto ni se falsificaron recibos**; los dos informes
complementarios se distinguen claramente de aprobaciones registradas por
el supervisor. Evidencias en
`/home/ragdehl/projects/.odyssey-agent-runs/c4-final-dev-four-role-20261024/`
(`status.json`, `round-1/*-completed.json`, `qa-supplementary.json`,
`perf-supplementary.json`). Todos los revisores examinaron la misma fuente
funcional de cierre. Ninguno encontró un defecto bloqueante nuevo.

**Nota metodológica:** un hook genérico `pytest` de todo el repositorio
recorrió también benchmarks históricos congelados y acabó con **27 FAIL,
4.874 PASS, 80 SKIP**; no es el gate transversal canónico, que PASS y
está acotado al contrato implementado. No se retocaron esos tests antiguos,
ni se ha afirmado que toda la historia pase. El commit documental posterior
se hizo con el hook genérico `pytest` omitido y `odyssey_docs_guard.py`,
validación del esquema y `git diff --check` superados.

**Decisión:** dar por cerrado el **alcance de desarrollo funcional C1–C4
probado en DEV**, sin modificar Tasks para perseguir segundos. DEV mantiene
la versión funcional `050f26f`. No declarar aceptación end-to-end global,
ni `ready_for_user=true` del supervisor ni aprobación para promoción PROD:
quedan pendientes autenticación externa Cloudflare con sesión autorizada y
parcial C4 natural por interfaz (más métricas de carga reales si se exige
objetivo de p95). La reproducción parcial Writer+E3+n8n web aislada sí
consta, pero no se hará fault injection en el vault personal para conseguir
una demo. Estas puertas son propias de una futura promoción, no justificación
para reabrir Tasks o bloquear el diseño de la siguiente fase de notas.
