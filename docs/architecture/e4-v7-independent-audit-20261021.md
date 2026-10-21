# E4 — auditoría independiente v7, 21-10-2026

Código revisado: `90d89942b5069a2dd3c7b745e7b8be7d3c75743f` (base E3 `2055148f6ca97dd7575a1d6bfd966eba20a6628e`). Job `e4-v7-full-audit-20261021`: **Generality FAIL, Quality FAIL, Testing BLOCKED, Performance BLOCKED**. Fase `blocked_repair_budget`, `ready_for_user=false`, `deployment=forbidden`, sin Builder. Cuatro revisiones reales con permisos de solo lectura. Codex CLI reportó **649.259 tokens**: Generality 177.796, Quality 186.284, Testing 142.569, Performance 142.610. No equivale a la cuota real de ChatGPT.

Los gates del supervisor sobre el worktree inmóvil: **1.516 Python PASS, 179 Node PASS, 7 subtests PASS, ledger y Ruff PASS**. Los nueve benchmarks históricos que ya fallan en baseline no fueron marcados PASS.

## Defectos de Generality y Quality

- **Generality 1:** `dependent_group_graph.py` y `dependent_group_evidence.py` exigen que todos los Core anteriores formen parte de la cohorte, incluso un hecho independiente como «Terminé el informe» antes de «Conocí a Ana y Luis. Mañana llamar a los dos». Reparar sin perder la detección de un tercer referente omitido.
- **Generality 2:** `source_cohort_coverage.py` rechaza modificaciones no-personales tras el último nombre («en el parque», «hoy por la mañana»). Admitir modificadores fuente fiables, manteniendo el veto a un nombre extra o una nueva cláusula.
- **Quality:** `composition.py` puede devolver `completed` para Task pluripersonal sin releer obligatoriamente que el Markdown persistido conserva ambos enlaces. Añadir readback físico estricto y test de borrado de un enlace tras el guardado; degradar a `partial` si falta.

## Bloqueos de evidencia

- **Testing:** las pruebas reales Chromium → n8n → GPT → Core → Markdown → UI/replay están registradas, pero el revisor no podía leer `/tmp/e4_safe_trace_postfix.log` desde el worktree auditado. Proveer recibo depurado y verificable ligado al SHA. El donut se observó a 0 %, sin demostrar actualización del porcentaje.
- **Performance:** faltan presupuesto operativo acordado y distribución representativa p50/p95 del flujo E4, con GPT, CPU, RAM, swap e indexación. Las 12 pruebas de búsquedas con 250 notas y E2E aislados no bastan. FastEmbed cold/warm no se midió al faltar modelo en caché aislada.

## Activación y trazabilidad

Primer job `e4-v7-audit-20261021`: gates PASS, luego se bloqueó antes de GPT por tamaño del diff (441.575 bytes frente a límite 256 KiB). Un segundo job sobre **el mismo SHA** incluyó el diff completo usando un límite temporal en memoria de 512 KiB. Por autorización expresa del usuario se permitió solo para el proceso/job del 21-10 exceder el pacing diario LOCAL de Codex sin modificar contabilidad, permisos, snapshots, lock, política persistida ni cuota del proveedor. Excepción anotada en `.odyssey-agent-runs/e4-v7-full-audit-20261021.operator-exception-20261021.json`. El intento automático del día siguiente se desactivó. No hubo cambios de código, merge, deploy, DEV/PROD ni acceso a notas privadas.

Para cerrar E4: corregir los tres bloqueos de código, dar recibo E2E inspeccionable y métricas/criterios de Performance, ejecutar gates y **nueva auditoría** del SHA corregido; nunca reetiquetar dictámenes anteriores como PASS.
