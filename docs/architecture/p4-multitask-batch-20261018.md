# P4 — lote de tareas CREATE por el compilador y Writer canónicos (18-10-2026)

## Motivación y frontera

El mensaje de dos obligaciones «tengo que llamar al electricista y revisar la factura» fue rechazado por un auditor de Task-only: only_task_semantics=false, exactly_one_operation=false. La ruta existente tenía como precondición una sola operación; delegar arbitrariamente la primera tarea descartaría contenido del mensaje y sería inseguro. El compilador Core whole_source_compiler ya soporta múltiples Task CREATE revisadas, y TaskLifecycleGuard valida cada escritura con el mismo mecanismo E3/Markdown.

## Cambios de rama, opt-in DEV

- La auditoría independiente separa dos dimensiones: only_task_semantics significa que TODO el mensaje pertenece a Tasks (puede incluir varias acciones); exactly_one_operation determina su cardinalidad. Mensajes mixtos con un hecho Core mantienen only_task_semantics=false. La ruta de un solo comando Tasks permanece intacta y conserva interpretación, lifecycle y WorkSession service.
- Si la auditoría prueba todas-las-tareas y más-de-una-operación, y solo con task_create_batch_enabled (flag DEV), el coordinador usa la ruta habitual del Planner de mensaje completo, el auditor independiente mixed_task_create y los revisores coverage + speaker A/B. Se exigen al menos dos facts de kind=task (no convertir dos obligaciones en una). Los comandos de lifecycle o WorkSession no pasan el auditor de solo Task CREATE y se rechazan.
- El mismo compile_reviewed_operations de Core compila TODO el lote antes de una sola escritura. Cada RequestPlan se envía a execute_request con TaskLifecycleGuard(TaskOperation.CREATE), mismo Writer, readback, E3 idempotencia y eventual indexación que en cualquier otra ruta. No hay alternativa de escritura en la aplicación Tasks.
- Limitación deliberada del compilador existente: para crear Tasks a través de este seam cada revisión necesita una fecha de destino explícita que se pueda probar; un lote sin fecha sigue rechazándose, en lugar de inventar fechas/propiedades. El soporte general de Tasks sin fecha deberá hacerse como ampliación de contrato, no con una fecha ficticia.

## Evidencia y garantías

Pruebas tests/runtime/test_p4_multitask_batch.py: dos tareas reales datadas se crean como notas Task separadas, status pending, target_date exacto, dos receipts, replay de E3 sin duplicación; el flag apagado conserva abstención previa; propuesta que fusiona dos Tasks en un solo fact se rechaza antes de cualquier escritura; auditor que detecta WorkSession o lifecycle rechaza el lote sin mutaciones. 41 pruebas focales relevantes PASS. Gate transversal completo y despliegue DEV pendientes de cierre.


## Incidencia real y corrección de cardinalidad en revisión

- DEV `7cdafba` (solo sandbox): dos pruebas de Task-only `twotasks_a`/`twotasks_b` generaron dos Tasks distintas con fecha, status pending, readback físico por `/api/notes` y dos IDs indexados; `twotasks_c` generó solo una Task pese a dos obligaciones de la fuente: el auditor de cardinalidad respondió incorrectamente `exactly_one_operation=true`. La respuesta COMPLETED de ese caso fue **incompleta**. Otra prueba con lifecycle quedó needs_attention sin crear Tasks.
- Nueva rama NO DESPLEGADA: si el primer auditor Scope afirma una sola operación y está activo el flag opt-in, se solicita una segunda conclusión independiente con la fuente original y modelo diferente, siempre ANTES del Task delegate. Si ve varias, se revisa el lote entero y no se descarta la segunda; si contradice la clase Tasks-only o la cita fuente, se abstiene. No es un permiso para inferir identidades o fechas ambiguas. Dos revisores pueden coincidir erróneamente: no equivale a cobertura semántica garantizada.
- Regresión nueva con el primer auditor equivocado y el segundo correcto → dos Markdown Task y dos dictámenes; con auditor independiente que rechaza clase fuente → cero llamadas al delegate y ninguna escritura; con dos auditores de una sola operación → se conserva el delegate Task original. Un doble de test que simulaba COMPLETED sin recibo E3 legítimo falló de forma protectora; corregido para usar su delivery real y status NEEDS_ATTENTION en el test de enrutamiento, sin modificar seguridad productiva.
- Pruebas de rama: 36 focales PASS, `odyssey_cross_surface_gate.py` 988 Python + 174 JS PASS, acceptance ledger 18 invariants / 41 anchors PASS. Suite global tras arreglar dos tests desfasados de rutas `presence.js` y otro que fijaba una fecha antigua del snapshot de precios: **3927 Python PASS /80 SKIP/52 subtests PASS; nueve FAIL históricos exclusivamente de matrices/hashes/costes congelados**, sin regresiones nuevas. El gate transversal continúa PASS. Prueba del modelo fresco y validación de navegador en DEV **todavía pendientes**.

## Próximos pasos

Incorporar tests al gate permanente, completar batería, desplegar únicamente DEV, E2E real autenticado de dos tareas fechadas y negativo de WorkSession, consultar Tasks por API y Notes/Markdown para contar dos recibos. Revisar con cautela planes Task sin fecha y evidencias de futuras fechas; NO afirmar universalidad de multitarea por este primer lote.
