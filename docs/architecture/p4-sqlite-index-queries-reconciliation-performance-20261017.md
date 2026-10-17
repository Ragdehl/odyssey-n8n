# P4 — consultas SQLite, inventario de fuentes, reconciliación y rendimiento (17-10-2026)

**Estado:** solo en worktree/branch `feat/light-router-poc-20261016`, sin migrar ni desplegar DEV/PROD ni tocar datos privados. Sigue prohibida la promoción P4 sin E2E navegador real+n8n. La implementación mantiene Markdown canónico y E2/E3/CAS; todo SQLite es proyección derivada de notas.

## 1) Inventario SQLite que incluye también los descartados (formato 6)

`ContextIndex` formato 5→6 añade `vault_inventory`: una fila por Markdown validado, **también los soft-deleted**, con ruta, ID, JSON del frontmatter, SHA, excerpt, nombre normalizado y versión física `(ruta física, device, inode, tamaño, mtime_ns, ctime_ns)`. Añade `vault_aliases` normalizados NFC+casefold+espacios para **todos** los IDs. Índices `vault_inventory_name`, `vault_aliases_name`. Los índices 4/5 se reconstruyen antes de consumirse; `schema_digest` pinnea exactamente el schema compuesto vigente.

**Importante:** `vault_inventory` complementa (no duplica autoridad de) `notes`/`note_attributes`/`note_aliases`/`note_facts`/`note_links` que son solo de notas activas. No descartar eliminados del inventario: un ID de una nota soft-deleted puede seguir en conflicto con una nueva nota. Un inventario SQL que ignore esos IDs no permite demostrar la ausencia de duplicados.

`VaultRepository.note_version_snapshot()` obtiene las versiones de los Markdown en una única pasada `scandir`, sin seguir symlinks, comparando directorios antes y después de enumerarlos. Se utiliza como **detector de cambios**, no como hash de contenidos ni reemplazo de re-grounding. La versión se comprueba con la lista física actual; los resultados seleccionados se leen, validan y comprueban contra SHA e ID de Markdown. Las notas fuera del índice, rutas distintas, ediciones del mismo tamaño con mtime restaurado, symlinks externos, deletes, cambios de schema o versiones incompatibles niegan la prueba de completitud y obligan a scan de fuente o rechazan una consulta según contrato.

### Consumo productivo P4 (sin cambiar Legacy ni PROD)

`WholeSourceLightExecutor` activa `scoped_verified_metadata_catalog(index_path=context_index.path)` en el ámbito de una única entrega. Si el inventario físico corresponde al SQLite, `identity.find_exact_entity_candidates_batch`, `reference_preflight._find_existing_identity`, `SelfBindingRepository._validate_person_target` y `CalendarDayRepository._assert_unique_day_identity` reutilizan las filas físicamente comprobadas sin volver a parsear todos los Markdown. Si el inventario no coincide, regresan al catálogo físico completo (o rechazan cuando el fuente es inválido). Nunca asigna identidades por un simple `SELECT` sin pruebas. No hay caché entre peticiones ni nueva vía de escritura.

`odyssey_core.indexed_queries.CoreIndexedQueries` expone **una interfaz Core read-only** para `by_id`, `exact_names` con normalización de alias Unicode y filtro de tipo, `by_attribute`, `facts`, `links` salientes y backlinks por `target_id`. Utiliza SQL indexado, pero exige antes el inventario completo y hace `read_text+parse+validate+SHA` de los resultados positivos. Para nombre/alias se revalida la coincidencia exacta con la nota real; para links, su texto en la nota fuente y la unicidad del destino; para facts, el locator y texto del marcador canónico. Los resultados son evidencias/candidatos, nunca instrucciones del Writer. Exceso de matches, SQLite obsoleto, malformado o sin hash coherente **falla cerrado**, no trunca resultados silenciosamente.

## 2) Reconciliación incremental de cambios externos (sin reconstruir embeddings no afectados)

`ContextIndex.reconcile_external_changes` es una operación explícita de mantenimiento derived-only: compara el manifest SQLite con el vault, detecta altas, borrados, rename de ruta, cambios de nombre, alias y metadatos; lee/parses **solo** los Markdown cambiados y pasa todos sus IDs (incluidos IDs antiguos de rutas movidas/borradas) a `refresh_notes`. Es conservador: por defecto máximo 64 IDs cambiados, máximo técnico 256, contrato de esquema/modelo compatible y ninguna entrada Markdown inválida, duplicada o concurrentemente alterada. Si no puede demostrar consistencia, **rechaza sin convertir SQLite en autoridad**. No modifica Markdown; la ruta de reconciliación no se invoca automáticamente durante el Writer por riesgo de concurrencia y consumo de recursos: la factoría P4 continúa con su bootstrap de validación de índices, y el índice stale hace fallback físico.

`ContextIndex.refresh_notes` ya no reabre y parsea todos los Markdown para una escritura ordinaria. Compara físicamente **todas las versiones** contra el inventario previo, y solo lee/valida/re-embebe IDs afectados. Los cambios ajenos bloquean incremental y el runtime conserva su mecanismo ya existente de fallback de reconstrucción segura. Rebuild atómico del contexto y semantic/app indices continúa disponible; índices derivados corruptos no modifican la fuente.

## 3) Arranque P4 sin reconstrucción completa cuando nada ha cambiado

Antes, `build_runtime_from_environment` llamaba incondicionalmente a `refresh_indexes()` durante **cada arranque**, reconstruyendo embeddings de Context, SemanticEntityIndex y semantic de cada App aunque el vault fuese idéntico. Ahora **solo si `ODYSSEY_LIGHT_SOURCE_V1=1`** se llama a `p4_indexes_reusable` para cotejar el inventario físico completo, schema y modelo, todas las filas activas `(id,path,type,name,SHA)` del contexto y los equivalentes del índice semántico general y de cada App, incluidos `canonical_types` y modelos/versions. Si TODO cuadra, se conservan los índices byte idénticos; si falta uno, es viejo, hay drift, se modificó el schema/modelo o está corrupto, se llama al rebuild original. Legacy/DEV/PROD mantienen el comportamiento anterior hasta promoción formal P4.

Un benchmark sintético con **250 Notes** y embeddings deterministas (`scripts/p4_index_boot_isolated.py`) midió construcción de ambos índices **153 ms** y comprobación/reutilización **24 ms**, con detección de drift **10 ms**. No extrapolar estas cifras directamente a FastEmbed real: en otros benchmarks, preparar 1.000 Notes completas con el harness costó ~80 s; ahorrar ese trabajo en reinicios solo se concretará en DEV tras E2E y benchmarks reales.

## 4) Riesgos y próximos pasos

- **O(N) reducido, no eliminado:** el inventario físico completo aún requiere `stat/scandir` del vault, pero ya no multiplica parsing de Markdown por cada preflight/Calendar Day. En vaults grandes hay que valorar un seguimiento local de cambios de directorios con reconciliación, sin afirmar un snapshot atómico donde no lo hay. La escritura final sigue protegida por CAS, E3 y verificaciones de identidad de Core.
- **Concurrencia entre proceso externo y escritura:** no existe aún un journal compartido entre aplicaciones externas que modifiquen Markdown. La coincidencia de `device/inode/mtime/ctime` es evidencia de versión física, no una garantía criptográfica frente a un actor que pueda falsificar deliberadamente timestamps/inodes. Las consultas positivas sí re-hashean la fuente; un negativo prewrite fuera de la transacción de dominio debe continuar siendo conservador. Este gate no sustituye pruebas de carrera reales.
- **Semántica de enlaces:** `note_links`/`note_fact_links` siguen siendo wikilinks explícitos, no todas las posibles menciones lingüísticas. SELF procede del binding autenticado, no de los links; futuras propiedades (`birthday`, relación con usuario) se incorporan al schema cuando se definan, no se inventan en SQLite.
- **Reconciliación semántica/app:** aún queda medir y optimizar los scans propios de `SemanticEntityIndex.refresh_notes` y de índices de Apps en escrituras; el cambio de Context por sí solo no los elimina. No introducir un índice extra si el catálogo existente cumple.
- **Adopción P4:** tras pruebas de escala y riesgo, quedan las subtareas dependientes Chat↔UI, grupos N:M, crash E3 y navegador autenticado→n8n real→GPT→Markdown→donut/graph/historial en vault desechable; solo entonces autorizar DEV para pruebas personales.

## Evidencias

- `tests/core/test_indexed_queries_and_freshness.py`: lecturas sin parse de todo Markdown con índice completo, por ID/alias/tipo/propiedad/facts/links, negativas stale, alta/rename/borrado/soft-deleted, mtime restaurado, hash falso, alias/link SQL manipulado, reconciliación incremental, duplicados, inválidos y presupuesto.
- `tests/core/test_vault_repository.py`: escaneo por lote equivalente a `file_version`, cambio físico, symlink externo y directorio symlink, caché previa adversarial.
- `tests/runtime/test_p4_index_startup_reuse.py`: modelos/esquemas compatibles, índices de Apps, ausencias y drift que impiden reutilizar; nada de producción modificado.
- `scripts/p4_product_scale_isolated.py`: latencia sin modelo ni navegador, 20/250/1000 notas con fuente sintética y métricas de refresh incremental/rebuild.
- `scripts/p4_index_boot_isolated.py`: coste build vs comprobación de reutilización.

## Cierre medido 17-10-2026 (rama P4 únicamente)

**Tests:** Gate transversal **805/805 Python PASS** (68 archivos, 9 grupos), **168/168 Node PASS**. Ledger de aceptación **15 invariantes/26 anclas PASS**, y conserva explícitamente `P4 DEV UNAUTHORIZED`. Suite global: **3.709 Python PASS**, **80 SKIP**, **52 subtests PASS**, exactamente **10 FAIL históricos previos** de contratos congelados de benchmark/precios (ninguna regresión nueva). Ruff/format y `git diff --check` PASS. El hook pre-commit que ejecuta pytest global no puede dar verde mientras sigan los fallos históricos; no declarar CI verde ni cambiar silenciosamente presupuestos autorizados.

**Rendimiento P4 provider-free, Raspberry Pi 4 GB (mismo harness con vault descartable):**

| Notas extra | Baseline previo a los 3 bloques | Ruta nueva | Mejora de latencia de petición |
|---:|---:|---:|---:|
| 20 | ~86,9 ms | **80,8 ms** | ~7 % |
| 250 | ~795,5 ms | **656,0 ms** | ~17,5 % |
| 1.000 | ~3.052,5 ms | **2.508,4 ms** | ~17,8 % |

1 refresh incremental/0 full rebuild por petición. **Tiempo de preparación de 1.000 notas ~81,2 s**: coste del harness preparando índices de cero, NO del mensaje. Tiempos de arriba sin modelo, red, n8n ni FastEmbed con latencia real de tokens. El O(N) físico aún no desaparece. El profiler con herramientas añadidas seguía mostrando miles de accesos al vault; `note_version_snapshot()` ha reducido parte de ese coste usando `scandir` en bloque, no eliminando la prueba física.

**Arranque sintético de 250 notas**, índices Context+Semantic de prueba: construcción **152,76 ms**, reutilización verificada **24,48 ms**; tras modificación del Markdown el check rechaza reutilizar en **10,32 ms**. Estas cifras NO extrapolan el ahorro exacto del FastEmbed real. Cambios de source/schema/modelo/índices de Apps fuerzan rebuild; con `ODYSSEY_LIGHT_SOURCE_V1` desactivado continúa el bootstrap tradicional.

**Estado operativo y limitaciones:** Commit de checkpoint en branch tras los gates. DEV sigue instalado en `1474681`, PROD y notas personales sin cambios. El conector de consultas `CoreIndexedQueries` ya existe y tiene pruebas de grounding/frescura, pero **no todos los consumidores legacy ni todo el Planner están migrados a esta interfaz**; la mejora del circuito P4 viene sobre todo del inventario completo compartido, el refresh parcial y el escaneo de stat por lote. `reconcile_external_changes` es una API de mantenimiento explícita, **no un demonio de vigilancia** ni reparación automática de todas las clases de drift. No existe snapshot transaccional compartido con editores externos. Para completar P4 siguen pendientes los flujos N:M/subtareas Chat↔UI, recuperación de ciertos crashes E3 y **el E2E autenticado real navegador→n8n→modelos→Markdown→graph/donut/historial** sobre datos descartables. No autorizar todavía DEV.
