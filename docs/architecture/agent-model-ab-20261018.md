# Experimento A/B de reparación de código — Luna vs Sol (18-10-2026)

## Objetivo y control del experimento

Tras el piloto de 133623 tokens reportados por dos agentes Luna que NO terminó la feature, se preparó una tarea pequeña pero real: corregir la aceptación `tooling` vs `product` del supervisor. Su estado inicial se creó en un **commit idéntico** `f6627c1df7a3735da3e2ca1065b60e4a71e5cc65` de un worktree sintético. En ese estado, `tests/runtime/test_agent_cycle_supervisor.py` tenía **60 PASS y 4 FAIL** (tres fixtures sin `brief.md` y un bypass de scope documental). Se añadieron dos tests adversariales comunes antes de lanzar los modelos (docs/product/agent-team.md se debe rechazar; docs/architecture/agent-team-pilot-20261018.md se permite).

Se crearon worktrees `experiment/agent-ab-luna-20261018` y `experiment/agent-ab-sol-20261018` desde el **mismo SHA**. Ambos modelos recibieron el **mismo prompt literal** en `/tmp/odyssey-agent-ab-repair-prompt-20261018.txt`, con `codex-cli 0.162.1`, `--ignore-user-config`, `--ephemeral`, sandbox workspace-write, el **mismo razonamiento low** y 175 s máximos por proceso; ejecución secuencial en la Pi, sin tocar DEV/PROD. No compartieron correcciones entre sí.

## Resultado observado

| Medida (una sola muestra por modelo) | Luna 6 low | Sol 6 low |
| --- | ---: | ---: |
| Tiempo real de sesión | 43 s | **32 s** |
| Tokens reportados por CLI | 31336 | **20494** |
| Código de salida | 0 | 0 |
| Tests Python focales verificados independientemente | 64 PASS | 64 PASS |
| Ruff y `git diff --check` | PASS | PASS |
| 11 condiciones adversariales de scope | 11 PASS | 11 PASS |
| Archivos modificados | 2 | 2 |

Sol utilizó aproximadamente **34,6 % menos tokens reportados** y terminó en aproximadamente **25,6 % menos tiempo** que Luna, en este único experimento. No equivale a coste real, ni es una comparación estadística ni demuestra superioridad universal. Los dos repararon los cuatro fallos sin rebajar tests ni ampliar permisos y ninguno ejecutó despliegue.

Los datos re-ejecutados por un evaluador externo están en `/tmp/odyssey-agent-ab-scorecard-20261018.json`. Cada rama conserva sus diffs y logs `/tmp/odyssey-agent-ab-{luna,sol}-run.log`. El evaluador no depende del resumen del propio modelo.

## Integración y límites

Se escogió la versión Sol porque rindió igual en corrección de pruebas y restricciones con menor consumo/tiempo. La feature original fallida estaba basada en `0e7543a`, mientras la rama de trabajo ya incluía el fail-fast y reserva de tokens en `8be2c0f`. Se aplicaron los cambios en un **tercer worktree** `experiment/agent-ab-integration-20261018` sobre `8be2c0f`; el único conflicto era una adición simultánea de tests, resuelto **conservando las pruebas de ambas partes**. Verificaciones sobre el resultado combinado: **67 tests de supervisor PASS**, **1123 Python cross-surface PASS + siete subtests**, **174 JavaScript PASS**, Ruff PASS.

Nueva capacidad del supervisor: `plan --acceptance product|tooling` (product por defecto), estado `reviewed_tooling_ready` exclusivamente si gates + cuatro auditores aprueban y cada ruta modificada pertenece a allowlist cerrada de supervisor/contratos/dos tests/docs concretos; ningún cambio de producto se puede aprobar con perfil tooling. El mismo código sigue sin autorizar merge, push, deploy ni acceso a datos reales. El perfil producto conserva `reviewed_browser_gate_pending` y la exigencia de E2E autenticado.

## Limitaciones y próximo criterio de aceptación

No se ejecutó un bucle entero `supervisor.run` con un error real seguido de una segunda llamada Codex y cuatro dictámenes: **dos modelos repararon realmente la misma versión defectuosa de forma independiente**, y el paso de reparación automática del supervisor sigue respaldado principalmente por tests deterministas. No se ha medido el coste de una feature productiva P4 ni un navegador autenticado. La recomendación es mantener Sol como buena opción para reparaciones no triviales (la política existente ya lo hace cuando `round > 1`), no eliminar Luna por este resultado único. Antes de delegar P4→E6: validar una reparación real sin supervisión, controlar de forma más estricta el límite de consumo intrasesión si el CLI lo admite y conectar pruebas y notificaciones E2E, sin crear un servicio nuevo ni tocar PROD.
