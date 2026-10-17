# P4 — evidencia GPT genuino en ruta Core→Tasks dependiente (17-10-2026)

**Entorno/seguridad:** los tests se ejecutaron en Raspberry Pi en una unidad efímera `systemd --user --wait --collect --pipe -p EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env`, usando únicamente `ODYSSEY_APPROVE_LIGHT_POC=1` y presupuesto de 1 o 3 intentos. El fichero estaba protegido modo `600`, el user bus activo; nada se imprimió ni copió al repo. Los tests usaron **vault efímero diferente por intento** con Task sintética, SELF sintético, Core Writer real y Work Session/E3 reales. La interpretación GPT Router, segmentador, Tasks, auditor de operación y dos revisores Task fueron **frescas**; el `RequestPlan` de Core se congeló para aislar la clasificación y el enlace físico. No es navegador→n8n ni planificación Core GPT genuina. Ni DEV ni PROD ni notas personales se tocaron.

## Fallo reproducido

Fuente de prueba: `Hoy revisé Preparar informe Atlas. Ahora empieza una sesión de trabajo en esa tarea.` El Router tenía instrucción de no confundir actividad dentro de sesión con Core; en vivo interpretó erróneamente **ambas intenciones como una única operación de Tasks**:

- **5 intentos con prompt previo:** 0/5 completados, `capabilities` incluía solo `tasks` (y en el intento diagnosticado `temporal`). Un único `app_scope` resumía registrar la revisión e iniciar sesión; `TASK_ONLY_SCOPE` independiente devolvió `only_task_semantics=false` y `exactly_one_operation=false`, bloqueando correctamente la escritura **ANTES de Core**. Los cinco recibos resultaron `needs_attention`, sin sesiones ni hechos falsos, replay E3 estable.
- **Causa:** el prompt del Router enfatizaba que el progreso de una sesión debe ser Tasks, pero no distinguía explícitamente la **afirmación pasada independiente sobre una Task** de una actividad registrada *dentro* de una Work Session. El modelo amalgamaba un hecho y una orden, incluso sin que se mencionase sesión en la primera cláusula.

## Corrección general de interpretación

Se extendió `ROUTER_INSTRUCTIONS` en `odyssey_runtime/whole_source_model_contract.py` con una regla transversal de cobertura de intenciones: una afirmación pasada independiente pertenece a Core aunque su objeto sea Task; una orden Work Session posterior es una segunda operación Tasks; si la referencia del segundo fragmento depende de la Task del primero, devolver **joint con antecedente Core y ámbito Tasks dependiente**. No contiene nombres, IDs, texto del fixture, regexp ni una excepción por frase. Se conserva la instrucción anterior de que una actividad **explícitamente dentro de una sesión** debe clasificarse Tasks y no generar doble hecho personal. Test `tests/runtime/test_p4_model_contract_strict_schema.py::test_router_generic_intention_coverage_does_not_merge_core_fact_with_session_lifecycle` comprueba que el contrato realmente exportado contiene esas reglas sin nombres concretos.

## Resultado tras corrección — GPT genuino

- **3 intentos consecutivos tras ajustar el prompt:** **3/3 `status=completed`**, `capabilities=[core,tasks,temporal]`, `interpretation=joint`, un `app_scope` Core independiente y otro Tasks `depends_on_another_scope=true`.
- **3/3** segmentación exacta de fuente aceptada, `TASK_ONLY_SCOPE` sobre el segundo fragmento aprobó una sola operación, dos revisores semánticos corroboraron la Task y START_WORK_SESSION, `OpenAITaskInterpreter` real devolvió `START_WORK_SESSION` con referencia exacta `esa tarea`.
- **3/3** Core Writer real materializó un hecho en Day con enlace canónico `[[atlas|Preparar informe Atlas]]`; el servicio de Tasks creó **una** Work Session, `delivery_replayed=true` y snapshot byte a byte inmutable tras reenvío del mismo ID.
- El primer runner marcó esos tres resultados `passed=false` únicamente porque el **checker de test** esperaba un evento local `"prepare"` dentro del array de llamadas del delegado, pero ese fixture solo registra `"core", "task"`. Esta discrepancia no afectaba a `status`, notas ni replay. Corregido `scripts/p4_dependent_real_provider_gate.py` para comprobar `calls == ["core", "task"]`; el runner tiene también trazas acotadas de clasificación (sin prompts/credenciales), y se corrigió un `print(json.dumps(..., flush=True))` que pertenecía al código de test, no a Odyssey. Por transparencia, la **salida del runner corregido NO se reejecutó con GPT** después de estos cambios: la siguiente invocación adicional por herramienta fue bloqueada. Los tres éxitos **sí** fueron ejecuciones y comprobaciones genuinas, sus campos `completed`, `canonical_backlink`, `replay` y `unchanged_after_replay` fueron todos `true`.

## Siguiente gate y límites

`scripts/p4_live_router_diversity_matrix.py` quedó preparado con **9 frases sintéticas** de español, francés e inglés, casos positivos de Core→Tasks, Tasks-only de sesión, una persona→recordatorio, futuro indicativo Core y multioperación. No se ejecutaron esas nueve llamadas: la herramienta rechazó la invocación posterior del proveedor. La prueba separa correctamente un caso histórico de sobreclasificación de las posibles regresiones por la corrección genérica.

**No autoriza P4 en DEV:** falta diversidad multiidioma GPT nuevo, Core Planner genuino, subtareas dependientes, escenario autenticado navegador→n8n real, corrección de UI/graph/donut en pantalla, performance de la Pi y recuperación E3 postwrite en caso incierto. No aumentar frecuencia de llamadas ni saltarse controles de la herramienta para completar esos gates.

## Regresión posterior al cambio

- Gate transversal offline: **733 Python PASS**, **168 Node PASS** (63 archivos, 9 grupos), comprobación de integridad del ledger de aceptación **15 invariantes y 26 anclas PASS**, P4 DEV NO AUTORIZADA.
- Suite global: **3658 Python PASS, 80 SKIP, 52 subtests PASS y exactamente los mismos 10 fallos históricos** de benchmarks/pricing, sin regresión adicional. Esos tests antiguos no se han relajado para obtener un resultado verde.
- La matriz de nueve variantes permanece como prueba futura, no se ha contabilizado como evidencia completada. El prompt corregido tiene prueba de estructura, pero sigue pendiente la validación con modelos frescos de esa diversidad.
