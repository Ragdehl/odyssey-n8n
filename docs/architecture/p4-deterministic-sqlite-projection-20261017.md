# P4 — Proyección determinista completa en SQLite (17-10-2026)

**Estado:** implementada en rama P4, no desplegada ni autorizada para DEV/PROD. El vault Markdown sigue siendo canónico; SQLite es un índice derivado y reconstruible. Este cambio no introduce otro escritor ni divide físicamente los facts.

## Inventario real antes del cambio

Ya existían `ContextIndex` SQLite con tabla `notes` (id, path, type, name, tags, hash, embedding), `properties` **solo para campos filtrables del schema**, `note_projection` (aliases como JSON, texto indexable y cuerpo íntegro), y `note_links` (enlaces explícitos resueltos entre notas). Por tanto, había enlaces salientes y se podían derivar backlinks mediante `SELECT ... FROM note_links WHERE target_id=?`. `SemanticEntityIndex` dispone de otro índice de candidatos. El problema era que no estaban completas o normalizadas las proyecciones para **todas** las propiedades, alias exactos y facts individuales. Los nombres y tipos sí estaban indexados desde antes.

## Ampliación de `ContextIndex` (formato 5)

Se ha elevado `format_version` de 4 a 5 para exigir reconstrucción segura de índices antiguos antes de usarlos. `NotesQueryService` utiliza ahora la misma constante de compatibilidad que `ContextIndex`; cualquier lector incompatible falla cerrado, no interpreta parcialmente el formato nuevo. **La reconstrucción se hace desde Markdown**, no se modifica el vault. Las tablas existentes no cambian su contrato de consulta:

| Tabla | Qué contiene y para qué sirve |
|---|---|
| `notes` | ID, ruta, tipo, nombre, SHA, tags y vector (ya existía) |
| `properties` | Valores tipados para filtros soportados por el esquema (ya existía) |
| `note_projection` | Texto, aliases JSON y cuerpo Markdown proyectado (ya existía) |
| `note_links` | Enlaces explícitos **resueltos** de una nota a otra; índices para backlinks inversos |
| `note_attributes` **nueva** | **Todos** los campos del frontmatter canónico, incluidos aliases, tags, provenance, dates, revisions y cualquier futura propiedad de tipo, como cumpleaños o relación. Cada valor se conserva como JSON estructurado fiel al original |
| `note_aliases` **nueva** | Alias literal + representación NFC/casefold para búsqueda determinista por alias, con índice invertido |
| `note_facts` **nueva** | Fact individual por `(note_id, locator)`, `request_id`, ordinal, texto, instante de captura, coordenadas temporales y posiciones dentro de la nota |
| `note_fact_integrity` **nueva** | `valid` / `malformed`: distingue notas legadas con marcadores incompletos de hechos atómicos válidos; nunca inventa fact IDs |
| `note_fact_links` **nueva** | Menciones por fact, con destino resuelto o `NULL` cuando falta/no es único, y número de ocurrencias; puede consultarse en sentido inverso por `target_id` |
| `note_mentions` **nueva** | **Todos** los wikilinks literales salientes de una nota, incluidos los aún no resueltos; `note_links` conserva solo los resueltos, para evitar relaciones falsas |

Un backlink **no requiere otra fuente**: la consulta inversa sobre `note_links` / `note_fact_links` lo obtiene directamente. Los enlaces malformados o ambiguos no obtienen identidad inventada: permanecen como mención literal cuando son sintácticamente válidos. Los facts sin marcador válido siguen siendo cuerpo legible, nunca facts ficticios.

**SELF no es simplemente una propiedad inferida del grafo:** la relación entre un usuario autenticado y su nota personal se conserva en `SelfBindingRepository` dentro del estado durable. El contexto y los fact links sí permiten proyectar menciones **desde** esa nota y backlinks **hacia** ella, pero no convertir menciones en autorización para asignar SELF a otro usuario. No duplicamos secretos ni credenciales en SQLite.

## Escritura y mantenimiento

- `ContextIndex.rebuild` crea todos los índices a partir de notas validadas; el índice temporal reemplaza al anterior solo al completar correctamente la construcción.
- `ContextIndex.refresh_notes` actualiza atributos, aliases, facts e integridad únicamente para los IDs modificados; recrea el grafo ligero de links / menciones desde la proyección de cuerpo y fact existente para que **un nuevo target pueda resolver un backlink antiguo**, sin recalcular embeddings de notas sin cambios.
- `refresh_existing_note` mantiene el contrato metadata-only: conserva el cuerpo/facts/links, pero actualiza todos los atributos, alias y otras propiedades del metadata sin alterar identidad ni saltar CAS.
- Si aparece una incompatibilidad de formato, un drift de nota ajena, duplicación de ID o un fallo de la proyección, falla cerrado o solicita reconstrucción. No se usan índices stale para decidir CREATE/UPDATE o resolver identidad canónica.
- No se han agregado fechas de cumpleaños ni relaciones al schema de personas ahora. Una prueba con una **copia aislada del schema** añade esos campos y verifica que se indexan automáticamente en `note_attributes`, sin modificar el schema productivo actual.

## Pruebas y costes

`tests/core/test_context_deterministic_projection.py` valida atributos JSON completos, alias NFC, facts y sus locators, marcas temporales, links/backlinks entrantes y salientes, menciones sin target, basename ambiguo, nueva nota que resuelve mención antigua, edición/borrado y equivalencia `refresh_notes` vs `rebuild`, `refresh_existing_note` metadata-only, propiedades futuras, formato 4 incompatible y compatibilidad con marcadores de facts legados. Se incluye en el gate `scripts/odyssey_cross_surface_gate.py` junto a `test_context.py` y `test_note_queries.py`.

La proyección de enlaces solo incluye **wikilinks explícitos** del cuerpo. No interpreta menciones puramente lingüísticas como identidad, ni convierte automáticamente una propiedad textual en una relación entre IDs; para eso se necesita una definición tipada del schema y evidencia de resolución. La detección de colisiones de ruta al hacer NFC/casefold evita escoger arbitrariamente uno de dos archivos con nombres distintos solo en mayúsculas; el alias normalizado también comparte la regla Unicode y de espacios de Core.

El perfil P4 provider-free (vault sintético) mostró 20 notas **86,9 ms**, 250 notas **795,5 ms**, un refresh incremental y cero rebuilds durante WRITE. Antes de ampliar estas tablas se midieron aproximadamente 79 ms y 779 ms, respectivamente; **no es una optimización de latencia por sí misma**. El crecimiento del coste físico de Core sigue pendiente.

## Qué viene después (orden propuesto)

1. **Explotar estas tablas** mediante un puerto de consultas tipadas de Core para alias, ID/tipo, propiedades, facts por entidad/fecha y grafo outgoing/backlinks por fact. Las respuestas de SQLite son **candidatos derivados**, nunca autorización de escritura, y necesitan re-grounding de la evidencia decisiva en Markdown.
2. **Dar garantías de frescura al índice**: catálogo de rutas/versiones de archivos y cambios externos con reconciliación incremental. Un resultado SQL vacío solo será suficiente para un negativo cuando exista un comprobante de completitud/frescura. Si no, fallar cerrado o escanear la fuente completa. Evitar múltiples scans en Core Calendar/SELF/preflight.
3. **Medir rendimiento real** con índices de 250/1000/5000 notas, cambios fuera de banda y concurrencia. Conservar garantías E2/E3, Writer único y fail-closed; contrastar mejora de p95 y RAM en la Raspberry.
4. **Terminar P4 funcional** (subtareas Chat↔UI, grupos dependientes N:M, recuperación E3) y superar el E2E autenticado navegador→n8n→GPT→Core/Tasks→Markdown→graph/donut/historial sobre vault descartable antes de habilitar las pruebas del usuario en DEV.

La separación física de facts en documentos individuales NO está prevista: su identidad `(note_id, request_id, ordinal)` y su proyección SQL por fact dan búsqueda granular sin multiplicar Markdown ni modificar la decisión original.

## Resultado de las validaciones, cierre de la ronda

- **Gate transversal offline:** 782 tests Python PASS en 66 archivos y 9 grupos; **168 Node PASS**. `scripts/odyssey_acceptance_contracts.py`: 15 invariantes / 26 anclas correctas, **P4 DEV NO AUTORIZADA**.
- **Suite global:** 3.686 Python PASS, 80 SKIP, 52 subtests PASS y exactamente los **mismos 10 fallos históricos** de benchmark/precios; ninguna regresión nueva. Ruff/format y diff check PASS.
- **Coste en Pi, P4 sin IA:** 20 notas extra 86,9 ms, 250 notas extra 795,5 ms, 1 refresco incremental, cero rebuild durante escritura. No se han perfilado 1.000 notas en esta ronda, ni latencias reales de n8n/GPT; no se afirma mejora de latencia.
- **Seguridad:** caso de dos paths idénticos tras casefold no adjudica un target; alias normalizado respeta NFC/casefold y espacios del resolvedor de Core; falta aún el gate integral navegador/n8n.
