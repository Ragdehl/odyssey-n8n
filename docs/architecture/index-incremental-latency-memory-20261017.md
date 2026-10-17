# Auditoría de índices, reconstrucción y carga local — 17-10-2026

## Alcance y garantías
Investigación **solo DEV**, sobre el branch híbrido; sin modificar PROD ni el vault canónico del usuario. La prueba de rendimiento consulta el vault DEV en modo lectura, con copias desechables de los tres SQLite en /tmp, un único proceso FastEmbed frío y dos IDs Day sintéticos. Los resultados no son extrapolables sin medir otros tamaños o tipos.

## Fallo reproducido con regresión RED→GREEN
- `odyssey_core/source_inventory.py::inventory_row` serializa el fingerprint físico de cada Markdown como JSON `ensure_ascii=False`.
- `odyssey_core/context.py::ContextIndex.refresh_notes` comparaba ese texto con `json.dumps(before_version)` (predeterminado `ensure_ascii=True`).
- **Ocho nombres de archivo acentuados de las 102 Notes DEV** coincidían en todos los campos físicos del fingerprint, pero su representación JSON difería. La actualización incremental clasificaba una nota AJENA sin cambios como drift, lanzaba `ContextIndexError`; `refresh_affected_indexes` la capturaba y ejecutaba `refresh_indexes()`, reconstruyendo contexto, semántica general y semántica Tasks. Eso puede explicar las mediciones antiguas de ~26,7/30,1 segundos por refresco; sin tracing interno de aquellos rebuilds no se atribuye cada milisegundo con certeza.
- Dos comparaciones homólogas corregidas con `ensure_ascii=False`: refresco ordinario `refresh_notes` y `reconcile_external_changes` (usada para cambios externos/sincronización). Se conserva comprobación de inode/ctime/mtime/size y rechazo de drift físico verdadero.
- Nueva regresión `tests/core/test_context_incremental_unicode_versions.py` primero FALLÓ sin el cambio y después PASÓ: una nota `Lucía García.md` inmutable no fuerza fallback al modificar otra nota; solo 1 nota se embebe; un cambio físico no declarado en Lucía continúa siendo rechazado. Segunda regresión: reconciliación externa devuelve 0 con nombres Unicode intactos, detecta exactamente 1 cambio real en otra nota y vuelve a 0 después.

## Medición en Raspberry arm64, 102 Notes
- Modelo FastEmbed local de ~241 MiB en disco; instancia fría ~2,44–2,92 segundos, **RSS pico del proceso Python ~651–660 MiB**. No es coste incremental por cada nota si el proceso ya está vivo.
- Antes de corregir, usando SQLite copiados de DEV, el refresco incremental abortó en `context` a los ~0,01 s, por falso drift, y la composición productiva invocaría el fallback global. No se ejecutó fallback destructivo ni se alteró DEV.
- Después de corregir, mismos SQLite copiados y mismo vault DEV de solo lectura: contexto 0,214 s (2 embeddings, 3434 caracteres, inferencia 0,173 s), semantic 0,026 s (0 embeddings), semantic-tasks 0,026 s (0 embeddings); **0,267 s total**. Repetición con IDs idénticos: 0,278 s; reprocesa esos 2 embeddings pese a no haber cambios (optimización futura menor).
- No hay prueba de latencia, memoria ni consumo energético en móvil; el modelo local es demasiado grande para suponerlo gratis en un proceso de UI.

## ¿Es la indexación estrictamente incremental?
No. Los vectores seleccionados sí; `ContextIndex.refresh_notes` hace listado y stat de todos los ficheros, reconstruye la topología global de wikilinks desde proyecciones persistidas y valida inventario externo. Los índices semánticos general y Tasks ejecutan un recorrido completo de Markdown y validan cada nota incluso cuando seleccionan **cero** vectores para embebido. Por diseño, si falla una comprobación de drift/schema/concordancia, el coordinador puede reconstruir los **tres** índices completos. El hilo asíncrono coalesce IDs, pero una futura lectura necesita barrera de frescura; no reduce CPU si hay fallback. La cola del hilo es volátil: garantizar recuperación de refresh pendiente tras reinicios precisa verificación de startup, no asumir durabilidad.

## Próximos trabajos, orden recomendado
1. **P0:** medir actualización E2E DEV tras desplegar este fix; validar ausencia de fallback/CPU elevada y barrera al leer inmediatamente después.
2. **P1:** instrumentar decisión incremental vs fallback, causa, cantidad de notas releídas, inferencias y pico de memoria de forma acotada y privada (sin contenido); evitar rebuild global silencioso en ruta ordinaria y garantizar recuperación segura.
3. **P1 móvil:** separar almacenamiento canónico y proyecciones deterministas ligeras (id, alias, propiedad, enlace, backlink) de vectorización opcional y perezosa. Nunca inicializar FastEmbed ni revectorizar para guardar una nota de dos líneas. El modelo de ~241 MiB no cabe en un presupuesto liviano de UI por defecto.
4. **P2:** reutilizar snapshot/inventario validado entre índices y evitar parsear 2 veces todas las Notes semánticas, sin debilitar detección de cambios externos. No cachear autoridad entre entregas sin comprobación de versión.
5. **P2:** estudiar con pruebas de concurrencia paralelizar revisión de cobertura y dos speaker reviews tras Planner (si sus prerequisitos son independientes), manteniendo barreras antes de Writer y costes de casos rechazados; perfilar por separado n8n y transporte (~6 s no desglosados en la última muestra).

Referencias: `docs/architecture/p4-dev-latency-graph-20261017.md`, `docs/architecture/functional-roadmap.md`. PROD intocado.

## Validación E2E real y estado desplegado
- Primera corrección commit 66312f4 desplegada en DEV mediante scripts/odyssey-dev deploy (código de script 0; marker en disco 66312f4). Segunda corrección de la reconciliación externa: commit 1ced0a2 probado en rama, NO desplegado.
- E2E real nuevo p4dev20261017-unicodeindex04 a través de n8n + GPT + Writer/Markdown: COMPLETED, 19,8 s cliente / 17,989 s runtime, 2 recibos Core físicos, index_barrier 0 ms, index_refresh.schedule ~0 ms. El contexto SQLite DEV cambió a las 22:58:22. PROD /healthz HTTP 200, intacto.
- Modelo en esa petición: Router 2,990 s; Planner 3,394 s; revisión cobertura 2,834 s; dos speaker reviewers 1,953/2,381 s en paralelo; source_processing 12,319 s. Hay otros ~5,7 s de runtime fuera de source_processing y ~1,8 s de diferencial cliente/runtime; no atribuirlos sin instrumentación a n8n.
- RSS proceso runtime DEV observado posteriormente ~757 MB; swap global host ~933 MB en uso. No deducir consumo móvil ni fuga de memoria a partir de una muestra.
- Gate completo después de los dos cambios: 964 Python y 171 JavaScript PASS; 11 regresiones focales PASS.
- Pendiente: segundo deploy de reconciliación externa, observabilidad de motivo y duración de fallback, móvil nativo, corte abrupto del índice y pruebas a 1000/5000 Notes.

## Bloque siguiente — escalabilidad y observabilidad (17-10-2026)

### Medición de 100/1000/5000 Notes sintéticas en Raspberry
Script reproducible y versionado: `PYTHONPATH=. python benchmarks/indexing/probe_incremental_scale.py`; salida de control `/tmp/odyssey-index-scaling-tracked.log` (repetición 5000 Notes: context 0,643s, semantic 0,936s, semantic.Tasks 0,948s, 2,527s total). Se crean SOLO Markdown e índices temporales bajo `/tmp` con un embedder determinista sin modelo neural, para aislar filesystem, parseo y proyección SQLite. NO mide inferencia local real en 5000 notas ni hardware móvil.

| Notes | build 3 índices inicial | refresh context 1 Note | refresh semantic 1 Note | refresh semantic.Tasks 1 Note | total incremental |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 | 0,092 s | 0,015 s | 0,019 s | 0,019 s | 0,053 s |
| 1000 | 0,861 s | 0,127 s | 0,185 s | 0,184 s | 0,496 s |
| 5000 | 4,286 s | 0,640 s | 0,939 s | 0,921 s | 2,500 s |

Contadores I/O al cambiar UNA Note, con 5000 existentes: context **una lectura Markdown y 5001 comprobaciones file_version**; semantic **5000 lecturas Markdown**; semantic.Tasks **5000 lecturas Markdown**. Se confirma O(N) del refresco de proyecciones que no necesitan embeddings nuevos. Memoria pico benchmark sintético sin modelo: 73,5 MB RSS. El código aún procesa de nuevo la nota afectada si se repite refresh, incluso sin modificaciones: otra oportunidad menor de optimización.

### Instrumentación DEV (solo rama hasta deploy)
`odyssey_runtime/composition.py` emite a stderr un solo evento privado `odyssey_dev_index_refresh` al terminar el refresco. Los campos son `outcome` (incremental, full_rebuild, failed), `note_count`, `duration_ms`, `stages_ms` (context, semantic, semantic.tasks y full_rebuild cuando corresponda), `failure_stage` y `failure_class` si hay fallo. No contiene paths, IDs, texto, alias ni contenido de errores. Fuera de `ODYSSEY_DEPLOYMENT_ENV=DEV` + `ODYSSEY_LIGHT_SOURCE_V1=1`, no emite nada. No relaja ninguna comprobación: sigue reconstruyendo si detecta drift no declarado y falla cerrado si falla el fallback. Prueba física con índices reales sintéticos valida un incremental sin fallback y un full_rebuild a causa de una nota externa. La modificación de la reconciliación Unicode `1ced0a2` se incorpora en el mismo deploy pendiente.

### Límite de optimización
No eliminar el doble barrido semántico a ciegas: actualmente es defensa ante modificaciones externas y contratos incompatibles. Dirección P1: materializar un inventario/Snapshot de metadata, source_hash y versiones físicas verificado por context y reutilizarlo entre índices en UNA transacción lógica; cada índice debe preservar validación de origen, type y drift y una comprobación final anti-carrera antes de publicación. Nunca reutilizar contexto obsoleto para autorizar identidad, backlinks o inferencia.

### Resultado del primer deploy y reparación de observabilidad
- Instrumentación base desplegada DEV `c0cdcba` (script `odyssey-dev deploy` RC=0; check físico); E2E live nuevo `p4dev20261017-indextrace05`: COMPLETED, **22,1s cliente / 21,025s runtime**, 2 Core writes en una ruta, barrera inicial 0 ms, `index_refresh.schedule` no bloqueante. DEV/PROD HTTP 200.
- **No se ha podido confirmar aún la modalidad incremental desde este E2E**: `journalctl --user -u odyssey-dev-runtime.service` devuelve `No journal files were found` en la Raspberry, aunque el servicio tiene `StandardOutput=journal` y stderr heredado. Las pruebas aisladas sí demostraron eventos correctos; no atribuir observación en producción al log inexistente.
- Corrección siguiente (en rama): además de stderr, escribir los mismos registros *sin contenido privado* en `ODYSSEY_RUNTIME_ROOT/index-refresh-events.jsonl`, con permisos 0600, límite ~256 KiB y truncado al superar el límite; el log jamás se almacena en /data/odyssey PROD y no se escribe fuera de DEV+full source. Un fallo de disco o registro no interrumpe la mutación ni cambia el estado del índice. Tests de archivo, modo privado, rotación y silencio en PROD; nuevos E2E/log real y deploy pendientes.

### Cierre del último deploy: comprobación real de modo incremental
- `985aa0d` desplegado con `scripts/odyssey-dev deploy` RC=0; marcador físico `985aa0d92a8674bf82ffd7b51d250762cb701976`.
- Nuevo E2E por n8n/IA/Core Writer con `p4dev20261017-indexpersist06`: **COMPLETED**, cliente 26,9 s, runtime 23,860 s; UNA ruta Core y DOS recibos físicos en Markdown, `index_barrier=0 ms`, `index_refresh.schedule=0 ms`. No significa que la indexación haya terminado antes de responder.
- Archivo PRIVADO local `/data/odyssey-dev/runtime/index-refresh-events.jsonl`: **0600**, evento observado: `outcome=incremental`, `note_count=4`, `duration_ms=3229,1`; fases `context=2461,4 ms`, `semantic=42,9 ms`, `semantic.tasks=536,9 ms`. **NO full_rebuild** en esta muestra. DEV y PROD `/healthz` HTTP 200; PROD no modificado.
- La medida de 3,23s REAL no contradice el benchmark de 0,267s anterior: batch 4 frente a 2, proyecciones diferentes y modelo neural real. Ambos muestran que el mecanismo es incremental en vectores, no O(1) en I/O y todavía carga CPU/RAM.
- No afirmar que el ahorro de CPU sea universal: repetir con personas, tareas, cambios externos, pérdida de energía y bibliotecas grandes con modelo real; medir RSS durante background. La opción móvil debe eliminar la dependencia de FastEmbed de la escritura y de su hilo obligado, con indexación semántica perezosa fuera de UI y reconciliación persistente.
