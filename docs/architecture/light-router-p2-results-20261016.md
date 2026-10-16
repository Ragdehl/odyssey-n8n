# P2 — PoC integrada Router ligero, Core, Tasks y Markdown (16-10-2026)

**Veredicto:** la arquitectura de interpretación íntegra y posterior distribución se ha demostrado **técnicamente viable** con una PoC *aislada*. No se ha autorizado ni ejecutado una instalación DEV o PROD, ni está lista para usuarios. Este informe prevalece sobre la P1 meramente semántica.

## Qué se ejecutó

- Rama `feat/light-router-poc-20261016`, en `/home/ragdehl/projects/odyssey-e3-mutation`, código del prototipo EXCLUSIVAMENTE en `benchmarks/application_router/light_router_poc_20261016/`.
- `p2_integrated_bridge.py` combina **GPT-6 Router ligero** y **GPT-5.6 plan completo** (cuando `--fresh`), **una revisión INDEPENDIENTE de GPT-5.6** contra el mensaje original y una verificación determinista de `source_evidence`, fechas, referencias y cobertura, y baja el resultado al `RequestPlan` existente.
- El **Writer no es nuevo**: toda escritura de hecho usa `odyssey_core.application.execute_request`, preflight y Writer canónicos. La Task se procesa mediante `TaskCorePlanner`, `TaskLifecycleGuard(TaskOperation.CREATE)` y el mismo `execute_request`. Identidades se resuelven/crean en la preflight de Core, no en Router ni por las IA. La tarea reutiliza el ID canónico que la creación del primer hecho acaba de materializar.
- **No se invoca el viejo validador `candidate_coverage`** porque el contrato legado carece todavía de un contexto de hechos íntegros e impide incluso planes válidos. En esta PoC solamente se usa **una prueba de fuente alternativa y provisional**, que admite planes únicamente cuando la revisión externa y el control estructural concuerdan. **No se ha probado que alcance todas las garantías del validador de producción; no puede conectarse al runtime hasta que el contrato de Core se formalice y pruebe con casos adversariales.** No extrapolar el cumplimiento de Writer al de todo el pipeline.
- Copia temporal **nueva y validada de las 97 Notes de DEV** por solicitud; al final se destruye, incluyendo las notas creadas. Embeddings **sintéticos sin candidatos**: la simulación NO equivale a la recuperación semántica activa, ni al n8n/UI. Una guarda PoC adicional rechaza toda coincidencia parcial de nombre existente (p. ej. «Ana» vs «Ana López») **antes de ejecutar**, para no inventar identidades.
- Tras cada operación se reconstruye índice efímero de notas y se verifica lectura física del Markdown por fecha, número de hechos/recibos, Task status/prazo, nombre/ID único de persona y **backlinks reales** mediante `NotesQueryService.backlinks`, no solo existencia de archivos.
- Todas las llamadas nuevas de OpenAI se realizan con `store=false`, acotadas y sobre texto original más pistas mínimas. No se ha dado a proveedores el contenido íntegro del vault. Salidas semánticas y revisiones se conservan en JSON para regresión posterior.

## Resultados registrados: 6 mensajes, 5 completados, 1 bloqueo seguro

| Entrada | Reproducción con IA nueva (`--fresh`) | Readback y evidencias |
| --- | --- | --- |
| «Ayer hablé con Maya» | COMPLETED | Nota Maya creada, Day 15 actualizado, 1 backlink |
| «Hoy conocí a Guillermo» | COMPLETED | Reutiliza el mismo ID preexistente de Guillermo, ningún duplicado, 1 Day |
| «Ayer cené con Maya y hoy volví a hablar con ella» | COMPLETED | Misma persona en los dos Days 15 y 16, 2 backlinks |
| «Hoy he hablado con Ana y Luis…» | NO-WRITE / atención | El Planner detectó que «Ana» podría no equivaler a «Ana López»; sin prueba única no se escribe ni se crea otra Ana |
| «Hoy he conocido a Maite, mañana tengo que llamarla» | COMPLETED | Crea persona, registra Day 16, crea Task pendiente para 17/10, Task y Day enlazan ID **idéntico** de Maite; 2 backlinks |
| «Hoy he comprado pan y mañana compraré leche» | COMPLETED | Dos facts, fechas 16/10 y 17/10; segunda acción permanece fact futuro, no Task no solicitada |

- En el control con planes auténticos de la P1 (nuevas llamadas al revisor), los mismos 5 casos escriben y el caso Ana/Luis se **rechaza sin mutaciones** por nombre parcial. `p2_integration_receipts.json`.
- En la nueva campaña `--fresh`, se llama otra vez a Router, Planner y Revisor para CADA ejemplo: no se reutilizan los outputs semánticos grabados. `p2_integration_receipts_fresh.json`. En esta ejecución, Ana/Luis se abstiene aún ANTES de la preflight porque el Planner declara la identidad de Ana «unresolved»; el revisor no puede convertir esa incertidumbre en escritura.
- **Observabilidad sin maquillajes:** un intento anterior de la P2 original creó erróneamente «Ana» separada de «Ana López» porque los embeddings sintéticos no aportaban candidatos. Es un falso éxito que se ha corregido en la PoC mediante rechazo seguro; **NO declarar aquel 6/6 como éxito real**.
- Una llamada inicial de revisor independiente rechazó «ayer» porque el reloj absoluto se perdió en el contrato. Se corrigió enviando `clock` verificado al revisor. Otra recibió una cita fuente ampliada en torno al candidato; se acepta únicamente cuando sigue siendo una subcadena exacta de la fuente original y **contiene literalmente** la cita del plan; no se permiten frases inventadas.
- `tests/benchmarks/test_light_router_p2_contract_20261016.py`: oráculos de que la fuente no cambia, los hechos y referencias se mantienen y mutaciones adversarias (fecha, cita, sujeto, referencia, permiso Tasks, duplicados, ambigüedad y edición maliciosa del texto) se bloquean. Suites de Core/Tasks existentes siguen vigentes.

**Métricas de última campaña totalmente fresca:** 6 escenarios; 12 llamadas semánticas (Router+Planner) + 6 revisiones independientes; coste proveedor estimado de los tres pasos ~**0,0056895 USD** (`fresh_semantic_estimated_usd=0,0033423` y `total_estimated_usd=0,0023472`). Las latencias ~7–12 s/caso **no incluyen** integración HTTP n8n/Cloudflare, UI ni embeddings productivos; no compararlas como mejoras demostradas respecto al chat DEV.

## Limitaciones objetivas — próximos gates P3/P4

1. **Cobertura y pruebas de fuente formales**: integrar una prueba de semántica íntegra dentro del propio contrato Core; no limitarse a dos dictámenes de LLM. Aprobar adversariales para negación, condición, corrección, referencias no inequívocas, eventos con múltiples sujetos y tipos. No conectar la PoC provisional directamente al runtime.
2. **Identidad genérica**: reconciliar nombres parciales/alias mediante búsqueda canónica real y pruebas de correspondencia, sin falsos duplicados ni convertir un prefijo en prueba de identidad. Manejar SELF bajo binding autenticado real, incluida «mis hijos».
3. **Hechos sin fecha/día**: fuente de verdad para dónde escribir «mis hijos fueron al parque…» sin inventar que fue hoy ni una nota genérica; la PoC actual rechaza hechos sin fecha y sin dueño explícito. Tampoco admite aún tiempos cualitativos como «por la tarde» en el Writer completo.
4. **Una interpretación, varias apps**: generalizar operación/ámbito entre Core/Tasks, dependencias, escrituras parciales, readbacks y reintentos seguros usando el store E3 y el `ExecutionContext` E2; la PoC ejecuta pasos secuenciales y aún no implementa el gate durable de entrega/idempotencia.
5. **Datos de la aplicación real**: usar embeddings semánticos productivos/identidades/índices y estado de conversación en un clon aislado. n8n, donut, grafo y explicación de errores son los siguientes gates antes de recomendar pruebas manuales.
6. **Lengua del usuario**: el revisor fuerza hechos en español para la PoC; diseñar y probar preservación genérica del idioma de cada mensaje, sin reglas que funcionen solo en español.
7. **Variabilidad del proveedor**: ejecutar nuevas llamadas de aceptación repetidas y no depender de una sola corrida; guardar los rechazos legítimos y los aciertos en fixtures.

## Conclusión de arquitectura

La prueba demuestra que **Router de capacidades → comprensión conjunta del mensaje → fuente validada → Core Writer/Tasks especializados** puede producir notas y vínculos físicos coherentes sin trocear los sujetos ni crear otra lógica de persistencia. Sin embargo, el puente de seguridad es experimental y el caso Ana demuestra por qué no hay que desplegar con tan solo «lo ha entendido una IA».

**Siguiente decisión**: aprobar una implementación incremental P3 para convertir el contrato P2 en un contexto formal E2 y cobertura Core auditada, con los casos anteriores como gates reproducibles. Después P4 E2E n8n/UI y memoria/rendimiento antes de tocar DEV. PROD permanece fuera de alcance.

### Artefactos

- `prompt_contract.py` — mismos prompts ligeros para las dos fases; sin divergencias.
- `run_poc.py`, `observations_v1.json`, `observations.json` — P1 con modelos reales.
- `p2_integrated_bridge.py` — PoC de compilación/revisión y Writer existentes en vault temporal.
- `p2_integration_receipts.json` — P2 con planes genuinos previamente capturados, revisión nueva.
- `p2_integration_receipts_fresh.json` — P2 de IA nueva en las TRES etapas.
- `integration_control.json` — muestra que la antigua entrada full-source sin el nuevo contrato falló 0/3.
- `tests/benchmarks/test_light_router_p2_contract_20261016.py` — pruebas negativas y oráculos.
