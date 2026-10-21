# E4 — cuatro auditores independientes tras excepción presupuestaria, y remediación posterior (2026-10-21)

## Auditoría congelada

El trabajo `e4-plural-v4-four-audit-20261021` (commit de E4 `0ea6ece`, base E3 `2055148`) usó el supervisor optimizado, cuatro procesos Codex distintos, gates host PASS, exclusivamente worktree limpio/read-only. Los cuatro auditores **terminaron** (la excepción local de gasto ya no bloqueó):

- **Generality FAIL:** enumeración finita incompleta cuando otra Person minúscula aparece en una cláusula posterior; Core podía introducir un `assignee` no autorizado por la interpretación Task.
- **Quality FAIL:** faltaba una regresión vertical determinista con dos personas y una Task, Core Markdown, comprobación física y replay.
- **Testing PASS:** recorrido sintético con GPT real+Chromium+n8n y backlinks UI confirmado; esto no es fiabilidad lingüística ni DEV/PROD.
- **Performance BLOCKED:** falta una distribución suficiente de latencia/coste/CPU/memoria en Pi con modelos y embeddings de contexto real, y un presupuesto de aceptación explícito. El p95 de consultas de 250 notas no debe confundirse con el p95 E2E.

El ciclo `v4` registró **405.364 tokens CLI**, no fue aprobado. La excepción temporal del 21-10-2026 afecta solo al cálculo local de presupuesto, no a las salvaguardas de los auditores, cuotas reales de Codex o E3.

## Correcciones posteriores, en rama fuente aislada

1. `odyssey_core/source_cohort_coverage.py`: se rechaza con abstención una fuente cuya lista citada de miembros termina antes de otra cláusula (p. ej., `ana y luis; después conocí a marta`). Idéntico criterio conservador para otra oración previa. La prueba semántica no inventa personas/IDs y NO declara exhaustividad universal; rechazará alguna frase contextual válida hasta que exista evidencia semántica más específica.
2. `odyssey_apps/tasks/planning.py`: autoriza `assignee` y `parent_task` en el plan solo si existe mención tipada de esa relación en `TaskInterpretation`, con texto exacto y helper de tipo apropiado. Rechaza responsables y padres inventados por Core; conserva la delegación de identidad/escritura en Core.
3. `tests/runtime/test_p4_plural_person_full_vertical.py`: provider offline reproducible, **Writer/Core y Markdown reales** sobre vault sintético, crea exactamente 2 personas + 1 Task y enlaces físicos, respeta `target_date`, guarda replay E3 byte-idéntico, cubre rechazo posterior a Core y un `assignee` no solicitado. Registrado en el gate transversal. No sustituye E2E autenticado GPT/Chromium.

## Estado y condiciones antes de aprobación

Las pruebas focales de cobertura sintáctica (76 PASS), roles Tasks (29 PASS) y vertical 3 PASS están verificadas; el gate transversal final **1503 Python + 179 Node + 7 subtests PASS**, Ruff PASS, registrados en `/tmp/e4-v5-frozen-cross-surface-20261021.json`. **NO aprobado ni desplegado**: el commit de remediación posterior necesita congelarse y auditarse de nuevo; Performance precisa presupuesto de latencia del producto y mediciones representativas. Los nueve fallos históricos preexistentes de benchmark en el full suite siguen pendientes y no se consideran verdes. E5 sigue en rama separada.

**Comprobación con GPT real tras corregir el código:** PASS en Raspberry, 85,69 s con Chromium autenticado localmente, n8n aislado, 2 Person + 1 Task, dos backlinks consultados en la UI, fecha del delivery original y replay E3 inmutable. [Recibo con hashes y resultado del navegador](e4-v5-live-verified-20261021.json). Es observación única y no cumple el p95 reclamado por Performance.
