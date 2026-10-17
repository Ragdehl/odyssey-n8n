# P4 — ámbito por tipo y catálogo físico verificado (17-10-2026)

**Estado:** prototipo integrado solo en la rama P4 (opt-in en WholeSourceLightExecutor), DEV/PROD y notas privadas sin modificación. No se ha dado por superado el gate de navegador/n8n.

## Qué índices existían antes de esta ronda

- `ContextIndex` SQLite: `notes(id,path,type,primary_name,source_hash,tags,embedding)`, `properties(note_id,field,value,value_type)`, `note_projection` (alias/cuerpo), `note_links`, metadata de compatibilidad. **Ya sabe filtrar por tipo y propiedades** en consulta contextual; la pista de nombre de Router (`source_name_hint_candidates`) usa SQLite y revalida físicamente los resultados. Una ausencia en el índice no es prueba de ausencia en Markdown.
- `SemanticEntityIndex` SQLite: notas existentes y vector para *rankear candidatos*; la selección semántica no debe otorgar identidad sin evidencia adicional.
- El schema actual tiene **cero propiedades específicas de `person`, `project`, `concept` y `document`**. `person` ya lleva el tipo, el nombre y posibles `aliases` universales. Añadir `birthday`, relación familiar u otra propiedad tipada más adelante permite consultas adicionales, pero **no es requisito para buscar a una persona por nombre/alias/tipo**.

## Por qué se lee todo el vault aunque el target sea de un tipo

Las funciones que toman decisiones críticas de escritura o autoría no solo quieren localizar candidatos, sino detectar **duplicados o datos mal ubicados fuera de ese tipo/carpeta**, incluso si el SQLite derivado está atrasado. Revisado en código:

1. `odyssey_core/identity.find_exact_entity_candidates_batch`: lee, parsea y valida **todas** las notas antes de devolver un negativo/exacto/ambiguo por nombre y alias con filtro de tipo; un Markdown invalidado produce un fallo conservador.
2. `odyssey_core/temporal._assert_unique_day_identity`: comprueba TODOS los IDs/fechas, no solo la carpeta `calendar/days`, para detectar un Day duplicado o desplazado. Un Day se puede resolver hasta 9 veces en una sola petición.
3. `odyssey_core/identity_boundary.SelfBindingRepository._validate_person_target`: revisa que el `person_note_id` del usuario exista exactamente una vez, esté activo y sea tipo `person`, incluso si su archivo cambió de nombre/carpeta. Históricamente omite inválidos al hacer esta comprobación; la ruta nueva del catálogo opt-in los trata como incertidumbre y falla cerrado.
4. `odyssey_core/reference_preflight._find_existing_identity`: valida todos los documentos para demostrar la unicidad de un ID antes de permitir que el Writer lo use. `odyssey_core/persistence._find_duplicate_id` y otras rutas siguen siendo escaneos; este cambio NO los ha convertido en búsquedas SQL.

Es decir: **el filtro por tipo sí existe para búsquedas de recuperación, pero no equivale a una garantía completa de unicidad canónica**. No se deben confundir ambas clases de búsqueda.

## Qué se ha conectado, sin introducir una segunda autoridad

`odyssey_core/verified_metadata_catalog.py` ofrece un **catálogo efímero**, creado al primer uso y compartido por Core dentro de una única entrega P4. La primera consulta valida físicamente todos los Markdown con el schema vigente. Guarda únicamente metadatos verificados `{path, id, type, name, aliases, date, deleted, content_excerpt}` —NO un segundo almacén de facts—. Antes de cada nueva reutilización comprueba:

- Que la lista de rutas sea exactamente la misma (el `VaultRepository` comprueba el cambio de todos los directorios y crea el listado fresco cuando corresponde).
- Que cada ruta siga dentro del vault, no sea symlink escapado y conserve su versión real `device/inode/size/mtime_ns/ctime_ns`.
- Que el schema no se haya modificado incluso dentro del mismo objeto Python; cambios físicos o del schema fuerzan reconstrucción validada. Una fuente cambiada mientras se está construyendo provoca rechazo, no negativa falsa.
- Que no haya más de 20.000 rutas. Si se excede el presupuesto de esta optimización, los servicios vuelven al escaneo físico anterior; **no** se considera que las notas sobrantes no existan.

Consumidores P4: Calendar Day uniqueness, exact entity name/alias (mismo algoritmo de prioridad nombre/alias), `_find_existing_identity` de preflight y SELF. El catálogo **no escribe, no decide un ID nuevo, no salta Core Writer ni E2/E3 y no persiste entre peticiones**. Los consumidores sin ámbito P4 conservan sus algoritmos tradicionales. Una modificación externa, una duplicidad recién creada, un symlink, un Markdown inválido o una edición con mtime restaurado invalidan la prueba de referencia. `tests/core/test_verified_metadata_catalog.py` congela 8 escenarios adversariales, equivalencia con búsqueda normal y el criterio de no releer las fuentes ya verificadas en consultas repetidas.

## Benchmark: el beneficio depende de cuántas búsquedas haya

- **Una sola petición P4 con pocas referencias, 250 notas**: antes de este catálogo `759,4 ms`; con Day solamente `864,5 ms`; con exacta/ID `810,5 ms`; con SELF también `778,8 ms`. La diferencia residual frente a `759,4` es **+19,4 ms (peor, dentro del ruido de una medición corta)**. No afirmar aceleración de la ruta común.
- **Una sola petición P4 con 1.000 notas**: antes `3.040,9 ms`, con catálogo y cuatro consumidores `3.052,5 ms`; esencialmente igual. El O(N) global **no está resuelto**.
- **Diez búsquedas exactas sobre 250 notas** en el mismo ámbito P4, sin modelos ni embeddings: antes **288,18 ms, 2.500 llamadas de lectura**; con catálogo **152,33 ms, 250 lecturas**. Beneficio ~47% en ese escenario multiscope. Reproducir con `scripts/p4_verified_catalog_scope_bench.py` (notas sintéticas, sin proveedor, sin datos privados).

Por tanto, esta etapa **reduce repetición de lectura y búsqueda para mensajes complejos**, pero no debe comercializarse como aceleración general. Esta primera pieza es aún un catálogo derivado de verificación física, **no una nueva consulta SQL**. Usar el SQLite existente para búsqueda negativa con garantías todavía exige resolver su frescura externa.

## Decisión sobre facts

**Mantener una nota Markdown por entidad con múltiples facts atómicos**, sin cambiar el diseño acordado. `odyssey_core.atomic_facts.AtomicFact` ya identifica cada hecho por `(note_id, request_id, ordinal)` y su `locator` sin que haga falta que sea un archivo distinto. La próxima mejora razonable es una **proyección derivada por fact dentro de SQLite** (`source_note_id`, `fact_locator`, texto, fecha/anchors, links) para consultas selectivas, no un millón de Markdown ni otra autoridad. Las entidades siguen siendo agrupaciones legibles, sus facts se consultan indexadamente y cada cambio físico se comprueba/reconcilia con su nota canónica. Una separación física aumentaría el número de archivos, recorridos, enlaces y escrituras, y no resolvería la necesidad de validar IDs únicos.

## Próximo salto de rendimiento (no implementado aquí)

1. Ampliar **el ContextIndex SQLite existente** con un manifiesto de versiones físicas reconstituible y comparación eficiente de todos los nombres/rutas/versiones; reconciliar cambios externos y hacer fallback seguro ante cualquier desajuste. No basta un `SELECT` vacío contra el índice antiguo para crear una persona o Day.
2. Extraer en Core un puerto de consulta tipada de candidatos (`ID`, `nombre/alias`, `type`, y `property` cuando exista), de forma que Planner/preflight/Calendar/SELF utilicen **el mismo mecanismo**, revalidando físicamente únicamente las notas candidatas y la prueba completa de frescura antes de un negativo decisorio. La primera construcción del índice seguirá siendo O(N), pero debe salir del camino crítico habitual y ser incremental en Writer.
3. Medir concurrencia, E3 y cambios fuera de banda contra un snapshot de fichero real, con casos homónimos, duplicados y modificaciones justo antes de WRITE; ejecutar 20/250/1000/5000 con red y FastEmbed en entorno aislado. Hasta entonces conservar los guards físicos y no desplegar P4 en DEV.

## Evidencia de regresión

**Cierre validado 17-10-2026:** `CROSS_SURFACE_GATE PASS` **771 pruebas Python**, 65 archivos/9 grupos, **168 Node PASS**. El ledger de contratos permanece en **15 invariantes / 26 anclas**, sin autorizar P4 a DEV. Suite global **3.675 PASS, 80 SKIP, 52 subtests PASS y exactamente los mismos 10 fallos históricos de benchmarks/precios** (ninguna nueva regresión). Ruff y formato PASS; el hook de pytest completo del commit se omite por esos diez fallos históricos sin esconderlos.

No confundir pruebas unitarias/gate con navegador+n8n autenticado. Los cambios se mantuvieron estrictamente en `odyssey_core` (mecánica de consulta), `VaultRepository` como puerto físico read-only y el contexto opcional de P4; Tasks/UI usan sus reglas anteriores.
