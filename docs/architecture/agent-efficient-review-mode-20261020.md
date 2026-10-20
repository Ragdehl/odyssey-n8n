# Modo de trabajo económico — implementación ChatGPT y auditoría Codex (20-10-2026)

## Decisión del operador
ChatGPT desarrolla y corrige directamente en una rama aislada, ejecuta y verifica los tests y prepara evidencia reproducible. Codex NO programa inicialmente ni reconstruye la funcionalidad: lanza **solo una ronda** de los cuatro revisores independientes Generality, Quality, Testing y Performance sobre el commit final. Los revisores usan un perfil read-only; el supervisor conserva el fingerprint exacto de Git, la comprobación de permisos y los gates. Los cuatro siguen siendo obligatorios en producto.

Si falla un revisor, no iniciar Builder ni tres rondas de reparaciones. Registrar exactamente el hallazgo; ChatGPT corrige y repite los gates, y se organiza la nueva revisión acotada a la modificación afectada conservando evidencia de lo ya aprobado, sin reutilizar aprobaciones de un snapshot diferente como si fueran actuales. No saltarse una revisión cuando la identidad del código haya cambiado.

## Medición y causa del agotamiento
Los jobs E4 `e4-closure-review-fixed-20261020` y `e4-final-audit-20261020` reportan respectivamente 415.052 y 547.882 tokens Codex CLI, total 962.934 reportados. De ese total, Builders de reparación consumieron 150.070 y 254.248, **404.318** reportados; los ocho auditores combinados consumieron **558.616**. Hubo además repetición por cambios todavía abiertos, fallos iniciales de tamaño de evidencia (antes límite 128 KiB) y un intento de tercera reparación frustrado por cuota real; esa tercera sesión interrumpida puede no estar reflejada en el total reportado. Son tokens de CLI, **no la cuota real de ChatGPT**, y no se sabe qué fracción consumió caché/procesamiento interno.

La reserva local `scripts/odyssey_agent_pacing.py` usa un proxy semanal de tokens CLI y una división diaria: no lee el medidor real de la cuenta, no detiene una sesión ya iniciada cuando llegue al límite y no predice la cuota de 5 horas. No subir el proxy para interpretar falsamente que hay cuota real.

## Prueba completa antes de auditar
E4 (`a632502` antes del endurecimiento del paquete de revisión) superó a 20-10 el test Chromium autenticado local → n8n Docker sin red externa → GPT real en host → Core/Tasks Writer → Markdown y nota de día → gráfico y Notes después de recarga → replay E3 SHA idéntico. Se conserva todo en documentación E4. No es Cloudflare Access externo ni DEV desplegado.

## Límite y activación
El último error de Codex indica `try again at 1:56 PM` y la Pi tiene `Europe/Paris`/CEST; interpretar **13:56 del 20-10 como estimación de la CLI**, no como acceso a telemetría oficial. Un lanzador local one-shot protegido por `flock`, comprobación de fecha, snapshot y estado `planned` activa **solo** `run --max-rounds 1 --live` poco después. Si sigue bloqueado por proveedor o memoria, el ciclo queda en fallo verificable; no relanzar indiscriminadamente. No usar Codex Builder. Un control de seguimiento separado informa del estado, sin iniciar otro ciclo simultáneo.

Nunca auto-desplegar ni tocar Cloudflare, DEV/PROD, secretos, notas personales o vault real; las cuatro revisiones evalúan la rama y sus pruebas, no autorizan producción por sí solas.

**Verificación pre-auditoría:** cross-surface gate 1.343 Python + 178 JS y 7 subtests PASS, Ruff PASS; el diff completo incluido en el paquete cabe por debajo de 192 KiB.
