# P4 — Búsqueda indexada, revisión prewrite y claims seguros (16 octubre 2026)

## Autoridad y entorno

La única fuente de estado operativo sigue siendo `docs/architecture/functional-roadmap.md`. Trabajo solo en rama `feat/light-router-poc-20261016`; DEV sigue instalado en `1474681`, PROD y datos personales intactos. Probar en fixtures temporales con SELF autenticado, modelos de OpenAI actuales y Markdown físico NO equivale a haber probado un navegador autenticado y un webhook n8n.

## 1. Eliminación de un límite funcional accidental (>5000 notas)

La búsqueda inicial de pistas de nombres en `odyssey_runtime/whole_source_light.py` ejecutaba `repository.list_markdown_paths()` y analizaba todo el Markdown, y además rechazaba cualquier vault con más de 5000 Notes. Se ha sustituido por `ContextIndex.source_name_hint_candidates`, que lee **solo metadatos derivados** del índice SQLite existente. Un match se vuelve a leer del Markdown vivo y se contrasta contra el SHA256, ID, tipo, nombre y estado deleted; un match stale o un índice incompatible falla cerrado. El límite restante de **24 coincidencias** es un presupuesto explícito de contexto, NO un máximo del vault y NO trunca silenciosamente una lista mayor. La ausencia de un match indexado NUNCA es prueba de ausencia de la persona: Core resuelve y preflighta las identidades contra la fuente física de conocimiento.

`tests/core/test_p4_indexed_name_hints.py` cubre duplicados de primer nombre, no matches, cambio externo del archivo, índice alterado y >5000 filas de índice derivado; no afirmar que esto pruebe un vault real de 5000 Notes + FastEmbed. La prueba de 5001 filas sintéticas mantiene un único match validado físicamente para aislar el antiguo umbral sin llenar de memoria/swap una Raspberry ya cargada.

Bench `scripts/p4_product_scale_isolated.py`, tras el cambio y aún con **ConstantEmbedder**, sin IA, 1 refresco incremental y 0 rebuild: aproximadamente 103 ms con 20 Notes, 1016 ms con 250 y 3999 ms con 1000. Antes de este cambio, con caché de parseo P4 pero hints escaneados, eran ~105/1043/4100 ms. El ahorro incremental es modesto; el problema estructural O(N) permanece en Core: la auditoría de cProfile rastrea escaneos físicos repetidos en `CalendarDayRepository`, identidades, target y referencia, sin permiso para eliminarlos ni cachear identidades como autoridad.

## 2. Una segunda interpretación genérica y estrictamente ANTES de escribir

Una auditoría fresca anterior del mensaje sintético «Hoy Bruno Prototipo ha conocido a Carla Prototipo» terminó 3/4: en la cuarta, Planner omitió uno de los participantes y el revisor detectó la pérdida. Esto es un fallo del Planner; **el rechazo Core fue correcto**. Para mejorar sin añadir patrones específicos, P4 admite **una sola** reinterpretación completa cuando el revisor independiente rechaza una propuesta que no contenía incertidumbres. Se conserva la fuente original y el mismo Core reviewer y todos los guards, speaker dual, E3, Writer y readback. Cualquier propuesta `unresolved`/`needs_clarification` detiene el proceso, igual que Task lifecycle vetado, una identidad colisionada o una negativa. No hay replanificación tras entrar en la sección de mutación. El segundo rechazo no da lugar a un tercer intento.

Pruebas offline adversariales en `tests/runtime/test_whole_source_light_product_p4.py`: segundo plan completo y verificado antes de tocar el vault, dos rechazos consecutivos sin efectos, incertidumbre sin override, Work Session propuesta erróneamente como Task CREATE sin reintento y E3 replay idempotente. Se agregó un test recursivo de **todos los JSON Schemas estrictos** en `tests/runtime/test_p4_model_contract_strict_schema.py` para impedir propiedades declaradas pero no requeridas, que fallarían en producción al usar `strict=True`.

Pruebas con GPT nuevo sobre cuatro vaults temporales para cada caso: **4/4** terceros participantes, **4/4** dos días, con hechos Markdown verificados; **3/3** negaciones y **3/3** condicionales bloqueados sin escritura. Importante: las ocho pruebas positivas referidas pasaron al primer intento, así que NO hay evidencia de que el repaso adicional mejore la tasa real futura; la compatibilidad se probó offline por inyección del primer rechazo. Continúa siendo incorrecto declarar estabilidad semántica plena.

## 3. Fallos previos a escritura, E3 y claridad del resultado

Anteriormente un error de disponibilidad del proveedor o un índice stale durante el preplan podía propagarse como HTTP 500 después de que E3 hubiera reservado el request_id, dejando un claim sin recibo aunque no se hubiera escrito conocimiento. Se ha limitado el catching a `WholeSourceLightError` producido por consultas/modelos de P4 **antes** de Core Writer/Tasks domain. Los errores Core o del dominio de Tasks después de una escritura siguen propagándose para dejar el claim irresuelto y prevenir reejecución. Un error de proveedor prewrite se expresa como `NEEDS_ATTENTION` con un código de diagnóstico seguro y se registra como resultado replayable. No se expone mensaje libre de excepción, contenido privado, IDs o nombres en el diagnóstico.

Tests nuevas: cambiar un Markdown coincidente sin refrescar índices, fallo del SDK después de Router pero antes de Planner, y error inyectado en refresh posterior al Writer real. En los dos primeros: cero escrituras y recibo E3 recuperable por mismo request_id; en el tercero: efecto físico real, resultado NO confirmado, claim bloqueado y ningún segundo WRITE. Esta mejora **no** implementa reconciliación automática de claims inciertos; requiere manifest duradero con pruebas físicas previas y posteriores y permanece bloqueada.

## 4. Lo que P4 TODAVÍA no permite anunciar

- Work Sessions / Task UPDATE mezcladas con hechos Core en el mismo mensaje, dependencias entre ambas apps y completa equivalencia NLP del chat con subtareas y UI.
- Recuperación automática de un claim E3 sin resultado tras crash con posibles escritos físicos.
- Rendimiento con embeddings **reales** de FastEmbed y gran vault; el banco sintético sigue ~4 s con 1000 Notes, fuera de presupuesto deseable.
- Auténtico navegador autenticado→n8n→runtime P4→GPT→Markdown→índices→n8n→UI con pantalla, donut, graph y persistencia entre navegaciones. En la Raspberry se ha verificado presión de memoria (~1,5 GB swap ocupado); arrancar otra pareja n8n/Chromium en esa máquina pondría en riesgo los servicios existentes. No se ha modificado Docker DEV ni PROD.

No elevar este informe a autorización de DEV. Cada test cubierto se incorporó al gate transversal `scripts/odyssey_cross_surface_gate.py`, al registro de invariantes `docs/architecture/odyssey-acceptance-contracts.json` donde corresponde y se archivó evidencia de modelo solo en `/tmp` de la Pi. La siguiente entrega debe buscar la causa O(N) de Core sin perder frescura, completar el contrato E2/Task mixed y disponer de un navegador+n8n aislados de verdad (preferiblemente fuera de la Pi cargada). E5 Events y E6 Clean Architecture seguirán después/incrementalmente, no son el objetivo de P4.

## 5. Última batería estricta con proveedores NUEVOS

`scripts/p4_product_live_isolated.py` volvió a ejercitar la **nueva implementación productiva** de P4 mediante HTTP real de localhost, GPT nuevo, Core real y Markdown aislado, con verificación posterior independiente de hechos y replay byte-idéntico. Resultado final **10/10 escenarios aceptados**, 0 HTTP 500: siete mensajes positivos `completed` con el número exacto de hechos (incluidos Task CREATE, 2 fechas, pronombres cruzados, SELF implícito, preferencia), tres `needs_attention` conservadores correctamente sin escritura (negación, condicional, hecho sin fecha/owner). Los diez reenvíos con el mismo request_id conservaron íntegramente el vault. Registro privado de la Pi: `/tmp/odyssey-p4-final-fresh-live10.log`; salida `FINAL_LIVE10_EXIT=0` y JSON resumido `/tmp/odyssey-p4-product-live-actual.json`.

**No prometer 100 % permanente:** este experimento y las repeticiones 4/4 positivas anteriores son muestras pequeñas y con fuentes sintéticas. La duración de cada ejecución con GPT osciló aproximadamente entre 9 y 17 segundos. No se ha ensayado memoria larga conversacional ni 5000 Notes reales, subtask end-to-end con GPT→browser, sesiones mixtas o múltiples n8n actores.

## 6. Gate de regresiones y release gate explícito

`tests/runtime/test_whole_source_light_product_p4.py` ahora verifica asimismo que un error de índice/provider **ANTES** de escribir termina con recibo E3 seguro y mismo-ID replay; un fallo inducido **DESPUÉS** de escribir conserva claim incierto e impide toda segunda ejecución. Los esquemas JSON Strict de todos los reviewers están cubiertos por `tests/runtime/test_p4_model_contract_strict_schema.py`, y el ledger enlaza las pruebas de escala/hints indexados. Gate transversal local actualizado: **620 pruebas Python + 168 JavaScript PASS** en 56 archivos/9 grupos (sin credenciales proveedor). Suite global **3545 Python PASS, 80 SKIP, exactamente los mismos 10 fallos históricos de benchmarks y precios** (52 subtests PASS), sin nuevas regresiones; como siempre los diez fallos históricos de benchmarks/precios son independientes.

**La adopción P4 sigue BLOQUEADA para DEV:** se exigen el E2E real navegador autenticado→n8n→GPT→Markdown→índices→UI y el contrato general mixto Work Session/Task lifecycle con Core, además de reconciliación de crashes y mejora O(N). Se deja desactivada por defecto y no se tocan DEV instalado `1474681`, PROD ni datos reales del usuario.
