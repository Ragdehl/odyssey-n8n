# Auditoría de índices, reconstrucción y carga local — 17-10-2026

## Alcance y garantías
Investigación **solo DEV**, sobre el branch híbrido; sin modificar PROD ni el vault canónico del usuario. La prueba de rendimiento consulta el vault DEV en modo lectura, con copias desechables de los tres SQLite en /tmp, un único proceso FastEmbed frío y dos IDs Day sintéticos. Los resultados no son extrapolables sin medir otros tamaños o tipos.

## Fallo reproducido con regresión RED→GREEN
- `odyssey_core/source_inventory.py::inventory_row` serializa el fingerprint físico de cada Markdown como JSON `ensure_ascii=False`.
- `odyssey_core/context.py::ContextIndex.refresh_notes` comparaba ese texto con `json.dumps(before_version)` (predeterminado `ensure_ascii=True`).
- **Ocho nombres de archivo acentuados de las 102 Notes DEV** coincidían en todos los campos físicos del fingerprint, pero su representación JSON difería. La actualización incremental clasificaba una nota AJENA sin cambios como drift, lanzaba `ContextIndexError`; `refresh_affected_indexes` la capturaba y ejecutaba `refresh_indexes()`, reconstruyendo contexto, semántica general y semántica Tasks. Eso puede explicar las mediciones antiguas de ~26,7/30,1 segundos por refresco; sin tracing interno de aquellos rebuilds no se atribuye cada milisegundo con certeza.
- Cambio mínimo: `json.dumps(before_version, ensure_ascii=False)`, alineado con el productor del inventory, conservando comprobación de inode/ctime/mtime/size y rechazo de drift físico verdadero.
- Nueva regresión `tests/core/test_context_incremental_unicode_versions.py` primero FALLÓ sin el cambio y después PASÓ: una nota `Lucía García.md` inmutable no fuerza fallback al modificar otra nota; solo 1 nota se embebe; un cambio físico no declarado en Lucía continúa siendo rechazado.

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
