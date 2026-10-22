# E6: checkpoint incremental de composición y extensibilidad

**Objetivo**: hacer más económico conectar nuevas aplicaciones sin duplicar
interpretación, autoridad de escritura ni mecanimos de Core. E6 no es una
reescritura, no requiere nuevo servicio y no autoriza PROD.

## Baseline comprobada

- E5 DEV: `6debe8afdb614747fc89f289cca6e2136c70b865`; runtime y n8n responden 200; última revisión independiente de las cancelaciones PASS y E2E sintético real PASS. El trabajo E6 se hace en rama propia: DEV permanece exactamente en E5.
- El registro tipado `ApplicationRegistry`, `ApplicationCatalog` y `ApplicationDescriptor` ya limita las capacidades de Router; `ApplicationExecutor` y `execute_routed_request` ya aceptan ejecutores por id.
- E2 mantiene los transportes de evidencia, E3 `CanonicalMutationGate` conserva CAS, revisión, historial y readback; Writer/Markdown siguen siendo la única autoridad.
- Acoplamientos constatados: `odyssey_runtime/composition.py` y `odyssey_runtime/candidate_route_dispatch.py` registraban Task y Event con mecanismos específicos duplicados. `candidate_route_dispatch.py` contiene además políticas de herencia temporal diferentes para Task y Event, y `hybrid_group_compiler.py` construye el catálogo híbrido con `enable_tasks` y `enable_events`. La extracción de estas políticas NO está hecha en este primer corte.
- Eventos aporta ~700 líneas de reglas de ejecución/identidad y ~290 de mutaciones y no debe perder sus garantías por una refactorización superficial.

## E6.1 — Primer corte: unión única de capacidades y ejecutores

**Antes** (en los dos puntos de entrada):

```python
if "tasks" in enabled_application_ids:
    application_executors["tasks"] = execute_tasks
if "events" in enabled_application_ids:
    application_executors["events"] = execute_events
```

**Después**:

```python
application_executors = bind_registered_executors(
    application_catalog,
    {"tasks": execute_tasks, "events": execute_events},
    require_enabled=True,
)
```

El dispatcher de candidatos reutiliza la misma función en modalidad
`require_enabled=False`, preservando su error por ruta cuando la App no
tiene ejecutor. La función enlaza **solo** capacidades declaradas y habilitadas:
no importa código por string, no usa discovery de proveedores, no da
autoridad a una propuesta LLM, no cambia Core/Temporal/E3. Acepta una app
ficticia `projects` a través de `ApplicationRegistry` y
`execute_routed_request` sin tocar el ejecutor genérico.

Este corte elimina una duplicación de composición y fija un contrato de
habilitación y confianza reutilizable. NO elimina todavía las políticas
de routing particulares de Task/Event ni demuestra que Projects sea
totalmente integrable sin cambios del compilador y esquema.

## Evidencia y límites

- Tests específicos con Projects sintético: habilitación, deshabilitación,
  ids desconocidos/reservados, ausencia de handler obligatorio,
  correlación de ruta y errores acotados, y Core-only sin Apps.
- Regresión focal: 40 PASS. Primer gate transversal detectó 14 regresiones
  por pasar claves ficticias Tasks/Events a un catálogo Core-only; el enlace
  fue corregido para filtrar exactamente por las capacidades en el catálogo
  validado. Reejecución focal de las regresiones: 27 PASS.
- Después se añadió E6 como grupo permanente del gate y como evidencia del
  acceptance ledger. El sentinel del listado de grupos necesitó incluir el
  nuevo grupo y se corrigió sin reducir ninguno de los anteriores.
- Gate final ampliado: **1811 Python +181 JavaScript +7 subtests PASS**,
  130 archivos en 11 grupos; Ruff check/format PASS, integridad de contratos
  de aceptación PASS, sin mutaciones en DEV/PROD.
- Commit de implementación `9e4516a639f64fa64af2a93c4adc710ec815ea7d`; revisión independiente read-only **PASS**. El auditor inspeccionó el diff y confirmó las fronteras de catálogo habilitado, la ausencia de rutas para capacidades no registradas, el caso Core-only con catálogo vacío y la no alteración de actor, E3 y Events. Evidencia: `/home/ragdehl/projects/.odyssey-agent-runs/e6-app-bindings-source-review-20261022/findings.md`. La revisión no repitió la suite ni constituye prueba E2E DEV.
- No se han modificado datos, n8n, Runtime DEV, el vault real ni PROD.
- Próximos pasos E6.1: encapsular la validación común de source/actor y el
  contrato de evidencia tipada; NO unificar semántica de herencia de Task y
  Event si no existe equivalencia probada. E6.2: disminuir objetos Core
  construidos dentro de Apps con casos de uso/repo/puertos estrechos. E6.3:
  prueba de extensibilidad sobre una tercera app con Router híbrido y real
  E2E DEV solo después del checkpoint.


## E6.1 — Segundo corte: autoridad de ruta y cobertura temporal comunes

**Base:** primer checkpoint auditado `e2a98b5`. La validación local a
Router y el contexto original de E2 se mantienen como única procedencia.

Se añade `odyssey_runtime/scoped_route_authority.py` con:
- `ScopedRouteAuthority.verify`: confronta correlación de ruta, capability,
  source exacto en offsets del mensaje original, contexto local, actor y
  secuencia de conversación. Lo reutilizan la ruta Core/Temporal, Tasks y
  Events; una app ficticia Projects pasa idéntica comprobación de fuente.
  Anteriormente Tasks verificaba su source pero no actor/historial dentro de
  su wrapper específico. Core y Events sí lo hacían por separado.
- `missing_inherited_temporal_spans`: factoriza únicamente la comprobación
  de offsets de evidencias heredadas faltantes que duplicaban Tasks y Core.
  El proveedor `ScopedTemporalHandoff` sigue siendo quien valida la
  procedencia y resolución exacta; este cálculo NO certifica un datetime
  ni concede capacidad de escritura por sí solo.
- Las políticas NO son igualadas: Events conserva el rechazo
  `EVENT_SCOPED_TEMPORAL_EVIDENCE_UNSUPPORTED` para herencia no soportada;
  Tasks conserva su ejecución con `TaskScopedEvidence` y el rechazo si
  faltan pruebas; Core conserva su ruta normal y los propios guards.
  El dispatcher Core solo admite `core` y `temporal`.

**Pruebas:** `tests/runtime/test_e6_scoped_route_authority.py` incluye
capabilities Core, Temporal, Tasks, Events y ficticia Projects, intentos de
alteración de actor, fuente, correlación, contexto y offsets, más cobertura
Temporal compartida. Regresión focal con rutas existentes: **79 PASS**.
Gate permanente ampliado: **1830 Python +181 JavaScript +7 subtests PASS**,
131 ficheros, 11 grupos. Ruff PASS e integridad del registro de contratos
PASS (46 anclajes). Recibo local:
`/tmp/odyssey-e6-scoped-full-20261022.log`.

**Límites:** esta fase solo es verificación de ensamblaje/autoridad de
entrada. No elimina las políticas de Tasks ni Events ni interpreta
referencias genéricas. Revisión independiente focal read-only **PASS** del cambio
`e2a98b5..0eb549d`, sin defectos de seguridad o corrección encontrados;
evidencia: `/home/ragdehl/projects/.odyssey-agent-runs/e6-scoped-route-review-20261022/findings.md`.
Esta revisión no ejecutó nuevamente la suite y NO es aceptación DEV.
La primera aceptación real GPT→n8n→Markdown→Calendar para E6 sigue pendiente.
DEV permanece en `6debe8a`; no se escribió en vault ni se hizo deploy.


## E6.2 — Primer corte: caso de uso Core compartido para updates de propiedades

**Problema observado:** tanto `TaskDirectMutationService.set_completed` como
`EventMutationService.change` construían objetos genéricos
`KnowledgeUnit`, `SelectionCriteria` y `WriteTargetDecision` en cada App
y llamaban a `materialize_update` a través de E3. Dos rutas con el
mismo contrato de escritura y distintas reglas de lifecycle.

**Cambio:** `odyssey_core/prepared_property_mutation.py` introduce el caso
de uso acotado `execute_prepared_property_mutation`. Las Apps siguen
preparando el target en E3 y decidiendo si su estado admite el cambio y
qué `PropertyChange` debe aplicarse. Core prepara el objeto de escritura,
ejecuta `CanonicalMutationGate.execute_prepared`, obliga al CAS físico
original y devuelve el recibo físico + historial. El nuevo límite verifica
que el repositorio y esquema correspondan al gate que preparó el target,
que el tipo coincida con el target y comando, que request/actor/reloj
correspondan y que los cambios sean valores tipados no vacíos.

**Antes (duplicado en Apps):**
```python
unit = KnowledgeUnit(SelectionCriteria(...), "amend", changes, ...)
receipt = gate.execute_prepared(
    command, target,
    lambda _: materialize_update(unit, WriteTargetDecision(...), ...),
)
```

**Después (reutilizando Core):**
```python
receipt = execute_prepared_property_mutation(
    gate=gate, command=command, target=target,
    note_type="event", changes=changes,
    repository=repository, schema=schema,
    actor=actor, now=now, request_id=request_id,
)
```

**Fuera de alcance:** No se modifica `create_subtask`, Event CREATE,
resolución de identidad/Event title, Temporal, n8n ni el Writer general.
Tampoco se convierten las reglas de Task y Event en condiciones dentro
de Core. No hay transacción entre notas nuevas ni mecanismo paralelo de
persistencia.

**Validación local inicial:** 36 pruebas focales PASS sobre el nuevo
caso de uso, mutaciones Events+Calendar, Tasks+subtasks y E3 gate,
incluidos tokens stale, write readback, tipo incorrecto, repo/esquema ajenos
y actor/request alterados. **Gate transversal completo: 1838 Python +181 JS
+7 subtests PASS, 132 ficheros, 11 grupos; Ruff PASS y acceptance ledger
PASS (19 contratos, 49 anclajes).** Revisión independiente focal y primer
E2E sintético E6 en DEV siguen separados.


## Primera adopción funcional E6 en DEV — PASS (22-10-2026)

Código real probado: commit `b87a748f6e06028f885c38ffdb7c5b76ec13ade0`
en checkout DEV, marcador runtime y fuente al iniciar el ensayo. DEV venía
de E5 `6debe8afdb614747fc89f289cca6e2136c70b865`.
Antes de cambiar se comprobó limpieza de ambos Git, runtime/n8n HTTP 200;
se realizaron backups tar de vault/estado y volumen n8n con sus SHA256.

Recibo del orquestador:
`/home/ragdehl/projects/.odyssey-agent-runs/e6-first-dev-acceptance-20261022/orchestrator.log`.
Prueba real reutilizada contra commit efectivo en
`scripts/e5_dev_audited_mutations_e2e.py` (el prefijo del recibo es E5
por compatibilidad con el script, pero el SHA desplegado probado es E6).
Cadena: petición HTTP real → GPT/Router → n8n → Core/E3 → Markdown →
Calendar y readback. Resultado:

```json
{
  "pass": true,
  "wrong_date_cancel_rejected": true,
  "right_date_cancelled": true,
  "old_new_reschedule_correct": true,
  "no_fabricated_multi_day_event": true,
  "replay_byte_identical": true,
  "synthetic_only": true,
  "production_touched": false,
  "deployed_sha": "b87a748f6e06"
}
```

Runtime DEV y n8n verificados HTTP 200 después del ensayo; rama y checkout
DEV sin cambios locales. Dos backups retenidos; rollback Git E5 explícito.
El ensayo no autoriza PROD, no representa p95 estadístico y no ejercitó
nuevamente navegador Chromium ni la semántica de nuevas Apps Projects.
E6.2 sigue abierta para revisar oportunidades concretas de reducir
adaptadores; la E6.3 tendrá criterios medibles de nueva capacidad antes
de cerrarse. No repetir auditorías de E5/E6.1/E6.2 ya aprobadas.


## E6.3 — Tercera App integrada en el compilador híbrido (22-10-2026)

**Antes:** `execute_routed_request` aceptaba Projects como handler en un test
aislado, pero `compile_hybrid_candidate_bundle` y
`execute_candidate_routed_message` solo conectaban las Apps Task/Event.
No había contrato genérico para transportar un tercer grupo desde un
Router candidate validado hasta su executor con autoridad acotada.

**Nuevo corte opt-in, no activado en DEV:** la dataclass cerrada
`RegisteredScopedApp` (descriptor confiable + kind de candidato
admitido por Router/Core + executor invocable) sirve de registro único
de la tercera capacidad. `registered_app_index` prohíbe duplicar
IDs/kinds o reasignar las clases reservadas `task` y `event`.
El compilador acepta `registered_apps` únicamente desde la composición
confiable y selecciona esa ruta si todos los candidatos del grupo
coinciden exactamente con el kind declarado y están en estado
`candidate`. Si alguno es ambiguo o queda mezclado en un grupo con
Core, devuelve `RouterError` y no lo envía silenciosamente a Core.

El dispatcher recibe `registered_scoped_apps` por contrato tipado,
valida la ruta con `ScopedRouteAuthority` compartido de E6.1,
revalida candidate kind contra el registro y devuelve
`NEEDS_ATTENTION` ante dependencias/roles heredados cuyo transporte
semántico no existe para esta tercera App. Solo entonces ejecuta su
callback específico de aplicación y exige un recibo `ApplicationResult`.
No toca `materialization`, `CanonicalMutationGate`, ni los
mecanismos E2/E3; las Apps existentes mantienen su ejecución anterior.

**Prueba funcional sintética no escritora:** usa temporalmente el kind
Router *ya existente* `plan` como clasificación de un grupo
`projects`, sin inventar un nuevo tipo de nota ni crear permisos de
persistencia. Comprueba la secuencia **proposal → compiler →
validated bundle → dispatcher → registered scoped callback**, sin
fallback a Core, conservando fuente exacta y actor/contexto; sin
ninguna mutación de Markdown. Casos negativos: falta de registro,
clase Task/Event reservada, ID/kind duplicados, kind incorrecto,
estado ambiguo y grupo semántico mixto.

**Limitación importante:** todavía NO se ha añadido el tipo de
candidato `project` a Router y Core, ni la semántica del dominio
Projects, su schema de notas, GPT parser/prompts, interfaz ni
mutaciones propias. Esto demuestra la capacidad del mecanismo de
composición, **no una tercera aplicación de producción terminada**.
Una nueva clase de candidato requiere todavía revisión explícita
del esquema del Router/Core; no se permite descubrirla por texto de
modelo ni registrar plugins arbitrarios.

Pruebas locales nuevas: nueve casos E6.3 y regresión focal de
Tasks/Events. Evidencias de aceptación transversal y DEV se
anotarán cuando finalicen, sin anticipar su resultado.


### Revisión independiente E6.3 y corrección del bloqueo

La primera auditoría read-only del commit `74c4700` devolvió **FAIL**
por una divergencia de configuración: si el compilador omitía la App
`projects` pero el dispatcher sí la registraba, un candidato `plan`
podía compilarse como `core` y tomar una ruta distinta en vez de fallar.
Evidencia reproducible:
`/home/ragdehl/projects/.odyssey-agent-runs/e6-third-scoped-app-review-20261022/findings.md`.

**Corrección aplicada antes de promover a DEV:** el dispatcher revalida
cada grupo compilado contra la tabla confiable de tipos de candidato de
Apps registradas. Si algún candidato pertenece a una App explícitamente
registrada, exige que su `route.capability_id` sea esa App; si no,
lanza `RouterError` ANTES de la ejecución. Caso inverso (compilador
propone App pero dispatcher no la tiene) ya fallaba con validación del
catálogo. Nueva regresión:
`test_dispatcher_refuses_when_compiler_omits_trusted_app_registration`.
La corrección no cambia las rutas por defecto sin tercera App.
Primeras regresiones corregidas: **20 PASS** focales. Pendientes: suite
transversal final y revisión específica del bloqueo para aceptar E6.3.


**Regresión final después de corregir el bloqueo:** gate permanente
**1848 Python +181 JavaScript +7 subtests PASS**, 133 ficheros y
11 grupos; ledger de aceptación íntegro con **20 invariantes y
55 anclajes**, Ruff PASS. Pruebas sin efectos sobre DEV/PROD.
Fuente: `/tmp/odyssey-e6-third-app-after-review-fix.log`.
El primer FAIL de auditoría queda registrado como hallazgo corregido,
no convertido retroactivamente en PASS. Antes de adopción DEV debe pasar
la verificación independiente focal de la corrección y después el
E2E real de compatibilidad E6.


## E6.3 — Aceptación real en DEV (22-10-2026)

**Código realmente probado y desplegado:**
`7fac3eac813bc65302bb378db26fd442943864d0`.
Baseline de rollback:
`b87a748f6e06028f885c38ffdb7c5b76ec13ade0`.

- Primera auditoría de implementación: **FAIL** por discrepancia de
  registro compilador/dispatcher, donde `plan` podía ir a Core aun
  estando Projects registrado solo en el dispatcher. No se desplegó ese
  commit. Hallazgo:
  `/home/ragdehl/projects/.odyssey-agent-runs/e6-third-scoped-app-review-20261022/findings.md`.
- Reparación commit `7fac3ea` y caso regresión obligatoria.
  Revisión independiente read-only y focal del hallazgo: **PASS**;
  evidencia:
  `/home/ragdehl/projects/.odyssey-agent-runs/e6-third-scoped-app-fix-verification-20261022/findings.md`.
- Gate completo de la versión corregida:
  **1848 Python +181 JavaScript +7 subtests PASS**,
  133 archivos/11 grupos, Ruff PASS; acceptance ledger:
  **20 invariantes y 55 anclajes PASS**.
- Backups DEV vault/estado y volumen n8n con SHA256 comprobados tras
  el ensayo. Git DEV y marcador coinciden con SHA desplegado, limpias
  las ramas DEV y de desarrollo antes de documentar el resultado;
  runtime y n8n HTTP 200. Producción no modificada.
- Ensayo HTTP real y sintético con versión E6.3, ejecutando el script
  heredado `scripts/e5_dev_audited_mutations_e2e.py` (el prefijo
  de su resultado sigue diciendo E5, pero el SHA que comprueba es E6.3):
  **GPT/Router → n8n → Core/E3 → Markdown → Calendar PASS**.

Recibo reproducible:
`/home/ragdehl/projects/.odyssey-agent-runs/e6-third-scoped-dev-acceptance-20261022/orchestrator.log`
y `e2e.log`.

```json
{
  "pass": true,
  "wrong_date_cancel_rejected": true,
  "right_date_cancelled": true,
  "old_new_reschedule_correct": true,
  "no_fabricated_multi_day_event": true,
  "replay_byte_identical": true,
  "synthetic_only": true,
  "production_touched": false,
  "deployed_sha": "7fac3eac813b"
}
```

**Decisión:** checkpoint funcional incremental E6.0–E6.3 aceptado en DEV.
No autoriza PROD ni demuestra una app Projects real: siguen faltando
semántica, tipo nuevo de candidato si se requiere, schema, casos de uso,
interfaz y GPT E2E propios. Las nuevas mejoras de Clean Architecture
continúan al añadir capacidades, no mediante reescritura general.

**Medición local solo del compilador (sin GPT, 5x160 llamadas):**
mediana Core-only 0,0961 ms y mediana con tercera App registrada
0,0903 ms; están en la misma magnitud de coste y estas cifras **no**
son un p95 ni miden latencia global n8n, GPT, Core o Writer. Tampoco se
ha repetido una prueba visual Chromium en este checkpoint.
