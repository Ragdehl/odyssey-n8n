# E4 v8 — reparaciones tras auditoría independiente (21-10-2026)

**Código precedente:** `90d8994`; **última auditoría:** `e4-v7-full-audit-20261021` (Generality FAIL / Quality FAIL / Testing BLOCKED / Performance BLOCKED). Esta intervención la implementó directamente ChatGPT en la rama aislada; **no implica aprobación de E4 ni despliegue**.

## Correcciones verificables

1. **Generality (Core independiente).** `verify_dependent_group_graph` dejó de exigir que todo Core anterior sea un referente obligatorio: una anotación «Terminé el informe» puede preceder a «Conocí a Ana y Luis. Mañana tengo que llamar a los dos». El veto de un tercer Core de la misma forma fuente («Conocí a Marta») sigue en la etapa estructural; además el E2 físico reexamina los grupos previos, sus pruebas Core y sus Notes realmente afectadas. Una nota SELF que contiene un hecho distinto no se interpreta como un tercer referente por ser físicamente de tipo Person. Si no hay recibo fiable de un grupo anterior, se abstiene. No se inventan identidades ni enlaces.
2. **Generality (modificadores).** La cobertura de nombres finitos admite complementos acotados de lugar/tiempo en la *misma cláusula* («en el parque», «hoy por la mañana») en español, francés e inglés; sigue vetando una continuación de lista, cláusula extra o introducción explícita de otra persona, incluso en minúsculas. No se omiten caracteres del texto original.
3. **Quality (postwrite).** Nuevo helper genérico `odyssey_core/plural_task_readback.py`, ejecutado por la composición de Tasks después de Core Writer. Para comunicar `completed` exige una Task canónica afectada físicamente cuyo Markdown contenga **todos** los enlaces a los IDs Persona realmente resueltos por Core, sin IDs propuestos por GPT. Una pérdida postwrite degrada a `partial`, conserva IDs afectados y la semántica E3. Prueba adversarial en bóveda sintética retira literalmente el wikilink de Ana después de la escritura y exige `partial`.
4. **Testing (progreso).** El ensayo Chromium captura con MutationObserver la evolución real del donut durante toda la petición (no solamente su valor inicial 0%). La prueba viva mostró **[0,8,18,84,94]**, sin retrocesos, sobre datos sintéticos.

## Gates ejecutados

- Focal E2/source cohort/Graph/Tasks/vertical: **119 PASS** en un corte anterior y **9 PASS** adicionales al ensayar SELF y pérdida física; la batería transversal **1.527 Python + 179 Node + 7 subtests PASS**, `/tmp/e4-v8b-cross-20261021.log`.
- Lint Ruff y formato en los archivos tocados; navegador real Chromium + n8n aislado + GPT vivo + Writer canónico + Markdown y ambos backlinks **PASS**:
  - `/tmp/e4-v8-live-20261021.log`: 2 Persons / 1 Task / 1 Day, 4 recibos, replay idéntico, 86,73 s E2E, medición de proceso 91,99 s, RSS máx Python 118.544 KiB.
  - `/tmp/e4-v8-donut-live-20261021.log`: mismos invariantes, secuencia donut [0,8,18,84,94], 77,79 s E2E, proceso 85,14 s, RSS máx Python 118.496 KiB, RSS máx subprocess 203.712 KiB. No mide recursos totales del Docker/browser ni Cloudflare.
- Microbenchmark dedicado a la nueva validación de Markdown; 25 repeticiones por tamaño de bóveda sintética, **sin GPT ni embeddings**: 50 notes + Person/Task: p50 25,369 ms/p95 empírico 25,544 ms; 250: 114,203/114,633 ms; 1000: 451,541/453,747 ms. Registro `/tmp/e4-v8-readback-perf-20261021.log`. Estos percentiles son solo del helper en bóveda sintética, no del usuario.
- Se mantiene separada la suite global con **nueve benchmarks heredados FAIL**, 80 SKIP en la pasada previa. Una batería transversal PASS no permite decir que la suite global entera sea PASS.

## Límites que impiden declarar cuatro PASS hoy

No hay aún un presupuesto de latencia/CPU/RAM aceptado, ni distribución representativa p50/p95 **del producto con GPT** o ejecución FastEmbed cold/warm en una caché sintética disponible. El modelo no estaba en la caché offline probada anteriormente; no se invoca el caché privado de DEV/PROD. El donut y enlaces sí tienen ensayo vivo. Esta intervención **NO reetiqueta** los dictámenes v7 ni certifica una tasa GPT a partir de dos ejecuciones. Quedan la auditoría sobre el nuevo SHA exacto, la campaña de Performance y Cloudflare Access antes de cualquier despliegue.

DEV/PROD, notas privadas y E5 intactos; código únicamente en worktree experimental.

## Recibo estructurado del E2E sobre el SHA de código final

**Código fuente congelado:** `1c79b3c64a980821242839bd79df3386c3947838`. Archivo inspeccionable desde el worktree de futuros auditores: [`e4-v8-gpt-browser-receipt-20261021.json`](e4-v8-gpt-browser-receipt-20261021.json). El recibo fue generado automáticamente leyendo la ejecución real de ese SHA, comprobando que el árbol Git estaba limpio, extrayendo únicamente campos sintéticos acotados, y adjuntando huella SHA-256 del log completo.

Resultado **PASS, exit 0**: GPT real, n8n Docker aislado, Chromium con cookie sintética; **74,15 segundos E2E**, 2 Person/1 Task/1 Calendar Day, cuatro recibos físicos, búsqueda Task y ambos backlinks visibles en UI, E3 replay sin cambios, 0 errores JS, flujo gráfico visible incluso tras recarga, `progressTrace.observed = [0,8,18,84,94]` con progreso monótono. El proceso instrumento consumió **78,4 s**, RSS Python máximo **117.344 KiB**, subproceso máximo **198.768 KiB**; no se puede confundir con uso global de RAM/CPU de Docker. No hay datos privados ni credenciales en el JSON. El modelo real no es una grabación; la cookie y la bóveda sí son sintéticas.

**Importante:** este recibo elimina específicamente la falta de evidencia inspeccionable señalada por Testing v7; no cambia retrospectivamente su dictamen ni certifica rendimiento p95, disponibilidad de FastEmbed o autenticación Cloudflare Access.
