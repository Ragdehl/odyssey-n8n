# Presupuesto y selección adaptativa de revisores — pruebas reales del 18-10-2026

## Resumen

El supervisor de desarrollo tiene una política declarativa validada en `ops/agent-team/model-policy.json`. La parte determinista ejecuta siempre `scripts/odyssey_cross_surface_gate.py`, ledger de aceptación y Ruff; los agentes se activan SOLO después del gate. En la primera entrega se exige reservar presupuesto suficiente ANTES de gastar tokens, según roles obligatorios. **Ningún cambio de producto, app de usuario, Core, Writer, runtime o workflow puede ser aprobado con un perfil de tooling.** Producto y tooling de riesgo alto/crítico exigen cuatro revisores (Generalidad, Calidad, QA y Rendimiento). Tooling normal de documentación interna y bajo riesgo exige dos (Generalidad y Calidad); QA y Rendimiento figuran como excluidos por alcance, no como PASS. Una modificación de `scripts/odyssey_agent_cycle.py`, política JSON, output schema o instrucciones de los especialistas se eleva automáticamente a riesgo alto, aunque el job dijera `normal`.

## Reserva y limitaciones del consumo

Se mantienen el límite inicial **110000 tokens CLI reportados** y reserva previa de **40000 por Builder**. Las estimaciones mínimas por auditor son Generalidad **55000**, Calidad **45000**, QA **55000**, Rendimiento **50000**. Se verifica el conjunto completo antes del primer trabajo y después de la implementación, sobre el diff real, además de comprobar la cuota restante antes de cada auditor. El mecanismo puede detectar falta de reserva y no iniciar nuevos modelos; **no limita exactamente el consumo intrasesión**, porque Codex sólo comunica la cifra al concluir la sesión. La regla de riesgo declarada es una preferencia mínima, nunca una excepción a la clasificación basada en el código cambiado.

## Prueba real A — riesgo alto, sin gastar un solo token

Job `risk-preflight-20261018`, perfil `tooling`, `--risk high`, presupuesto 110000. El comando gratuito `route` calculó **205000 tokens mínimos** para los cuatro auditores y señaló `can_start=false`. `run --live` cerró con RC=3, fase `blocked_insufficient_review_budget`, `ready_for_user=false`, **0 sesiones de IA, 0 tokens reportados y sin crear worktree**. Persistió evidencia bajo `/home/ragdehl/projects/.odyssey-agent-runs/risk-preflight-20261018/`.

## Prueba real B — documentación tooling normal, 2 agentes PASS

Commit original de documentación `be3e312` frente a base `d4fd311`; job `routine-tooling-audit-pilot`, perfil tooling/normal, 110000 tokens. Se ejecutó el gate transversal completo, ledger y Ruff: **todo PASS**. Después Generalidad con **GPT-6 Luna low: PASS/42134 tokens**, y Calidad/Seguridad con **GPT-6 Luna low: PASS/40028 tokens**. Total **82162 tokens reportados**, menor que 110000, dos sesiones IA y ninguna sesión de Builder (la modificación inicial era obra de ChatGPT). Estado terminal **`reviewed_tooling_ready`**, `ready_for_user=true` significa *documento interno listo para revisar por mantenedor*, NO despliegue de Odyssey. QA y Rendimiento no se ejecutaron y no figuran como aprobados. Evidencia original: `/home/ragdehl/projects/.odyssey-agent-runs/routine-tooling-audit-pilot/status.json` y `round-1/*.json`. No es una comparación A/B de dos funcionalidades idénticas con distinto número de auditores, ni prueba suficiente para reducir controles de producto.

## Prueba real C — elevación AUTOMÁTICA, pese a etiqueta incorrecta

Commit `7daf590` con código y `model-policy.json` modificados, baseline `be3e312`. Job `auto-risk-preflight-20261018`, `--risk normal --acceptance tooling --token-budget 110000`. La consulta gratuita detectó `auto_escalated_by = [ops/agent-team/model-policy.json, scripts/odyssey_agent_cycle.py]` y fijó `effective_risk=high`, los cuatro roles y **205000 tokens de reserva**. La ejecución real devolvió RC=3, `blocked_insufficient_review_budget`, `ready_for_user=false`, **0 llamadas a IA y ningún worktree**. La falsa etiqueta normal no desactivó revisores.

## Validación automática y próximos límites

Al finalizar el cambio de escalada, **96 tests focales del supervisor PASS**, gate transversal **1152 Python + 174 JavaScript PASS y 7 subtests**, ledger 18 invariantes / 41 anclas, Ruff PASS. Los casos adversariales comprueban rutas sensibles, políticas manipuladas, falta de presupuesto, separación entre producto y tooling y ausencia de revisión parcial.

Esta fase resuelve la decisión de cuánto revisar y cuándo abortar por presupuesto. No sustituye el test browser→n8n→GPT→Core Writer→readback, que sigue siendo obligatorio para aprobar P4 de producto. Antes de delegar P4→E6 de manera desatendida faltan aislamiento OS de credenciales/datos, pruebas visuales reales y evidencias de cuatro auditores independientes dentro del presupuesto explícitamente autorizado para los cambios de alto riesgo. DEV sigue en `b0fc9b21` y PROD no han sido modificados.
