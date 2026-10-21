# E4 — Tercera auditoría y reparación de identidad/tiempo/UI (21-10-2026)

**Rama E4 independiente, NO desplegada.** Auditoría `e4-corrected-audit-v3-20261021` del commit `160733d`, base E3 `2055148`, ejecutada por el supervisor tooling `29af06b` (aprobado 4/4 en `review-eff-tooling-v3-20261021`). Gates host PASS. **Generality FAIL, Quality FAIL, Testing FAIL; Performance NO LANZADO:** cap diario local agotado tras tres sesiones; quedó `paused_daily_budget`. Es una auditoría fallida, no permiso de despliegue ni aprobación parcial transferible a esta reparación.

## Hallazgos y reparación

1. **Generalidad y Calidad:** `source_cohort_coverage` omitía nombres en minúsculas y en el inicio de oración. Dos revisores coincidentes y dos recibos Core físicos podían ser incompletos respecto de tres nombres explícitos. Añadido veto **sintáctico de enumeraciones ancladas a las citas exactas**: detecta participantes descubiertos antes, entre y después de las citas, con coordinaciones y comas ES/FR/EN independientemente de la capitalización. No inventa nombres, roles ni IDs ni relaja ninguna evidencia Core/E2/E3. En caso de ambigüedad sintáctica, falla cerrado. Regresiones directas y grafo con dos revisores aprobando erróneamente nombres minúsculos o iniciales.
2. **Calidad:** en `composition.execute_tasks`, la rama plural no pasaba a Core el **instante original** capturado por Temporal (la singular sí). Ahora lo hace para `person_proofs`, preservando el reloj del único delivery en el Planner/Writer incluso si el reloj del host ha cruzado medianoche.
3. **Testing:** el navegador solo exigía una lista Notes no vacía; podía aprobar sin buscar Task o leer backlinks. El E2E ahora realiza búsqueda **real** por nombre de Task en la UI, abre cada Person por búsqueda y exige el backlink a esa Task desde cada ficha. Se emplea un solo evento `input` por búsqueda para no confundir al índice con consultas intermedias al teclear muy deprisa. Conserva el 403 de auth, gráfico/recibos, recarga y replay E3, todo sobre bóveda sintética.

## Evidencia reproducible

- Prueba de navegador Chromium + n8n real con modelo **grabado**: PASS, 42,79 s; 1 Person + 1 Task, Task visible en búsqueda, 1 backlink UI, E3 sin cambio de bytes.
- Prueba de navegador Chromium + n8n real + **GPT real**: PASS, 77,20 s; 2 Person + 1 Task + 1 Day, Task visible en búsqueda, 2 backlinks reales, enlaces y 4 recibos Markdown/graph, replay byte-idéntico, 0 mutaciones de DEV/PROD. El instante sintético del usuario fue `2026-10-20T10:30+02:00` pero `composition._current_time` se forzó a `2026-10-21T00:00:02+02:00` después de recibirlo: la Task mantiene `target_date=2026-10-21`, NO el 22. Es una prueba de cruce de medianoche del fixture y no una modificación del reloj de producción.
- Regressiones focales sobre `source_cohort_coverage`/grafo, `dependent_group_graph` y plural verified scope: **85 PASS**.
- [Recibo machine-readable de E2E y hashes SHA256](e4-v4-after-audit-e2e-20261021.json), ligado al código fuente exacto del test. Gate final: **1493 Python + 179 Node + 7 subtests PASS**, Ruff PASS. El SHA se registra en Git.

## Presupuesto y estado

Supervisión anterior al arreglo: Generality **97.784**, Quality **158.537**, Testing **101.435**, total **357.756 tokens reportados**; comparador anterior para esos tres roles **546.550**, variación de aproximadamente **-34,5 %**, no estimación de costes globales ni estabilidad estadística. Antes de la auditoría E4 se ejecutaron dos auditorías de tooling (231.119 y 223.062); este trabajo combinado saturó el límite diario local de 1.428.571. No se alteró la cuota ni se reinició una cuarta revisión sobre código ya fallido.

**PENDIENTES:** commit de reparación y gate actualizado, nueva auditoría independiente 4/4 de ese commit tras recuperación del presupuesto local; Performance sin aprobación en E4; medir latencia/cold-warm p95/recursos con muestra representativa y ejecutar aceptación en DEV autenticado antes de desplegar. El control sintáctico reconoce enumeraciones acotadas y puede abstenerse en prosa más compleja; no es comprensión universal de nombres ni una prueba de ausencia absoluta de omisiones. Los nueve fallos congelados preexistentes de benchmarks del full pytest siguen siendo deuda, no se declaran verdes.
