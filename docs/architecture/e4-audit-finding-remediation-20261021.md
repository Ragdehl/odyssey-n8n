# E4 — Remediación tras revisión de cuatro auditores (21-10-2026)

**Rama aislada, NO DEV/PROD.** El ciclo `e4-plural-audit-v2-20261021` sobre `4a096b6` ejecutó Generality FAIL, Quality FAIL, Testing BLOCKED y Performance BLOCKED. Todos los gates deterministas previos pasaron. Se corrigieron los hallazgos de código antes de solicitar nueva aprobación; el resultado anterior sigue históricamente válido (NO aprobado).

## Barreras modificadas

1. `dependent_group_graph.verify_dependent_group_graph`: toda referencia con **cardinal explícito cerrado** exige exactamente ese número de aristas distintas a la misma cita; no se acepta una arista para «los dos». Se verifica **antes** de cualquier escritura Core. Si las aristas comparten antecedente, se aplica también un veto de cobertura de menciones explícitas en el texto fuente. Es genérico de referencias y consumidores, no de Tasks/Note IDs.
2. `source_cohort_coverage.require_explicit_cohort_coverage`: comprobación **unidireccional de omisiones** (no NER ni autoridad para añadir vínculos): citas fuente únicas, no solapadas; un nombre explícito capitalizado a mitad de oración que no está cubierto por las citas seleccionadas provoca abstención. Los nombres comunes minúsculos, nombres al inicio de oración, nombres ambiguos y morfologías no cubiertas siguen requiriendo revisión semántica y prueba Core; este guard por sí solo NO garantiza comprensión universal. Por diseño puede rechazar conservadoramente referencias propias a lugares o entidades cercanas; hay que evaluarlo con lenguaje variado antes de considerar la feature madura.
3. `dependent_group_evidence._require_complete_person_cohort`: la comprobación física de recibos Core se exige también cuando se propone **una** arista de Person a un cardinal plural; conjuntos mixtos y recibos incompletos se rechazan.
4. `request_planning._render_domain_interpretation_section`: guía de conjunto compartido SOLO si la fuente, cardinalidad y valores distintos acreditan un conjunto finito único. Nunca fusiona acciones independientes ni menciona Tasks como semántica universal. Core sigue decidiendo acciones, identidades y Writer.
5. El camino opt-in de plural verificado anticipa la comprobación fuente antes de construir el DAG y escribir. El validador Tasks aplica el mismo veto antes de preparar la mutación.

## Regresiones ejecutadas

- Pruebas focales E2/E3/Graph/Tasks/Work Session: **121 PASS** con variantes de una arista, selección incompleta de tres nombres y dos revisores que coinciden equivocadamente.
- Gate transversal completo: **1480 Python PASS, 7 subtests PASS y 179 Node PASS**; Ruff PASS. Pruebas históricas de benchmarks de suite completa con nueve fallos preexistentes, tal como documentado en el commit anterior; no se declaran aprobadas.
- **E2E real tras correcciones PASS (69,71 s)**: Chrome/Chromium autenticado con negativa 403, Docker n8n aislado, GPT real, Core/Writer, **2 personas + 1 Task + 1 Day**, dos vínculos físicos verificados, Task `target_date=2026-10-21` para reloj sintético `2026-10-20`, 4 recibos SVG y UI tras recarga, E3 replay inmutable. Ver [recibo JSON con huellas SHA256 de fuentes exactas](e4-audit-fix-e2e-receipt-20261021.json). Las primeras dos pruebas eran falsos negativos por **reloj del ejecutor sin congelar**: se observó `2026-10-22` (fecha real del día siguiente) mientras el test esperaba `2026-10-21`. El fixture ahora fija explícitamente ambos relojes; no se alteró resolución temporal de producción. Esta sola ejecución no garantiza estabilidad GPT ni p95 de sistema.

## Coste de auditores (tokens reportados, solo proxy local)

| Auditor | Ciclo de comparación `e4-review-only-retry-20261020` | Ciclo `e4-plural-audit-v2-20261021` |
|---|---:|---:|
| Generality | 106424 | 270919 |
| Quality | 104311 | 136237 |
| Testing | 95254 | 139394 |
| Performance | 84882 | 117006 |
| Total | 390871 | 663556 |

**Resultado: +69,8 %**, sin Builder en ninguno de esos dos ciclos. El diff fundamental provoca packet completo para cada revisor; optimizar solo con medidas de enfoque verificables y conservando los cuatro dictámenes independientes de contrato Core/E3. El presupuesto local registrado NO es el saldo real de ChatGPT.

## Deudas pendientes

- Nueva auditoría independiente del commit corregido, con las dos barreras de cardinalidad y fuente verificadas.
- E2E reejecutable asociado a commit y consultas UI explícitas, y medidas de latencia/CPU/RAM/p95 bajo carga representativa; un resultado aislado no representa percentiles.
- No desplegar, no dar E4 por aceptada ni integrar E5 sin aceptación formal.
