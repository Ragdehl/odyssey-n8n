# E6 — Diagnóstico UX y prueba real final, 22-10-2026

DEV código probado y desplegado: `5951830645a3070e6cb72ec40315840f4ee6cf14`. Producción no se modificó.

## Problema identificado y corrección

Events generaba `execution_flow` sin el campo obligatorio `temporal` y con `steps=[]` para una ruta que sí registraba etapas. Tasks conservaba evidencia interna pero sin el contrato público `version/routes`. Los validadores de n8n y navegador, correctamente, omitían la ruta incompleta. La corrección de `odyssey_runtime/whole_source_light.py` convierte **únicamente** las rutas directas completadas y realmente observadas de Tasks/Events al contrato público: incluye Router medido, pasos comprobados y revisiones de fuente previas, sin inventar splits ni autorizar nuevas escrituras. Un segundo parche evita duplicar revisiones temporales dentro de la duración del Router.

Código: commits `c26f801` y `5951830`. Pruebas directas: 30 PASS. Gate transversal completo: **1850 Python y 181 JavaScript PASS**. Ledger: 21 invariantes, 57 anclajes. Nada de esto demuestra una mejora de rendimiento.

## Evidencia de producción simulada en DEV

Relevamiento sintético GPT→n8n→Core/E3→Markdown→Calendar, commit `5951830`: **PASS**, rechazó CANCEL de fecha incorrecta, ejecutó CANCEL correcto, reprogramó, no creó evento multidía falso y replay dejó bytes idénticos.
Recibos: `/home/ragdehl/projects/.odyssey-agent-runs/e6-direct-flow-second-acceptance-20261022/{orchestrator.log,e2e.log,backup-sha256}`.

**Chromium móvil 390x844**, clic real para crear Event y abrir gráfico: `routeLanes=1`, `legacy=false`, 8 SVG, día 29-10 correcto, nota única encontrada y visible después de recarga. Tiempo de envío **22,4 s**; Router observado **8238 ms**. Sin errores JS ni HTTP.
Recibo: `/home/ragdehl/projects/.odyssey-agent-runs/e6-ui-verified-event-20261022.log`.

**Chromium escritorio 1280x960**, clic real para crear Task, abrir gráfico, localizar nota, marcar Completada y después Reabierta con las dos mutaciones E3, recargar: `routeLanes=1`, `legacy=false`, estado final Pendiente, sin errores JS ni HTTP. Tiempo **32,4 s**.
Recibo: `/home/ragdehl/projects/.odyssey-agent-runs/e6-ui-verified-task-20261022.log`.

## Incidencia y recuperación de despliegue

Un despliegue quedó interrumpido al parar n8n, con checkout nuevo y web preparada pero marcador anterior; se detectó y se restauró con despliegue completo al checkpoint seguro `7fac3ea` antes de realizar el despliegue final `5951830`. Ambos servicios y su marcador deben comprobarse tras la prueba. Copias de seguridad de DEV y n8n tienen SHA256, con baseline `7fac3ea`.

## Limitaciones no cerradas

Los tiempos medidos **no son p95/p99** y no prueban rapidez suficiente. La operación anterior de Task (34,18 s backend) dedicaba ~4,33 s al Planner, ~0,163 s a escritura y ~0,095 s a Git; faltaba visibilidad de revisiones previas. Nueva telemetría permite inspeccionarlas, pero sin evidencia que justifique eliminar auditores o reintentos GPT. No se han probado móvil físico, entrada pública Cloudflare, WorkSessions/subtareas ni todos los casos multilingües desde el navegador. No declarar ausencia universal de regresiones.
