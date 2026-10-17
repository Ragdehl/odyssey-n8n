# P4 — Por qué SQLite no evita aún leer miles de notas (17-10-2026)

## Resultado medido, no hipótesis

En la Raspberry Pi de 4 GB, con el P4 productivo de Core/Writer/E3, usuario SELF sintético, embeddings deterministas y un vault efímero de 250 notas adicionales, `scripts/p4_source_hotpath_profile.py` capturó **31 enumeraciones del vault, 8.086 lecturas Markdown, 9 resoluciones de Calendar Day y 4 comprobaciones SELF** en una sola petición. Perfil instrumentado sin caché de lectura: 3.346,6 ms, incluyendo 1.407,5 ms en lectura I/O y 537,8 ms en enumeración, con coste extra del perfilador. `CalendarDayRepository.resolve` revalidaba nueve veces fechas/IDs y `reference_preflight`, `identity_boundary` y `whole_source_readback` repetían escaneos/parseos. Los 3,35 s NO son el tiempo normal de la misma petición; el benchmark sin perfilador (250 notas) era ~1.019 ms, y a 1.000 notas ~3.971 ms, sin red/GPT.

**Los SQLite ya existen y se utilizan**, no son información ausente:

- `ContextIndex` contiene tablas `notes` (ID, ruta, tipo, nombre, SHA), `properties`, `note_projection` (texto y alias) y `note_links`, además de embeddings; sirve para búsqueda/contexto, filtros y nombres sugeridos. `source_name_hint_candidates` ya consulta SQLite sin leer todas las notas y verifica físicamente los resultados con SHA/ID/tipo.
- `SemanticEntityIndex` mantiene la tabla `notes` con vectores, nombres, tipos, ruta y SHA para clasificar candidatos a identidad.
- Estos índices son **proyecciones derivadas**, no pueden certificar por sí solos que NO exista una identidad duplicada ni que una nota haya sido editada externamente desde su última actualización. Es justamente por eso que preflight, SELF, unicidad de Calendar Day y resolución de referencias consultan Markdown directo y, hoy, varias veces.

## Mejora contenida implementada en esta ronda

Se añadió `VaultRepository.scoped_unchanged_reads()` como una caché **opcional, por petición/contexto**, usada solo por `WholeSourceLightExecutor` P4. No modifica Core Writer, planificadores, ontología, identidad, prioridades SQLite ni el formato Markdown.

- Antes de reutilizar el contenido de un archivo se vuelve a resolver su ruta, se comprueba que siga dentro del vault y se contrasta (ruta física, dispositivo, inode, tamaño, `mtime_ns`, `ctime_ns`). Si cambió, se vuelve a leer la fuente; no se devuelve un antiguo contenido por estar en memoria.
- Antes de reutilizar una enumeración de rutas se comprueba la versión de **todos los directorios previamente enumerados**, incluso tras un cambio de subdirectorio; si un directorio cambia o desaparece se vuelve a recorrer el vault. Si un directorio cambió durante la enumeración inicial, no se guarda esa lista como negativa segura. Copias del listado devueltas a código de cliente no permiten modificar el cache.
- `create_text`, `replace_text` y `remove_text` invalidan inmediatamente las copias de la nota afectada y el listado; lecturas fuera de la petición no comparten caché. Límites explícitos: máx. 4.096 notas de texto, 8 MiB de bytes y 20.000 rutas en el índice temporal; fuera de esos presupuestos se continúa sin caching, no sin verificación.
- Las protecciones de E2/E3, validación de schema, SHA de índices, comprobación de unicidad y Writer **se siguen ejecutando sin cambios**. No se introduce un ID/alias derivado de SQLite como autoridad.

Pruebas adversariales añadidas en `tests/core/test_vault_repository.py`: nuevo o eliminado fichero durante petición, modificación externa por replace atómico, edición del mismo tamaño tras restaurar `mtime`, reemplazo por symlink fuera del vault, directorios creados/borrados externamente, cambios con el propio Writer, petición siguiente, ámbito anidado y presupuesto de memoria. La batería de ruta `tests/runtime/test_whole_source_light_product_p4.py` y Work Sessions factory sigue ejecutando Writer/HTTP/E3.

**Benchmark P4 sin modelos/Red (no cProfile)** en el mismo dispositivo:

| Notas adicionales | Antes, ms | Después, ms | Reducción aprox. | Refrescos incrementales | Rebuild |
|---:|---:|---:|---:|---:|---:|
| 20 | 102,7 | 79,2 | 23 % | 1 | 0 |
| 250 | 1.019,0 | 759,4 | 25 % | 1 | 0 |
| 1000 | 3.971,4 | 3.040,9 | 23 % | 1 | 0 |

Preparar desde cero los índices de 1.000 notas tardó ~82,4 s en la nueva prueba (antes 78,9 s): esos tiempos de construcción no son el tiempo del mensaje. El benchmark sigue teniendo contenido y embedder sintéticos; no prueba p95 en uso real ni memoria de FastEmbed. La mejora es medida, pero el O(N) de Core permanece y 3 s sin GPT a 1000 notas sigue siendo demasiado.

## Siguiente cambio arquitectónico recomendado (sin introducir una segunda autoridad)

1. **Usar mejor las tablas SQLite existentes para localizar candidatos** por ID/nombre/alias/tipo/fecha. Ya están parcialmente, pero no los consumen todas las rutas Core. Centralizar esa consulta en un único servicio Core y devolver rutas tipadas y fuente hash, sin escribir desde SQLite.
2. **Introducir un catálogo/versionado del vault con reconciliación de cambios externos** (archivo y directorios), derivado y reconstruible. La escritura canónica actualiza su manifest bajo el mismo límite de operación; una discrepancia o falta de cobertura debe invalidarlo y ejecutar el escaneo físico de seguridad. Hasta entonces un `SELECT` sin filas NO equivale a probar que no hay duplicados, así que no retirar los escaneos arbitrariamente.
3. **Agrupar verificaciones en la misma petición**: actualmente SELF/Calendar Day/preflight/created-entity recorren varias veces los mismos archivos. Un snapshot de metadata + versiones de las fuentes, revalidado justo antes de mutar y con invalidación postwrite, puede eliminar O(k×N) y aprovechar SQLite para seleccionar. El checkpoint E3 y el CAS de note siguen siendo los límites de mutación; no una caché permisiva.
4. **Instrumentar p50/p95 y RAM** a 20/250/1000/5000 con FastEmbed real en un host/entorno aislado antes de autorizar DEV; medir separadamente latencia GPT/n8n, materialización Core y refresh de índices. Perf sin IA a 1.000 notas debería aspirar a mucho menos de un segundo; es un objetivo a validar, no un rendimiento ya logrado.

**No se ha migrado Markdown a SQLite ni cambiado PROD/DEV**, y esta ronda no constituye el E2E real del navegador. Hay costes de red/GPT que se suman por separado (observaciones previas de ~9-17 s con GPT); esta mejora solo recorta I/O/validación local.

## Gates de esta ronda y estado de adopción

- **Gate transversal offline `CROSS_SURFACE_GATE PASS`: 763 Python PASS**, 64 archivos / 9 grupos, **168 Node PASS**. Incluye ahora `tests/core/test_vault_repository.py` en `performance_and_indexes` y el gate original de E2/E3/Tasks/UI. El acceptance ledger conserva **15 invariantes / 26 anclas** y P4 DEV no autorizada.
- **Suite global:** 3.667 Python PASS, 80 SKIP, los **mismos 10 fallos históricos** de presupuestos y hashes de benchmark, 52 subtests PASS; ninguna regresión nueva observada. Ruff y formato PASS; el hook de pytest global en commit se omite expresamente por esos 10 históricos, no se afirma CI verde.
- **Arquitectura/P4:** cambio acotado a `VaultRepository` y `WholeSourceLightExecutor`. No se ha desplegado, no se han migrado identidades ni introducido index SQLite autoritativo. El benchmark sintético y la memoria de la Raspberry no aprueban por sí mismos el circuito auténtico n8n/browser.
