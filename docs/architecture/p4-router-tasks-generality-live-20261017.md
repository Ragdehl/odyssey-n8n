# P4 — Revisión generalidad Router, Tasks y Core Writer con GPT real (17-10-2026)

**Alcance y privacidad:** comandos ejecutados en Raspberry Pi bajo `systemd --user` transitorio (`EnvironmentFile` fijo y protegido de `AGENTS.md`, flag de autorización), usando SOLO mensajes sintéticos. Los tests de clasificación y auditoría no cargan el vault ni escriben Notes. Los tests verticales crean un vault TEMPORAL y SELF autenticada sintética; HTTP localhost y E3 auténticos, SIN navegador ni n8n desplegado. DEV sigue en `1474681`, PROD y datos reales intactos.

## 1. Router GPT-6: primer gate 9/9 reveló pérdida de cardinalidad

La matriz original `scripts/p4_live_router_diversity_matrix.py` pasó las nueve condiciones de **etiquetas de capacidad**, pero en el caso «revisé Atlas, inicia sesión en Atlas y después corrige Beta» la salida tenía dos scopes: Core y uno Tasks que fusionaba DOS mandatos. Contar solo `capabilities=[core,tasks]` como éxito era un oráculo insuficiente.

Se reforzó el contrato general del Router: **un scope por intención independiente, aunque varias sean del MISMO dominio Tasks**. Ninguna frase, ID, persona o nombre de Task de los casos aparece como excepción en código productivo. El criterio de aceptación del modelo se endureció: el caso de Core + dos comandos Tasks exige **3 scopes** (1 Core, 2 Tasks) y el caso Tasks-only con dos comandos exige 2 scopes Tasks.

- Nueva repetición con GPT real de los nueve casos: **9/9 PASS**, incluido el caso de 3 scopes. Fuente raw `/tmp/odyssey-p4-router-diversity-20261017-c.log`.
- Ampliación posterior a **22 escenarios reales de Router**: **22/22 PASS**. Incluye variación ES/FR/EN, hecho independiente seguido de Work Session, persona nueva + obligación, futuro indicativo NO Task, actor implícito (Guillem), pronombre que arrastra a una tarea, Ana y Luis, sujeto colectivo «mis hijos», fecha de sprint, proyecto nuevo, Bea y sus hijos, Task CREATE, subtarea explícita, STOP/EDIT Work Session, preferencia SELF, y dos órdenes Tasks sin Core. Tanto las múltiples capacidades como la cardinalidad mínima esperada de los comandos se contrastaron. Logs `/tmp/odyssey-p4-router-extended-20261017.log`.

**Interpretación:** son 22 *clasificaciones* correctas con GPT real, NO 22 ejecuciones completas ni 22 pruebas de graph/backlink; Router no resuelve identidad ni decide Writes. En caso de múltiples scopes dependientes P4 sigue bloqueando la petición sin escribir hasta tener planificación N:M (no descarta grupos silenciosamente).

## 2. Auditor independiente de ámbito Tasks GPT real: 6/6

Nuevo `scripts/p4_task_scope_auditor_live.py` comprueba seis entradas con el **modelo real y el esquema productivo** `TASK_ONLY_SCOPE_PROMPT`: inicio único, actividad única (ambos autorizables), inicio + modificación de otra Task, inicio + stop, un hecho personal + sesión y una predicción futura (los cuatro no autorizables). **6/6 decisiones correctas**, con fuente exacta copiada, cero escrituras (`/tmp/odyssey-p4-task-scope-auditor-20261017.log`). Esto protege la frontera aunque un Router defectuoso agrupe múltiples operaciones.

`tests/runtime/test_whole_source_light_product_p4.py::test_router_two_task_operations_can_never_execute_only_the_first` crea el resultado congelado de dos `app_scopes` Tasks de la prueba GPT y un auditor Tasks que dice NO. Usa los servicios de runtime y E3 reales en vault efímero para verificar: no se invoca el delegado de dominio, las Notes quedan byte idénticas, el resultado es `needs_attention` y el retry recupera el mismo recibo sin pedir al modelo otra respuesta.

## 3. Planner/Writer real GPT + HTTP y backlink SELF

El runner ya existente `scripts/p4_product_live_isolated.py` se ejecutó con GPT real de Router/Planner/review y Core Writer/HTTP/E3 reales para tres casos: `cross_app` (persona + tarea con pronombre), `implicit_undated_self` («He conocido a Nerea Ensayo») y `pronoun_two_dates` (persona compartida entre ayer y hoy). Resultado **3/3 `accepted=true`**, hechos físicos esperados 2/1/2, petición `completed`, lectura del vault temporal y replay E3 inmutable, sin duplicación; `/tmp/odyssey-p4-core-planner-real-20261017.log`.

El checker se fortaleció para el caso crucial de **primera persona implícita sin fecha**: ahora requiere un `backlink` canónico desde el hecho en la nota SELF hacia la persona mencionada, verificado mediante `NotesQueryService.backlinks` —no basta con contar un hecho. Nueva ejecución con GPT real **1/1 PASS**, `implicit_self_backlink_verified=true`, HTTP 200, replay idéntico, `/tmp/odyssey-p4-self-backlink-20261017.log`. El experimento anterior ya había evidenciado ese SELF en Markdown, pero esta ronda exige expresamente la proyección de grafo correspondiente.

## 4. Ruta dependiente Core→Tasks con GPT real, contrato de recibo corregido

`scripts/p4_dependent_real_provider_gate.py` se volvió a ejecutar con GPT Router, split, TaskInterpreter, auditor y dos revisiones genuinos. Core usa un `RequestPlan` **congelado**, pero su `execute_request`/Writer, TaskWorkSessionService y E3 escriben **Markdown real en vault sintético**. Después de arreglar la discrepancia anterior de `calls` del runner, el recibo nuevo fue **1/1 PASS** con `status=completed`, Task canónica enlazada físicamente, UNA Work Session, replay E3 sin cambios, `domain_calls=[core,task]`; `/tmp/odyssey-p4-dependent-receipt-corrected-20261017.log`. Este resultado no valida planificación Core genuina dentro de la ruta dependiente; para la planificación Core completa se usó el runner del apartado 3, en otras fuentes.

## 5. Pendientes / criterios de adopción

- Las tasas observadas son una muestra limitada en la misma fecha; no son garantía probabilística ni autorización DEV.
- Chat P4 debe poder producir subtareas dependientes desde Planner Core sin inventar título y aún está protegido por `DEPENDENT_SUBTASK_PLANNER_NOT_READY`; la UI ya usa la misma puerta de mutación canónica.
- N:M (3+ segmentos dependientes, dos Work Sessions distintas, atribución de actor/fecha entre fragmentos) está detectado como no soportado y debe conservar abstención explícita, no pérdida de acciones.
- Falta el recorrido **navegador autenticado → n8n realmente ejecutándose → Router/Planner GPT fresco → Core/Tasks/E3 → Markdown → gráfico/donut/historial** en un vault aislado, y la reconciliación E3 tras fallo postwrite incierto.
- Faltan mediciones de índices, swap, CPU y tamaño grande de vault en Raspberry. No instalar un segundo navegador/n8n pesado sin presupuesto de memoria.

**Control de continuidad:** scripts reales del proveedor requieren flag + `EnvironmentFile` transitorio del user manager y NO pertenecen al gate offline de CI. Suite transversal y global deben registrarse en el roadmap después de finalizar, sin sustituir la condición del navegador real.

## 6. Gate determinista global y rendimiento real de la Raspberry

Se volvió a ejecutar `python scripts/odyssey_cross_surface_gate.py` con la nueva regresión de **dos órdenes Tasks dentro de un único mensaje**: **734/734 Python PASS** (63 ficheros/9 grupos), **168/168 Node PASS**. El acceptance ledger mantiene 15 invariantes/26 anclas y **DEV P4 no autorizada**. La suite global cerró **3659 PASS, 80 SKIP, los mismos 10 FAIL históricos de benchmarks/precios y 52 subtests PASS**; no se detectaron regresiones nuevas. Ruff y formatos también correctos.

El benchmark provider-free `scripts/p4_product_scale_isolated.py` se volvió a ejecutar en la Pi con **20, 250 y 1000 Notes sintéticas** (no datos del usuario; embeddings deterministas). Resultados `/tmp/odyssey-p4-product-scale-20261017-current.log`:

| Notes adicionales | Preparación índice (s) | Ejecución P4 sin LLM (ms) | Refresco incremental | Rebuild en escritura |
|---:|---:|---:|---:|---:|
| 20 | 0,05 | 102,7 | 1 | 0 |
| 250 | 5,09 | 1.019,0 | 1 | 0 |
| 1000 | 78,9 | 3.971,4 | 1 | 0 |

Esto es comparable con ~103/1016/3999 ms de la medición anterior; **no sugiere una regresión**, pero confirma que el coste de lectura/preflight del Core tiene todavía comportamiento próximo a O(N), independiente del modelo. No demuestra rendimiento real de FastEmbed, red, n8n ni navegador. El perfil completo y la optimización del número de escaneos físicos de Core siguen pendientes; no se instaló otro navegador/n8n sobre la Pi con 4 GB RAM y ~1,5 GB de swap ocupado.

La repetición GPT tras modificar la clasificación no convierte la ruta de subtareas en soportada: `DEPENDENT_SUBTASK_PLANNER_NOT_READY` continúa bloqueando antes de cualquier escritura cuando falta un título de nueva Task acreditado por el Core Planner, y N:M se bloquea cuando excede la capacidad exacta de la ruta. **No desplegar DEV ni PROD.**
