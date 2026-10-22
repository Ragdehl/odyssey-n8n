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
referencias genéricas. Revisión independiente de código y primera aceptación
real GPT→n8n→Markdown→Calendar para E6 quedan separadas. DEV permanece en
`6debe8a`; no se escribió en vault ni se hizo deploy.
