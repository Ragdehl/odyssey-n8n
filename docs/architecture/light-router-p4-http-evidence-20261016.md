# P4 — Puerta de aceptación HTTP y reintentos; 16-10-2026

## Veredicto

**P4 parcial, NO aprobado para DEV ni para pruebas del usuario.** La ruta experimental funciona de Router y Planner con llamadas GPT reales a Core, Tasks, Writer y el adaptador HTTP real de Odyssey dentro de un vault y servidor **aislados**. No atraviesa el webhook real de n8n, ni un navegador autenticado, ni los índices productivos. No hay despliegue ni cambio de datos. No interpretar los 208 Python y 143 Node como una validación del producto completo.

## Continuación P4: variabilidad del Planner/revisor y comprobación física (16-10)


Checkpoint en rama `feat/light-router-poc-20261016`: commits `10e209a` y `483a276`, sin merge ni deploy. El gancho pytest del commit es conocido como bloqueado por diez fallos históricos; se ejecutó la suite completa de forma explícita antes del checkpoint (3428 PASS / 80 SKIP / 10 previos), con Ruff y validación de esquema correctos. El siguiente gate se mantiene en integración real de la nueva ruta sin importar módulos `benchmarks` desde el runtime productivo, pruebas n8n/browser en sandbox, seguridad de recuperación después de escritura y medidas Raspberry.

La batería ampliada (17 entradas) descubrió variabilidad real incluso con el mismo mensaje: el Planner llegó a inventar día/franja de tarde para un pasado no fechado, o a crear un participante literal `user` para primera persona. La cobertura Core frenó esas variantes sin escritura. Otro rechazo intermitente confundió un plan futuro («compraré») con una ocurrencia garantizada. No es un problema de `request_id` ni evidencia de que la protección Core deba rebajarse.

Se preservaron los prompts validados y se añadieron aclaraciones generales sobre actor gramatical ≠ entidad canónica, fecha no especificada = `null` y planes futuros ≠ hechos consumados. La última tanda fresca de cuatro escenarios dio 4/4 `completed` con 6 facts físicos nuevos; `p4_physical_readback.py` comprueba cada marcador canónico, propietario/fecha, persona por ID resuelto a través de la proyección Notes, SELF y backlinks. Cinco pruebas adversariales rechazan faltas de owner, identity link, cardinalidad o SELF. La matriz sin textos de usuario ni respuestas íntegras del proveedor se conserva en `p4_variability_summary_20261016.json`. **Una tanda correcta no demuestra estabilidad general**: hay negativas seguras y rechazos falsos en otras repeticiones. Ningún cambio en DEV.

En paralelo, la ruta de respuesta de chat se modificó **solo en rama** para que n8n persista de forma correlacionada el mensaje visible antes de responder al navegador. Con 28 pruebas local/HTTP correctas, el dry-run de restauración desde n8n reconstruyó 50 respuestas antiguas compatibles en un clon: 399→449 turnos, 19 restantes y una respuesta conflictiva excluida; 23 respuestas se preservaron sin metadatos opcionales inválidos. **Ni la restauración ni el nuevo flujo se han desplegado sobre conversaciones reales**. Pruebas finales de rama: **3428 Python PASS, 80 SKIP, mismos 10 fallos históricos; 168 Node PASS**. El test de petición inválida n8n exige explícitamente la ruta sin respuesta huérfana. La verificación n8n/web autenticada y los demás gates de P4 permanecen pendientes.

## P4 cross-surface recheck, 16-10-2026

Extensión de regresiones reusable: [gate cross-surface](cross-surface-regression-gate.md), 529 Python y 168 Node PASS (full suite 3454 Python PASS, 80 SKIP, los mismos 10 fallos históricos) sin proveedor; recorrido HTTP real Notes/Tasks/subtask/Work Session con vault temporal, pero **no navegador/n8n live**. Una batería fresca de 17 mensajes GPT reales en clon DEV produce 11 `completed` y 6 `needs_attention`; el bloqueo a Guillem→Sergio es un falso negativo residual. `NO_CHANGE` del Day de Guillem con `CREATE` de la Task de llamada fue inicialmente señalado incorrectamente por el verificador previo que exigía todas las escrituras nuevas; también se reutilizó legítimamente una preferencia SELF ya existente. Verificador reforzado exige fact marcado previo o nuevo, propietario exacto, coincidencia literal, SELF y backlinks; no admite texto similar no demostrado. Mini-retest de 3 mensajes PASS en dicho verificador, con un fact nuevo y otro previo para caso mixto Guillem+Task. El modelo todavía puede producir una paráfrasis redundante: el revisor semántico de ya conocido de Core es experimental y no está integrado en esta ruta. **No se autoriza DEV ni se proclama ausencia de hardcoding.**

## Evidencia REAL con cinco peticiones HTTP nuevas

Script: `benchmarks/application_router/light_router_poc_20261016/p4_runtime_http_sandbox.py`. Es un banco de pruebas, no código de producto; reusa P3 y usa embeddings sintéticos, clona temporalmente las 97 Notes DEV, crea actor y SelfBinding efímeros y destruye todo al acabar. Monta el **`odyssey_runtime.server._handler_for` y `RuntimeComposition.execute_product` auténticos** sobre TCP 127.0.0.1, con ruta experimental expresamente inyectada y `full_source_mutation_guard=True`. Llama de nuevo a GPT-6 Router, GPT-5.6 Planner conjunto y GPT-5.6 revisor, con `store=false`, luego Core Writer y Tasks normales.

| ID | Fuente | Resultado físico + HTTP |
|---|---|---|
| `http-maya-1` | Ayer hablé con Maya. | HTTP 200 COMPLETED; crea 1 Person Maya y fact en Day 15; 1 backlink verificado |
| `http-maya-2` | Ayer cené con Maya y hoy volví a hablar con ella. | HTTP 200 COMPLETED; 2 facts en Days 15 y 16; reutiliza **exactamente el mismo ID Maya** y ambos backlinks, sin segunda persona |
| `http-maite-3` | Hoy he conocido a Maite, mañana tengo que llamarla. | HTTP 200 COMPLETED; persona + Day + Task; validado estado `pending`, `target_date=2026-10-17`, exactamente 2 fact receipts y dos backlinks al ID canónico Maite |
| `http-ana-4` | Hoy hablé con Ana y Luis. Ana va a París mañana… | HTTP 200 NEEDS_ATTENTION; **todos los archivos byte por byte intactos**; incertidumbre Ana vs Ana López |
| `http-ambig-5` | Ayer vi a Eric y Luis; mañana iré con él al cine. | HTTP 200 NEEDS_ATTENTION; **ningún archivo modificado**; referente «él» sin evidencia inequívoca |

**Cinco de cinco reenvíos con request_id original:** el almacén duradero devuelve `delivery_replayed=true`, no llama de nuevo a Router/Planner/Writer y las Notes permanecen **idénticas byte por byte**. El resultado se recupera también en una instancia nueva de `RuntimeComposition`, sin ejecución. Duraciones completas HTTP incluidas en `p4_runtime_http_receipts.json`, observadas ~8–15 s por mensaje, no comparables con n8n/índices productivos.

## Hallazgo crítico descubierto por fault injection

Antes del cambio, una repetición del mismo **sub-request ID Core** no duplicaba el hecho Day, pero **dos ejecuciones Task CREATE con el mismo sub-request ID sí creaban DOS Tasks**. Reproducción con `execute_request` real y vault temporal: Day primero 1 luego 1; Task primera ejecución 1, segunda 2. Esto demostraba que el store de resultados completados NO bastaba ante caída entre escritura Task y recibo HTTP.

Corrección opt-in, **apagada por defecto**: `RuntimeComposition.full_source_mutation_guard: bool=False`. Con `True`, se reserva atómicamente el `request_id` en el `LocalDeliveryResultStore` E3 **antes** de planificar/escribir, y se libera solo después de guardar recibo de replay completo. Ante caída incierta después del efecto, se conserva el claim y el siguiente intento del mismo ID devuelve **HTTP 409 sin otra escritura**. Test real de transporte HTTP con fallo inyectado produce 500→409 y un solo efecto. La petición no se repite automáticamente y requiere reconciliación manual/duradera del recibo: **no se ha implementado aún la recuperación satisfactoria de un claim pendiente**, por eso no está lista para DEV.

La guarda no reemplaza la idempotencia de Task CREATE ni la transacción multi-Note. Debe usarse con diseño P4 final para continuación/cancelación y resultados `partial`. Es una barrera de at-most-once, no un «exactly once» demostrado.

## Workflow/UI

`tests/odyssey_p4_http_receipts_workflow.test.mjs` ejecuta el **código fuente real de mapeo n8n** localmente con fixtures derivados de respuestas HTTP capturadas y valida la forma del navegador. **No es una ejecución real del webhook n8n ni del DOM del navegador.**

- Las tres completadas se presentan como confirmación si el mapeo recibe los Action/Unit receipts.
- **Bloqueo UX**: Ana y «él» reciben aclaración genérica sin opciones verificadas. La interfaz no puede ofrecer una elección accionable ni continuar. El test deja explícita la limitación, no la disfraza de aceptación.
- Ausente aún un gráfico de ejecución de la nueva ruta y su ajuste de ancho/etapas, así como el donut con progresos de los tres modelos.
- Runtime DEV y n8n actuales responden a `/healthz`; eso **no** verifica la nueva ruta en n8n.

## Gates siguientes antes de DEV manual

1. Mover Router/Planner/revisor desde los scripts de banco de pruebas a contratos de producción autónomos y autorizados por Core, manteniendo original íntegro y decisiones tipadas por capacidades; tests completos con notas/índices auténticos, alias y contexto conversacional.
2. Resolver continuidad parcial de hechos sin sobrebloquear solicitudes: qué hechos se conservan cuando hay ambigüedad de uno solo, y cómo continuar opciones de identidad sin que una IA invente la asociación.
3. Integrar claims y reconciliación tras caída, controlar creaciones forzadas Task; pruebas de interrupción ANTES y DESPUÉS de cada mutación multi-App, concurrencia, reenvío tras reinicio.
4. **Ruta real** navegador→n8n→runtime→LLM→Writer→readback→n8n→browser con copia de vault y aislamiento; medir por etapa, CPU/memoria/indexación de Raspberry, sin reprocesar todo el vault en ruta crítica. Debe usar requests nuevos y estados reales, no replays grabados.
5. Resultados visibles accionables: gráficos compactos, etiquetas legibles, qué decidió cada IA, hecho guardado/no guardado y selección/cancelación de ambigüedades.
6. Validar una **batería extensa y diversa** de regresión real, variantes de frases y negativa/condicional antes de anunciar «listo para probar».

## Evidencias y límites

- Recibos completos `benchmarks/application_router/light_router_poc_20261016/p4_runtime_http_receipts.json`. Script reproducible `p4_runtime_http_sandbox.py`.
- Tests `tests/runtime/test_full_source_delivery_guard_p4.py`: guarda opt-in, HTTP 500→409, replay tras restart y claim persistente.
- `tests/benchmarks/test_p4_runtime_http_live_receipts.py`: resultados semánticos y readback reales; `tests/odyssey_p4_http_receipts_workflow.test.mjs`: caracteriza mapeo actual e insuficiencia de UX.
- **208 pruebas de backend y 143 de UI JavaScript superadas** en los subconjuntos pertinentes; además, **suite Python completa: 3.395 PASS, 80 SKIP y exactamente los mismos 10 fallos históricos preexistentes de benchmarks/pricing (52 subtests PASS)**; **Node completo: 165 PASS, 0 FAIL**. La suite JavaScript no prueba un navegador autenticado.
- Estado DEV al cierre: commit `1474681`, checkout limpio, **97 Notes sin cambios**. PROD sin cambios. Nuevo código sigue únicamente en rama `feat/light-router-poc-20261016`.

**Decisión:** P4 HTTP aislado PASA y revela una mejora de seguridad necesaria; **P4 producto real NO PASA**, mantener gate manual DEV cerrado.
