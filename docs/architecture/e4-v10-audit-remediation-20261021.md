# E4 v10 — remediación de auditoría v9 (21 de octubre de 2026)

## Estado de la auditoría independiente que originó esta reparación

Job `e4-v9-closure-audit-20261021` sobre commit congelado
`1421ec10366b439551c4323f3aa8fadfb4d5ff09`: Generality **FAIL**, Quality **FAIL**,
Testing **FAIL**, Performance **BLOCKED**. Los cuatro se ejecutaron realmente
con diff completo, source snapshot read-only, gates cross-surface/acceptance/Ruff PASS,
**890.675 tokens Codex CLI reportados** y excepción solamente de pacing local
y máximo temporal 768 KiB (no cuota del proveedor). Ningún auditor declaró PASS.

El bloqueo anterior de Testing por ausencia de trazas y donut 0 % ya no reapareció;
los informes y el E2E autenticado con GPT real eran inspeccionables, pero los auditores
detectaron tres problemas nuevos en código y oráculos. Performance sigue bloqueado
por muestra insuficiente y FastEmbed no disponible en caché aislada.

## Reparaciones sin duplicar la autoridad de escritura

- **Conjunto cerrado de referencias (Generality):** `ensure_complete_core_reference_set`,
  helper genérico de Core, acepta opcionalmente `closed_target_types`.
  Cuando Tasks tiene un conjunto de Personas E2 verificado, invoca
  `closed_target_types=("person",)`. Cualquier referencia adicional a Person
  fuera de ese conjunto, incluso con otro texto («Marta»), es rechazada
  **antes de Core Writer**. El comportamiento default del helper en otras
  Apps/Note types no cambia. Nueva regresión con Person extranjera.
- **Alias de Persona omitida (Generality):** la fase E2 ya no presupone
  que el nombre canónico aparezca literalmente en la fuente. Evalúa recibos
  Core usando `source_mention` exacto, y, como los enlaces de alias a veces
  son escritos físicamente SIN recibo E2 reutilizable, inspecciona los
  wikilinks reales de los hechos con `request_id` del grupo Core anterior
  exclusivamente; un wikilink a Note `person` veta una selección incompleta.
  No inspecciona indiscriminadamente links antiguos de una nota actualizada.
  Prueba física: `Mari` resuelve a `[[maria-garcia|María García]]`
  en Calendar Day y la operación «los dos» que omite a esta tercera Persona
  se bloquea antes de Tasks, incluso sin recibo E2 de la referencia alias.
- **Cláusula personal oculta en un modificador (Generality/Quality):** el
  guard de fuente finita rechaza modificadores con subcláusulas
  «donde/mientras/cuando/where/while/when/où/lorsque/quand», no infiere
  personas por regex. Nuevos negativos ES/EN/FR y conserva los legítimos
  «en el parque»/«hoy por la mañana».
- **Oráculo de Testing:** `scripts/odyssey_e4_plural_model_campaign.py`
  compara el **multiconjunto exacto de todas las Personas** con SELF+cohorte,
  IDs únicos, un enlace exacto por cada objetivo, ausencia de referencias
  a terceros, y el **Markdown byte a byte** antes/después de reproducir
  la misma entrega. Es importable sin arrancar GPT. Nuevos adversariales
  para Ana duplicada/Luis omitido, IDs repetidos, Marta extra, enlace perdido
  o duplicado y replay flag verdadero con contenido alterado.
- **Test vertical de composición auténtica (Testing):**
  `tests/runtime/test_p4_composition_plural_postwrite_loss.py` invoca
  `dependent_task_delegate` construido mediante
  `composition.build_runtime_from_environment()` con bóveda y Planner
  de prueba. Intercepta la relectura física después del Writer y elimina
  el wikilink a Ana. **No llama manualmente al guard**: exige `partial`
  desde `odyssey_runtime/composition.py`. Si se elimina la llamada de
  producción al guard, el test deja de pasar.

## Evidencia y criterios de cierre

Focal: **90 PASS** (Core set, source, alias físico, composición de producción,
oráculo). Gate transversal actualizado con tests adversariales obligatorios y
preflight: **1.549 Python PASS, 179 Node PASS, 7 subtests PASS**, Ruff PASS. La suite global histórica tiene
9 fallos benchmark preexistentes en Router/Temporal reproducidos sobre base;
no se transforma esa deuda en PASS.

La campaña GPT v9 anterior incluyó 3 casos de creación correctamente guardados
y 1 abstención segura; el E2E posterior en navegador+n8n con GPT real
terminó PASS en 91,05 s, traza y SHA-256 congelados bajo
`docs/architecture/e4-v9-gpt-browser-*`. Tras congelar v10 en `43e18fb`,
se ejecutó otro E2E GPT real+n8n+Chromium sobre la nueva versión:
**PASS, 110,45 s, 2 Personas/1 Task/1 Day, enlaces físicos, navegador y
replay E3 byte-idéntico**. Su traza completa y muestra host de 27 lecturas
se conservan con SHA-256 en `e4-v10-gpt-browser-receipt-20261021.json`.
Durante parte de la ejecución MemAvailable del host bajó a ~971 MiB,
SwapFree a ~222 MiB; estos valores NO equivalen a RSS aislado del producto.
La muestra v10 permanece en **1/20 browser**, 0/20 directas v10 y sin
distribuciones válidas p95. **E4 no tiene cuatro dictámenes PASS** y no está
autorizada para desplegar.

Performance: 3 directos positivos (47,092, 52,918, 58,473 s) y 1 E2E
v9 (91,05 s) no establecen p95 de 20 casos. Medidas de memoria total,
swap, temperatura y CPU de una carga completa GPT+n8n+navegador faltan.
FastEmbed **ya se ha medido** con modelo público en caché de prueba aislada,
tres recargas offline y reconstrucción de 250 notas sintéticas; no implica
haber medido un p95 de solicitudes reales. El primer ensayo sobre
`~/.cache/fastembed` quedó históricamente BLOCKED y fue superado por
el ensayo aislado descrito abajo.
Los SLA en el informe v9 son **umbrales provisionales de experimento**,
no una aceptación de usuario ni condiciones de prod.

## Cortafuegos contra auditorías repetidas sin posibilidad de aprobación

El gate `scripts/odyssey_e4_audit_preflight.py` es de lectura exclusivamente:
comprueba árbol Git congelado, recibo E2E de v10 con traza SHA-256 anclada al
código revisado, modelo FastEmbed offline + índice de 250 notas sintéticas,
**20 ejecuciones positivas independientes directas y 20 navegador+n8n+GPT**
según los objetivos provisionales, y telemetría de recursos del host con
carga completa. Si falta algún requisito informa `HOLD` (código de salida 2):
**no se despachan auditores Codex a ciegas**. No considera las muestras de
v9 evidencia nueva de v10 ni permite sustituir muestras GPT por fixtures.
Regresiones adversariales de E4, el oráculo de campaña y el propio gate de
preflight quedan incluidos en el gate transversal y verificados por sentinelas.
Esto previene repetir la misma auditoría Performance BLOCKED por carencias
previsibles, pero no puede garantizar que una futura revisión no encuentre
un defecto nuevo. La norma para E4 es ejecutar el preflight y solo lanzar
cuatro revisores cuando devuelva READY.

FastEmbed aislado real (Pi, caché pública separada, sin notas personales):
recarga offline de 3 procesos, mediana 1,427 s, consultas ~12–14 ms;
rebuild 250 notas: Context 7,756 s, Semantic 5,974 s,
RSS pico ~1.043 MiB y memoria disponible host tras prueba ~1.552 MiB.
El tiempo inicial de descarga (49,93 s) no cuenta como carga fría offline.
El warning de pooling de ONNX/FastEmbed queda registrado para revisar
compatibilidad de embeddings. Estas medidas **no prueban el p95 de producto**.
Véase `e4-v10-fastembed-isolated-pi-receipt-20261021.json`.

**Sin despliegue, merge, Builder ni cambios a DEV/PROD, Cloudflare, E5 o notas privadas.**
