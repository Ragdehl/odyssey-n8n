# Odyssey — reducir el orquestador a coordinación mecánica

**Tipo:** plan arquitectónico para el siguiente trabajo; **NO implementación ni aceptación de etapa**.
**Base inspeccionada:** DEV desplegado `a40237b`; refactor local posterior `e9420b3` (elimina una llamada redundante al Router, sin adopción DEV). La PR #165 (`f274000`, instrucciones y comprobación de reglas contradictorias) permanece separada. Confirmar de nuevo estos SHA y flags al empezar cada bloque.

## Objetivo vinculante

No seguir agregando caminos `if core/tasks/events/...` ni parches de frases al runtime. **Los bloques semánticos reciben el mensaje original, el ámbito de trabajo, el contexto conversacional y las evidencias relevantes por un contrato común**; cada bloque interpreta solo su dominio, usando IA si hace falta. E2/Core valida fuente, dependencias e identidad; **E3 sigue siendo la autoridad canónica de mutación**. El coordinador se limita a entrada autenticada, registro y ejecución por dependencias verificadas, entrega/replay y presentación/telemetría. No instalar otro orquestador, framework, cola, servicio, almacén ni Writer.

**Regla de diseño:** contexto semántico completo y acotado ≠ permisos ilimitados. Todos los bloques reciben el **mismo sobre original inmutable**, más las pruebas de lectura a las que están autorizados. Ninguna salida del LLM concede identidad canónica, acceso a otro usuario ni permiso de escritura.

## 1. Diagnóstico del código efectivo (revisión de lectura)

### Entrada y alternativas

`RuntimeComposition.execute_product` (`odyssey_runtime/composition.py:698-978`) posee la transacción de entrega, replay, conversación y protección prewrite; `execute` (`3030-3226`) elige motor. La composición (`6513-6525`) selecciona `WholeSourceLightExecutor` cuando `ODYSSEY_LIGHT_SOURCE_V1=1`, si no el dispatcher híbrido experimental cuando está activo, si no `execute_routed_request`. **No son tres etapas que se ejecuten consecutivamente.** El camino light está protegido contra el vault PROD (`composition.py:3805-3819`): conservar ese límite de confianza.

Los tamaños son una señal para investigar, no un objetivo en sí: `composition.py` 6863 líneas (fábrica `_build_runtime_from_environment_unlocked`: 2766), `whole_source_light.py` 3029 líneas (`_execute_source`: 792; `_execute_dependent_graph`: 618; `_execute_independent_scopes`: 299), `candidate_route_dispatch.py` 1424 líneas (`execute_candidate_routed_message`: 1166); `routing.py` 899. Hay que **reducir decisiones y rutas activas**, no dividir archivos y conservar las mismas condiciones.

### Inventario de decisiones con propietario incorrecto

| Ubicación actual | Responsabilidad observada | Propietario objetivo y mecanismo existente que reutilizar |
|---|---|---|
| `whole_source_light.py:868-1199` | Ruteo de capacidades, comprobaciones SELF, elección por combinaciones específicas Events/Tasks/Core y topología independiente/dependiente | Router emite hipótesis de source scopes; E2 valida fuente y DAG; Core valida SELF y referencias; registro de Apps identifica quien interpreta. El runtime no interpreta combinaciones. |
| `whole_source_light.py:1204-1260` | Distingue Tasks único, lote de CREATE y condiciones de delegación | App Tasks decide intención/lifecycle y entrega una operación validada. E2/Core verifica cobertura de fuente. |
| `whole_source_light.py:1260-1621` | Planificación, revisión semántica, speaker, cobertura, compilación y escritura de hechos | Core reutiliza `whole_source_compiler`, `application.execute_request`, identidades y revisión; E3 persiste. La presentación de fases lee resultados, no recalcula intención. |
| `whole_source_light.py:1623-2069` | Camino especial Core→Task, Task/Session y plurales de personas | `dependent_group_graph.py`, `source_bound_dependency.py`, prueba canónica de identidad en Core y reglas de Tasks. No algoritmo de «dos personas», «una Task» o frase familiar en coordinador. |
| `whole_source_light.py:2071-2688` | En un solo método prepara grafo dependiente, preflights y ejecuta Core, Tasks, Work Sessions, handoff, manifest y estados | **Una sola** validación del grafo en E2/Core; cada bloque prepara y valida su operación; ejecutor mecánico ordena por aristas verificadas y consume recibos E3. |
| `whole_source_light.py:2690-2988` | Valida particiones independientes y repite políticas de Tasks/Events, orden y postwrite | `independent_source_scopes.py` + grafo E2 general; registro de bloques, contratos de preflight y resultado, E3/manifest. |
| `composition.py:4946-5556`, `5686-5793` | `execute_tasks` y `execute_events` integran interpretación, lifecycle y decisiones propias dentro de la fábrica de Runtime | Adaptar las **Apps Tasks y Events existentes** como bloques de dominio registrados, sin duplicar servicios de mutación. |
| `composition.py:3785-6550` | Fábrica mezcla configuración/flags/recursos con enormes funciones anidadas de dominio | La fábrica solo inyecta dependencias y registra los bloques; implementación de dominio permanece en Core/Apps ya existentes. No borrar flags hasta probar equivalencia. |
| `candidate_route_dispatch.py:259-1424`, `routing.py:287-488`, `source_scope_compiler.py` | Caminos de orquestación alternativos, herencia ad hoc, particiones y políticas App/Temporal | Inventariar consumidores, mantener compatibilidad mientras haya uso, **retirar la alternativa sustituida** tras prueba de paridad; nunca construir una tercera variante. |

### Funcionalidades genéricas ya construidas que NO se deben rehacer

- `odyssey_core/execution_context.py`: `ExecutionContext`, `StageSpec`, `StageInput/Output`, `ContextStage`, `run_context_stage` y fusión inmutable. **Hoy P4 no construye este carrier**, mientras el dispatcher candidato sí lo hace (`candidate_route_dispatch.py:1015`). La versión actual oculta puertos no declarados y **no tiene un puerto de historial/conversación ni el ámbito original completo para cada bloque**; evolucionar el contrato existente, no inventar otro.
- `odyssey_core/independent_source_scopes.py:28` valida particiones íntegras; `dependent_group_graph.py:97` valida N:M **solo Core/Tasks**, con 2–16 grupos y al menos una dependencia; `dependent_source_scopes.py` cubre una variante estrecha. `independent_source_scopes.py` admite únicamente ciertos pares de Apps. **No existe aún un grafo neutro para cualquier App, un grupo o cero aristas**. El ejecutor convierte estos resultados en fragmentos recortados.
- `ApplicationRegistry/Catalog`, `bind_registered_executors`, `ScopedRouteAuthority` (E6): ya permiten registrar ejecutores y validar fuente/actor. Extender registros, no codificar combinaciones.
- `odyssey_core/application.py`, `mutation_gate.py`, `materialization.py` y `SourceBoundDependency`: Core/E3 ya ofrecen gran parte de garantías. **No afirmar que toda App entra hoy en el mismo recorrido de solicitud ni que existe una transacción global E3**: Events usa `execute_event_candidate` + `EventMutationService` + `CanonicalMutationGate`, no la misma entrada `execute_request` que Core. `CanonicalMutationGate` protege una mutación de Nota, **no garantiza atomicidad de varias notas**. No se observó por ello un Writer clandestino; sí una **paridad de contratos de solicitud** por demostrar. El manifest de petición, recibos y estados parciales debe seguir protegiendo escrituras múltiples sin inventar rollback atómico.
- `odyssey_apps/tasks/interpretation.py:1046-1049` descarta explícitamente `conversation_context`; `odyssey_apps/events/provider.py:154-165` interpreta únicamente `source`. Esto contradice funcionalmente el propósito de que los bloques dispongan de contexto suficiente para resolver anáforas y referencias cruzadas. No solucionar mediante lista de pronombres o nombres especiales.

## 2. Contrato objetivo entre bloques

El **mismo sobre inmutable** debe transportar, con límites de tamaño y procedencia:

- `request_id`, `delivery_id`, actor autenticado y ámbito de vault ya resuelto por ingress (sin credenciales); `original_source` byte-exacto; reloj original/fecha/zona IANA; conversación anterior auténtica y acotada, diferenciada de la fuente de hechos del mensaje actual.
- `scope`: uno o varios intervalos exactos `[start,end)` y tipo de intención **propuesto**; todos los bloques conservan acceso de lectura al `original_source` completo (no solo `part.source.strip()`); el offset decide qué porción interpreta/escribe cada bloque.
- Contexto E2 acumulado: evidencias de Temporal, candidatos de notas y SELF con procedencia, menciones no resueltas, grafo y dependencias, resultados canónicos ya confirmados de pasos anteriores. Lo no comprobado se marca `proposal`, `pending` o `unverified`, nunca se eleva a prueba de identidad.
- `StageOutput` por bloque: interpretación y evidencias tipadas ancladas al original, intención/operación propuesta, dependencias, abstención o pendiente. El contrato se amplía **solo tras demostrar el caso de consumo en un bloque**. Un bloque no entrega cambios físicos a Markdown por su propio texto de modelo.

El acceso común al mensaje completo **no significa leer el vault entero ni permitir que una App escriba directamente**. Cada bloque solo consulta los handles de lectura autorizados; Core verifica identidad/cambio de estado. Reutilizar los `ContextPort` actuales, añadiendo solamente lo que hoy falta (source-scope, conversación y pruebas previas), con validación y versiones.

```text
[Ingress: autenticación, request/delivery, conversación, reloj]
           |
           v
[ExecutionContext E2 — original inmutable + ámbito(s) + pruebas]
           |
           v
[Router: propuesta de hechos/intenciones y relaciones fuente]
           |
           v
[E2/Core: integridad del origen + DAG de dependencias]
           |
           v
[Registro de bloques: Temporal, Core, Tasks, Events, futura App]
   Cada bloque recibe el MISMO original y su scope/evidencias
   Cada bloque interpreta solo su semántica y devuelve propuestas
           |
           v
[Core: resolución canónica, preparación, validación y dependencias]
           |
           v
[E3 existente: gates por mutación, manifest/recibos de petición, Markdown/readback]
           |
           v
[Runtime: respuestas, progreso, índices derivados, replay y UI]
```

**Scheduler genérico mínimo**: ejecutar la preparación de bloques independientes; esperar las pruebas verificadas de sus predecesores para los dependientes; si falta prueba, emitir `pending/needs_attention` sin inventar identidad; serializar efectos E3 y agrupar recibos. El orden se deriva del grafo **cuando su validación esté demostrada para esas capacidades**, **nunca** de `if Events+Tasks`, del número de padres, del idioma o de un `TaskOperation` dentro del orquestador. No paralelizar escrituras sobre el vault Git, ni prometer transacciones multi-Nota atómicas.

## 3. Orden estricto de refactorización (no varias soluciones paralelas)

### R0 — Congelar comportamiento real y elaborar matriz de aceptación

- Anclar SHA desplegado, flags efectivos, callbacks en uso y salidas de las rutas Core/Tasks/Events/Notes/Calendar; localizar y clasificar todas las ramas del P4 y del candidato como **semántica**, **validación de frontera**, **mecánica de entrega**, **histórica**. No modificar código de producción antes de registrar estas rutas y sus tests.
- Capturar antes del refactor los recorridos de usuario disponibles con GPT real y navegador/n8n en un **vault/actor desechable auténticamente aislado**. Si algún caso falla ya en la base, marcarlo `baseline FAIL` sin cambiar un golden para hacerlo pasar. Distinguir DEV HTTPS real de puente aislado.
- Congelar la matriz de comportamientos **ya soportados** de Core, Tasks, Work Sessions y Events; registrar mensajes con 0/1/2/3/5+ unidades, N:M, varias fechas, pronombres y referencias plurales como escenarios de aceptación o como brechas **baseline**, distinguiendo lo que hoy puede y no puede pasar. La prueba de una App ficticia corresponde a R4, no a la línea base. Los ejemplos son variaciones de TEST, nunca condiciones de ejecución.

### R1 — Contexto original común, adoptado en incrementos pequeños

- **Primero, transporte sin interpretar:** extender **el `ExecutionContext` existente**, no crear otro, con original byte-exacto, scope validado, reloj/actor de ingress y conversación autenticada de solo lectura con procedencia explícita. Elegir una sola frontera real P4 para integrarlo y probar que no se forja fuente, se filtran hechos de historial a la escritura ni se exponen otros vaults. No cambiar simultáneamente cuatro intérpretes.
- **Después, una adopción semántica cada vez:** usar el mismo sobre en la ruta Core elegida y luego en Tasks, Events y Temporal conforme sus contratos y dependencia real; cada bloque mantiene acceso a original completo + scope. En Tasks eliminar `del conversation_context` **solo** cuando el prompt, parser y validador sepan diferenciar historial de fuente actual. En Events cambiar el input `source` acotado por un contrato versionado. **Dar contexto adicional al modelo SÍ es un cambio model-facing**: leer `odyssey-llm-stage`, heredar el prompt validado, probar con GPT real, no marcarlo como un ajuste invisible.
- Retirar la llamada que pasa un fragmento `.strip()` a un intérprete que necesita anáforas de otra frase solo cuando ya consuma el contexto completo y siga anclando sus propuestas a los spans originales. No duplicar interpretación para un mismo bloque.
- Al terminar **cada incremento funcional integrado**: pruebas deterministas, GPT real del modelo/configuración efectiva y navegador real desde Chat→n8n→E3→Markdown→Notes/Calendar→recarga y replay, con ambigüedad sin escritura. Cuatro roles independientes sobre el SHA de integración. **No cerrar R1 solo con pytest.**

### R2 — Converger gradualmente en el propietario del grafo y la cobertura

- **No asumir que ya es genérico:** `dependent_group_graph` hoy limita Core/Tasks, 2–16 nodos y al menos una arista; `independent_source_scopes` solo admite algunos pares. Conservar ambos validadores donde protegen condiciones diferentes. Estudiar/introducir un **único contrato de grafo E2/Core**, extendiendo primero la validez a un ámbito, cero aristas y capacidades registradas **con pruebas equivalentes de fuente, cobertura, revisores y dependencias**; no cambiar todo de golpe ni forzar rutas que el intérprete de la nueva App no sabe manejar.
- Migrar una combinación de bloques soportada a la vez al mismo contrato: primero Core/Tasks, luego Events/Tasks y el resto que esté realmente habilitado. Para cada una, comparar resultados idénticos con el camino antiguo y borrar el selector/branch obsoleto antes de ampliar más combinaciones. Independiente = grafo sin aristas, dependiente = grafo con aristas cuya prueba es válida: **solo tras demostrar ambas formas**.
- Sacar del P4 la elección de combinaciones, grupos familiares, cardinalidad de personas, speaker y target. Core resuelve referencias de tipos genéricos con incertidumbre explícita; Temporal interpreta fechas; cada App decide si su operación de dominio puede ejecutarse. Consolidar únicamente revisores equivalentes; conservar verificaciones de confianza diferentes sin crear un LLM nuevo por cada `if`.
- Gate de **cada tramo funcional** con GPT real/navegador y auditoría Generalidad/Calidad/Pruebas/Rendimiento sobre SHA integrado, sin omisión de hechos ni escritura por identidad falsificada.

### R3 — Apps como propietarias; paridad E3 sin fingir una transacción global

- Inventariar y probar **por familia de mutación** la entrada actual: Core vía `execute_request`; Tasks/Work Sessions vía sus servicios y `CanonicalMutationGate`; Events vía `execute_event_candidate` y `EventMutationService`. Medir para cada una actor, target, CAS, identidad, idempotencia, recibo, lectura física Markdown y estado **PARTIAL tras escritura incierta**. No suponer que un solo request global E3 o rollback multi-nota existen.
- Reubicar/adaptar `execute_tasks` y `execute_events` de la composición a sus módulos/servicios **ya existentes** por pequeñas familias de operaciones. Sus handlers consumen el mismo contexto y entregan operaciones/estados tipados; Core conserva identidad y planificación genéricas. El coordinador despacha por registro, no por `if capability == ...`.
- Reemplazar los decisores `_execute_dependent_core_task`, `_execute_verified_plural_person_scope`, `_execute_dependent_graph` y `_execute_independent_scopes` solo cuando sus respectivos caminos tengan equivalentes de bloque/plan/recibo reales. Retirar cada camino sustituido **antes de añadir otro**. El ejecutor restante ordena y proyecta resultados, sin hacer interpretación semántica.
- Donde una App usa el `CanonicalMutationGate` pero carece de una garantía de solicitud compartida, reparar en **Core/E3 existente**, preservando el manifest de operación y los recibos de éxito, fallo y parcialidad; no sustituir el Writer ni inventar atomicidad universal.
- Gate de cada tramo funcional con modelo real, browser/n8n/Markdown/replay y cuatro roles de auditoría sobre SHA integrado.

### R4 — Retirar alternativas y demostrar extensibilidad

- Con el nuevo flujo probado, identificar referencias y flags aún vivos de `candidate_route_dispatch`, `routing.py` y rutas P4 antiguas. Retirar el camino antiguo **solo si la ruta activada, legacy y tests tienen sustituto**; conservar adaptadores de compatibilidad necesarios en perímetros externos, no una segunda interpretación.
- Registrar una App de prueba con semántica propia y referencias cruzadas **sin editar el orquestador**; verificar el mismo contexto E2, Core/E3 y gráfico/donut. Si hay que añadir `if nueva_app`, el refactor no está terminado.
- Comparar llamadas IA, p50/p95, CPU/RAM y serialización de escritura en Raspberry contra R0. Exigir que no se añada coste significativo sin justificación y que la UI, entregas y datos existentes permanezcan intactos.
- E2E final completo en entorno aislado y DEV publicado para SHA idéntico, con cuatro auditores independientes: **Generality, Quality, Testing, Performance**. No aceptar auditoría o aceptación anterior sobre SHA antiguo.

## 4. Criterios de aceptación medibles

1. **Una sola ruta de composición semántica activa**, sin motor alternativo de interpretación seleccionado por caso o App. `RuntimeComposition` no contiene reglas de nombres, pronombres, número de entidades, tipos de operación de Tasks ni pares de capacidades; solo delivery, registro/ejecución de contratos, E3 y telemetría.
2. Todo bloque recibe original/contexto/evidencias relevante y el ámbito exacto. Hay pruebas que impiden pérdida de un hecho, uso de otro scope, herencia de sujeto/fecha no probada o ignorar la conversación validada.
3. Cualquier nuevo tipo de App se registra sin editar la lógica del orquestador; guardas genéricas de Core y E3 se siguen ejecutando. Un App/LLM no tiene capacidad de autorizar una identidad o escribir por haber propuesto un enlace.
4. Una petición puede producir cero, uno o muchos hechos/operaciones, incluidos dependientes N:M; ambiguo/no soportado resulta en `pending`/`needs_attention` comprensible, **sin bloquear una afirmación perfectamente registrable solo porque no sea Task/Event**. Nunca se trunca una parte desconocida.
5. Todos los caminos de mutación pasan pruebas equivalentes de actor, concurrencia, CAS, idempotencia, recibo, Git/Markdown/readback, fallo posterior a escritura y replay. Se conserva la separación de vault personal y la futura dirección local-first móvil.
6. En **cada etapa funcional terminada**: cross-surface y schema/ruff PASS, ensayo adversarial con proveedor **real** efectivo, acción manual en navegador autenticado contra app/n8n real con vault aislado, Markdown físico y UI tras recarga/replay, **cuatro auditores independientes sobre el SHA final**. Si falta algo, se informa `IMPLEMENTADO / NO ACEPTADO`, nunca `TERMINADO`.
7. Reporte reproducible antes/después: número de ramas semánticas y callsites por App en el runtime, rutas retiradas, llamadas de modelo, cobertura de formatos/mensajes, SHA local, SHA desplegado, auditorías y latencia. Reducir complejidad **real**, no solo redistribuir líneas.

## 5. Lo que NO se va a hacer

- No codificar `mis padres`, `Luis`, `ambos`, idiomas, orden de cláusulas ni ejemplos del corpus.
- No construir otro mega-Context, `if` encubiertos en plugins, nuevo Router/Writer, nuevo servicio, LangGraph, base o cola.
- No sacrificar Core/E3/actor/identidad/readback ni la seguridad prewrite para reducir condicionales.
- No llamar «E2E» a mocks, respuestas grabadas, llamadas Python solas o navegar sin IA real; no confundir cuatro auditores PASS con E2E del producto.
- No fusionar ni desplegar ni tocar datos reales como parte de este **plan de lectura**. La PR #165 y su regla de contradicciones deben integrarse por su flujo autorizado y probarse; un cambio escrito en una skill no es una barrera automática.

## 6. Próximo paso concreto

El primer trabajo de implementación será el **primer tramo de R1**, sobre un diff pequeño: proporcionar el `ExecutionContext` de E2 y fuente original/`scope`/historial autenticado a **una frontera semántica existente** de P4, sin crear otra ruta ni cambiar otras Apps. Adaptar el prompt de esa frontera únicamente si realmente recibirá contexto nuevo; realizar el E2E auténtico antes de cerrar ese tramo. Después repetir la adopción por bloque, pasar a R2 y retirar decisiones por combinaciones en el P4. No reabrir Features UI, schemas ni otras fases hasta cerrar esta simplificación.
