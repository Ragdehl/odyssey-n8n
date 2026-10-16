# P4 — Task referida dentro de un mensaje: contrato tipado E2/E3 sin mutación paralela

## Estado y alcance

Rama `feat/light-router-poc-20261016`. **Módulo y recorrido de consumidor probados sobre vaults temporales, pero todavía NO cableados en el Router/Planner P4 del producto.** No se han ejecutado llamadas nuevas de proveedor para esta nueva revisión dependiente, ni navegador+n8n real. DEV `1474681` y PROD sin cambios. Estado vinculante: `functional-roadmap.md`.

## Hallazgo verificable de diseño

Core **sí puede producir** una prueba `CanonicalReferenceEvidence` de tipo `task` desde su Writer general, después de registrar un hecho fechado con un enlace físico a una Task ya existente. No hay que deducir una Task de un Note `person`, crear un ID artificial o escribir directamente en Markdown. Una prueba puede transportarse junto con su origen literal y hash actual mediante `odyssey_core/source_bound_dependency.py`. La fuente y el objetivo se vuelven a comprobar contra el vault actual con la autoridad común de Core.

`odyssey_apps/tasks/dependent_target.py` añade una frontera específica de Tasks `prove_dependent_task_target`. Verifica que:

- La interpretación **existente** de Tasks corresponde exactamente al segmento original dependiente, posee una sola referencia textual al objetivo y contiene una operación Work Session soportada (inicio, parada, edición o actividad asignada a una Task), o bien `CREATE_SUBTASK` con un solo `TaskRelationshipMention(PARENT_TASK)` anclado en el texto dependiente.
- **Dos revisiones de texto** coinciden sobre el mismo antecedente, el tipo `task`, la mención dependiente, y también la operación solicitada; sus campos de texto deben coincidir byte a byte con el mensaje íntegro. Esas revisiones *no* proporcionan IDs ni autoridad de escritura.
- Core realmente produjo la única referencia sobre una Task, en una operación terminada, y su link es vigente en Markdown físico. Si Core probó solo una persona, un alias dudoso, un referente repetido o un hecho cuyo documento fue editado, la prueba falla cerrada.
- `TaskDependentTarget.require_current` vuelve a comprobar el hash y el tipo de las Notes fuente/destino **inmediatamente antes de usar el objetivo**. No se ha creado otro Writer ni resolvedor de identidad, y el contrato no muta nunca el vault.

El esquema cerrado `DEPENDENT_TASK_TARGET_REVIEW_SCHEMA` y dos instrucciones de auditoría independientes se han incluido en la capa de contratos de modelos productivos, con test que verifica `strict=True` (todos los campos obligatorios, sin campos extra), y sin incluir IDs en respuesta. **Limitación relevante:** los tests locales suministran las dos respuestas congeladas; probar las llamadas reales a dos modelos es responsabilidad del futuro coordinador integrado y de un gate de GPT nuevo, no puede darse por demostrado a partir de dos diccionarios de test.

## Pruebas físicas y replay

`tests/runtime/test_p4_dependent_task_target.py`: Core `execute_request` auténtico en Markdown sintético enlaza un hecho `calendar_day` a una Task existente de tipo `task`. La prueba física se transporta al contrato Tasks, que la verifica y entrega su ID acreditado al **mismo** `TaskWorkSessionService.start` que usa la API Notes/UI; Notes muestra la sesión y le añade actividad. Una segunda sesión simultánea se rechaza por el guard real del dominio.

Se comprueban operaciones inesperadas, referencias a personas, fuente alterada, una de dos auditorías discordante, `operation_supported=false`, ambigüedad, extras que intentan inyectar un ID, identidad Core falsificada, caducidad si la Task o la nota fuente cambian y conflictos de `expected_revision`/`expected_source_hash` (CAS) en el servicio original de Tasks. Un consumidor de prueba que ejecuta una Work Session bajo **la puerta E3 productiva** atraviesa HTTP localhost real: primer resultado 200, replay del mismo request ID sin escrituras, conflicto de distinto texto con el mismo ID rechazado. Si se simula una caída entre la escritura de Work Session y el recibo, E3 deja el claim sin resultado, bloquea el reintento y no crea otra sesión. Esto demuestra una frontera de seguridad real; **no demuestra** que el Router P4 ya genere o consuma este tipo de handoff automáticamente.

Se ha añadido la suite al `scripts/odyssey_cross_surface_gate.py` y al ledger acotado de 15 contratos; sus selectores declaran solamente evidencia determinista/HTTP local. El gate requiere obligatoriamente **navegador autenticado → n8n real → GPT → Markdown → navegador**, y no se ha rebajado.

## Pendiente crítico

El coordinador P4 todavía no produce subsegmentos dependientes tipados, no obtiene en todos los caminos Task IDs mediante Core y no invoca las dos auditorías para cada transición. Faltan un contrato genérico de grupos dependientes con fuente completa N:M, resolver `Task CREATE/UPDATE` y `parent_task`/subtareas sin introducir un escritor nuevo, el contexto temporal compartido, el caso `person` que solo puede devolver aclaración, y el gate E3 de escritura incierta con reconcile no duplicante. No se debe enchufar el nuevo adaptador a Work Sessions de P4 hasta satisfacer estas precondiciones, ni aceptar un split de dos frases si el anclaje de su referencia no está demostrado.

## Extensión verificada: subtarea con Task-padre acreditada

El mismo adaptador distingue además un `TaskOperation.CREATE` acompañado de **un único** `TaskRelationshipMention` con `role=PARENT_TASK`, rechazando otros vínculos, objetivos, referencias repetidas o una operación de creación normal que no menciona un padre. Exige auditorías `operation=CREATE_SUBTASK` / `operation_supported=true`, y el parent ID proviene **solamente** de la prueba de Core vigente.

`tests/runtime/test_p4_dependent_task_target.py::test_core_proven_parent_task_is_usable_by_existing_subtask_ui_service` materializa realmente una Task hija con `TaskDirectMutationService.create_subtask`, pasando los tokens `expected_revision`/`expected_source_hash` del padre al gate E3 existente. Verifica Note hijo pendiente, title explícito, el hecho «Tarea superior:» y el wikilink físico al padre. Cuatro negativas rechazan revisión de operación, referencia de tipo persona o antecedente dudoso SIN escribir. Esto demuestra que el mismo objetivo canónico de Core es consumible por la operación de subtareas **desde el servicio de dominio ya instalado**. No demuestra todavía cómo el Planner productivo extraerá el título de la frase dependiente: en la prueba se entrega un título literal de fixture. No hay cambios a la ruta P4 ni validación GPT de este nuevo uso.

## Prueba de ensamblaje productivo sin navegador

Se añadió un paso E2E **más cercano al producto**: `tests/runtime/test_p4_production_composition_task_ui.py` levanta `build_runtime_from_environment()` de la rama con sus mismas instancias **reales** `ContextIndex`, `SemanticEntityIndex`, `VaultRepository`, `SelfBindingRepository`, `TaskWorkSessionService`, `NotesQueryService`, `RuntimeComposition`, E3 y adaptador TCP localhost. Entorno `ODYSSEY_LIGHT_SOURCE_V1=1`, `ODYSSEY_ENABLED_APPLICATIONS=tasks`, roots de datos y cache de embeddings **completamente desechables**. La parte de IA es congelada (`RecordedClient` Router/auditor y `TaskInterpretation` inyectado); se usa `ConstantEmbedder` y `UnresolvedReasoner` para evitar red, `FastEmbed` y costes. El mensaje Tasks-only llega a la `execute_tasks` genuina (no al stub `task_delegate`), resuelve la Task en el índice/Markdown, inicia la sesión por el servicio de dominio, persiste recibo E3, la misma API Notes agrega actividad, el HTTP `POST /notes` refleja esa misma sesión y la petición repetida por TCP retorna el recibo sin volver a interpretar. No hay Task ficticia o segunda escritura por replay.

**Diferencia frente a pruebas anteriores:** esta sí comprueba el cableado del factory productivo hasta Tasks+Notes, aunque **no** cubre el salto dependiente Core→Tasks, ni n8n, navegador, GPT genuino, embeddings reales, ni gráfico/donut. El gate final de adopción permanece bloqueado.

## Resultados transversales finales

Pruebas con schema estricto y módulos Core+Tasks existentes: `scripts/odyssey_cross_surface_gate.py` **688 Python PASS y 168 Node PASS** en 60 archivos/9 grupos. Suite Python global: **3613 PASS, 80 SKIP y los mismos 10 fallos históricos preexistentes** de hashes/pricing/benchmarks (52 subtests PASS); sin nuevas regresiones observadas. El checker mantiene 15 invariantes, 26 anclas y rechaza la promoción a DEV. La nueva prueba del ensamblaje productivo ya está incluida en el gate. El contrato de destino de Tasks se exporta a través de `odyssey_apps.tasks`, sin modificar las rutas de ejecución existentes ni instalar en DEV.

**Importante:** no hubo pruebas nuevas de GPT para el enlace dependiente; la revisión doble sigue congelada y hay que demostrarla con modelos reales y el coordinador semántico de P4. Las pruebas del factory sí corren las clases productivas de Tasks/Notes/Core/E3 y HTTP local, pero no n8n/navegador.
