# P4 — Referencias dependientes: evidencia canónica, protección y límite Task (16-10-2026)

**Estado:** primera protección productiva de Core + puerta de procedencia E2 read-only, **NO** ejecución completa de Task/Work Session dependiente. Única fuente operativa: encabezado activo de `functional-roadmap.md`. Rama `feat/light-router-poc-20261016`, sin deploy DEV ni PROD y sin tocar Notes personales.

## Hallazgo estructural y corrección

La arquitectura anterior **ya contiene** `CanonicalReferenceEvidence`, `_dependent_evidence_is_current` y `DependentReferenceGuard` de Core, además de `DependentRouteHandoff` en el Router híbrido legacy. El guard de Core verifica **antes de WRITE** tanto el hash/identidad del documento que persistió el enlace como el hash/identidad del Note canónico referenciado; también exige un marker real en el plan de escritura. Por tanto NO se ha creado un segundo resolvedor de identidades ni un nuevo Writer.

El nuevo P4 `WholeSourceLightExecutor._partial` anteriormente devolvía, sin revisión de todo el mensaje, **la evidencia canónica de la última suboperación**. Un mensaje real sintético «Hoy he conocido a Maite, mañana tengo que llamarla» produjo dos hechos y dos pruebas canónicas independientes para la misma persona; solo se mostraba la última prueba en el `ApplicationResult`. Era una selección por orden de ejecución, no por autoridad E2. La corrección conserva un único carrier **solo cuando hay exactamente una prueba canónica entre TODAS las suboperaciones y el resultado total es completed**. En caso contrario devuelve el carrier vacío. Una excepción de readback físico que convierte un resultado en partial elimina explícitamente el carrier. Continúa empleándose el agregador común `routing._aggregate` para acciones, history, affected IDs, pending, etc.

## Prueba y transporte E2 sin autoridad de escritura

`odyssey_core/source_bound_dependency.py` añade `prove_source_bound_dependency()` y un `SourceBoundDependency` **interno/read-only**. No interpreta pronombres, no autoriza Tasks ni selecciona operaciones. Antes de transportar un posible antecedente exige:

- Fuente original completa no modificada, un antecedente literal seguido del texto dependiente sin pérdida/reordenación de caracteres; referencia y persona acreditada con menciones únicas en su tramo original.
- Resultado previo `ApplicationResult.COMPLETED` con **exactamente una** prueba `CanonicalReferenceEvidence`, coherente con una prueba en su resultado real de acción y con la nota fuente efectivamente afectada por Core (no un carrier adjuntado arbitrariamente).
- Coincidencia literal acreditada entre mención original y nombre canónico; alias y casos con varias posibles entidades no se promocionan automáticamente.
- Revalidación física `_dependent_evidence_is_current` contra el Markdown actual tanto de fuente como de destino. Si una nota cambia, la prueba deja de valer.

El método `core_write_guard()` produce el `DependentReferenceGuard` **existente** para un futuro consumidor de Core: sin un marker y un plan Core válido, el guard rehúsa la escritura. Esta prueba lexical/física **NO demuestra por sí misma** que «ella» se refiera a la persona anterior. Una interpretación y auditoría semánticas independientes deben acreditar esa relación, bajo el contexto de SELF autenticado y en la misma reserva E3, antes de cada acción.

Tests `tests/core/test_p4_source_bound_dependency.py`: resultados reales de Core y Markdown temporal, casos alterados/múltiples en texto, caso `Maya` con un carrier único; caso `Maite` con dos apariciones y ningún carrier promovido; proof falso separado de sus acciones, source Note no afectada, alias no probado, target/source cambiados físicamente, status partial, y veto real de `DependentReferenceGuard` si falta el marker. La nueva batería entra en `scripts/odyssey_cross_surface_gate.py` y la selección de pruebas del registro de aceptación se mantiene acotada y auditada.

## Por qué esto todavía NO permite una Work Session anafórica

La evidencia Core puede acreditar **una persona** que aparece en un hecho, pero Tasks Work Sessions necesitan una **tarea canónica existente**. No puede convertirse automáticamente un `person` Note ID en un `task` Note ID, aunque el contexto mencione una presentación «de ella». Antes de autorizar `start/stop/edit` deben existir una tarea concreta, operación Tasks interpretada y todos los controles de estado y concurrencia del servicio de Work Sessions. Tampoco puede asumirse que el hecho «conocí a Maya» crea una Task. El camino Tasks-only independiente sigue funcionando, pero el enlace Core→Tasks dependiente se queda bloqueado mientras falte evidencia tipada de destino y contrato de operación.

**Para completar el bloqueo:** extender la composición E2 con una ruta dependiente que conserve spans originales y una relación semántica auditada, reciba solo la prueba canónica vigente de Core, y pase a Tasks exclusivamente un objetivo `task` probado mediante su resolvedor/servicio habitual. Si el antecedente solo demuestra una persona, bloquear la mutación (o solicitar la Task exacta), sin inferencias ni reemplazar texto por un nombre inventado. Conectar el gate E3 único y probar reintentos + navegador/n8n/Markdown/UI auténticos. Otras puertas siguen pendientes: crash postwrite sin recibo, rendimiento O(N) y prueba visual real.

Ninguna prueba aislada ni sonda GPT revalida por sí sola el lanzamiento de P4 en DEV: sigue `verified_real_browser_n8n=false`. La Raspberry mantiene carga y swap elevados, sin levantar segundo navegador ni instancia n8n.

## Hallazgo adversarial posterior: Task falsamente inferida de un futuro indicativo

Se repitieron los diez casos con GPT **nuevo** tras la corrección de carriers. **Resultado real: 9/10**. El caso sintético «Hoy compré pan y mañana compraré leche» devolvió **HTTP 500** después de persistir exactamente un hecho, y el replay idéntico fue **HTTP 409** por claim incierto. La defensa E3 funcionó (no duplicó el hecho), pero P4 no cumplió la expectativa funcional de dos hechos. **No ocultar este fallo bajo la suite offline verde**. El script de pruebas previo NO archivaba las respuestas GPT por etapa y no permite atribuir con certeza la excepción original a un proveedor o Core.

Una nueva ejecución aislada de diagnóstico del **mismo mensaje** mostró un problema semántico reproducible en la entrada: el Router llegó a proponer `separable` Core+Tasks para dos hechos personales sobre fechas diferentes. Esa ejecución diagnóstica fue bloqueada sin escribir nada por el auditor de partición. El resultado indica una ruta de fallo plausible pero **no prueba** que sea la única causa del HTTP 500 anterior.

Corrección transversal, sin `if` por frase ni aceptar el plan del Router como autoridad:

1. `ROUTER_INSTRUCTIONS`, el auditor `TASK_ONLY_SCOPE_PROMPT` y los dos modelos de partición E2 distinguen explícitamente futuro indicativo/plan personal de una nueva obligación, recordatorio, tarea o operación de Work Session. Un evento futuro SIN obligación no se convierte en Task CREATE.
2. `WholeSourceLightExecutor._execute_independent_scopes` ejecuta ahora la **auditoría independiente de TODOS los fragmentos Tasks antes del primer WRITE Core**. Guarda solo el recibo de auditoría de ese mismo fragmento, y la ruta Tasks secundaria lo vuelve a validar por fuente exacta y exclusividad. No hay doble llamada de revisión en la ejecución normal. Un fallo de proveedor, incongruencia de fragmento o un `only_task_semantics=false` bloquean el mensaje completo sin dejar un Core fact parcial.
3. Nuevos tests adversariales congelan una propuesta falsamente `core+tasks` e incluso una auditoría de independencia erróneamente aprobada: la auditoría Tasks correcta responde `false` y se demuestran **cero escrituras**, recibo E3 replayable y ninguna invocación a la mutación Tasks. Otro test inyecta caída del proveedor en la revisión Tasks previa a escrituras. `tests/runtime/test_p4_model_contract_strict_schema.py` comprueba que las instrucciones de esta distinción forman parte de los prompts **realmente usados** por los cinco actores semánticos.

**Límite:** esto previene una clase de efectos parciales evitables si el auditor Tasks se pronuncia correctamente, pero un modelo podría seguir equivocándose. No reemplaza el intérprete Tasks, Core readback, validación E2/E3 ni recupera un claim incierto del experimento temporal. Para evaluar estabilidad se están ejecutando repeticiones GPT con un vault completamente nuevo en cada ensayo; resultados se añadirán aquí y al roadmap tras completarse, sin modificar instalaciones ni datos personales.

## Nuevas pruebas de proveedor tras la protección E2 prewrite

Con cuatro vaults temporales **completamente nuevos**, cada uno con Router/Planner/auditores GPT de proveedor NUEVO, el mensaje sintético de dos hechos fechados se comportó **4/4** como Core: HTTP 200, `completed`, dos hechos físicos en fechas distintas, cero Task nueva, **replay E3** sin cambios físicos. Logs privados de la Pi: `/tmp/odyssey-p4-future-indicative-recheck.log`. La tasa anterior 9/10 (un fallo real con HTTP 500 tras primer hecho) se conserva arriba como evidencia histórica, no se reescribe como 10/10.

Para controlar efectos secundarios, la ruta P4 mixta independiente Core+Work Session se probó **2/2** veces con GPT nuevo de Router, validadores E2, Core Planner y TaskInterpreter separado real: en ambos casos completó, dejó una preferencia en SELF, creó una única Work Session sobre Task de fixture, interpretó `START_WORK_SESSION`, no duplicó nada tras replay y no tocó ningún vault real. Archivos de la Pi: `/tmp/odyssey-p4-independent-after-prewrite-live.log`. La Task mutation en esa prueba usa la implementación auténtica `TaskWorkSessionService`, pero el delegate del fixture recibe una Task ya autenticada; NO es el recorrido integral de su resolución real en navegador+n8n.

**Gate actual transversal:** 658 Python PASS, 168 Node PASS, 58 archivos/9 grupos; el checker de aceptación confirma 15 invariantes y 26 anclas válidas y sigue marcando `P4 DEV UNAUTHORIZED`. Suite global Python **3583 PASS, 80 SKIP, 10 fallos históricos** de benchmarks/precios congelados (52 subtests PASS), sin nuevas regresiones observadas. No se han manipulado DEV, PROD ni sus Notes. Dos ejecuciones reales con GPT de Core+Work Session siguen `completed` tras el precheck.
