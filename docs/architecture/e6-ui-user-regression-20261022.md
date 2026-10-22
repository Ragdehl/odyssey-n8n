# E6 — prueba del recorrido real de usuario desde la interfaz (22-10-2026)

## Alcance y versión comprobada

**Se utilizó Chromium headless mediante clics, escritura y navegación reales**
sobre los archivos web **desplegados en DEV** (no un mock del frontend),
a través de un proxy temporal limitado a localhost. Se verificó en DOM la
versión efectiva `7fac3eac813bc65302bb378db26fd442943864d0`.
Las peticiones de escritura fueron remitidas al n8n real de DEV, con
allowlist de textos ficticios; las consultas/estado/calendario pasaron por
el proxy de lectura. No se accedió a PROD, ni se probó el enlace externo
Cloudflare, ni un móvil físico. Las llamadas a GPT fueron reales.

**Resultado funcional:** PASS en todos los recorridos efectuados. No implica
ausencia de defectos fuera de los escenarios ensayados.

## Matriz E2E de interfaz

| Recorrido probado | Resultado |
|---|---|
| Chromium móvil 390 × 844 y escritorio 1280 × 960: cargar chat, versión DEV, errores JS, reload | PASS |
| Inspección previa de 41 nodos de conversación y 20 detalles SVG en ambos tamaños, recarga y solo lecturas | PASS |
| Móvil: escribir mensaje completo en el textarea y pulsar Enviar → progreso real 0→8→94→Guardado | PASS |
| Crear Event ficticio `Concierto ficticio UI E6 C246A088` para 2026-10-29 por la GUI | PASS, 1 escritura HTTP |
| Abrir gráfico/detalle del nuevo mensaje: SVG presentes y legibles | PASS, 6 SVG |
| Calendario mensual muestra Event el 29-10-2026; abrir vista Día y comprobar título | PASS |
| Desde Notas, buscar Event por nombre único y abrir ficha | PASS, exactamente 1 coincidencia |
| Conversación sobrevive a reload tras crear Event | PASS |
| Escritorio: escribir y enviar `Mañana tengo que preparar el informe ficticio UI E6 F9E6A670.` | PASS |
| Desde Notas, localizar Task y abrir ficha, estado inicial Pendiente | PASS, exactamente 1 coincidencia |
| Pulsar check Task → Completada → pulsar Reabrir Task → Pendiente | PASS, dos mutaciones reales E3 |
| Conversación sobrevive a reload tras crear Task | PASS |
| Vista Día del 23-10-2026 muestra Task; vista Día del 29-10-2026 muestra Event, móvil y escritorio | PASS |
| Vista 7 días: Task en 22–28 oct; navegar a 29 oct–4 nov y encontrar Event | PASS |
| Cambiar a 3 días: esperar al render de `calendar-schedule-3`, Event presente en 29–31 oct | PASS |
| Cambiar a 1 día: esperar al render de `calendar-schedule-1`, Event presente el 29 oct | PASS |
| Excepciones JavaScript y errores API en todos los ensayos Chromium | 0 |
| Readback de Markdown del Event (tipo/event_status/start_date) | 1 Event, scheduled, 2026-10-29 |
| Readback de Markdown Task tras marcar y reabrir | 1 Task, pending, 2026-10-23, revisión 3 |
| Runtime DEV, n8n y código desplegado, tras las pruebas | HTTP 200, commit `7fac3ea` |

## Latencia observada y limitaciones reales

Desde el clic de Enviar hasta el acuse de la interfaz, una ejecución
**Event 26,4 s** (operación registrada backend ~21,8 s) y una **Task 39,0 s**
(backend ~34,2 s). No es p50/p95 ni análisis estadístico; constituye una
**preocupación de UX**. Se observaron las etapas de interpretación de
Events/Tasks y Temporal, y la etapa de Planner en Tasks; estas métricas no
explican por sí solas toda la latencia de extremo a extremo.

Los detalles del chat contienen `operational.stages` y gráficos, pero
los dos resultados analizados carecen de `request_detail.flow`;
por ello la UI muestra el aviso de que esta solicitud no conserva
la división de Router ni las transformaciones por etapa. **No se ha
demostrado que sea una regresión de E6**; se registra como limitación de
diagnóstico. Los gráficos mostrados no prueban una traza Router completa.

No se han probado mediante esta sesión: autenticación externa Cloudflare,
móvil físico, todos los contratos lingüísticos y relaciones N:M, cada
camino de error, cargas concurrentes, p95/p99 sostenido, nueva Projects
con GPT, UX de WorkSessions/subtareas, capturas antiguas o accesibilidad
integral. Los gates offline ya pasan 1848 Python +181 JavaScript +7
subtests y el E2E HTTP previo cubrió cancelaciones/reprogramación/replay.
Esos recibos se conservan, sin confundirse con los clics reales aquí.

## Reproducibilidad y seguridad

La restauración temporal de bibliotecas gráficas de Chromium se dejó en
`/tmp/odyssey-e6-browser-deps` (extracción de 16 paquetes en temporal,
sin instalar cambios de sistema). Los scripts y recibos están en:

- `/home/ragdehl/projects/.odyssey-agent-runs/e6-ui-user-path-20261022.cjs` y `.log`
- `/home/ragdehl/projects/.odyssey-agent-runs/e6-ui-task-path-20261022.cjs` y `.log`
- `/home/ragdehl/projects/.odyssey-agent-runs/e6-ui-calendar-views-20261022.cjs` y `.log`
- `/tmp/odyssey-e6-final-ui-readonly-20261022.log`
- Captura visual móvil en `e6-ui-user-path-20261022/mobile-after-submit.png`.

Las escrituras se limitaron a dos mensajes sintéticos únicos y a las dos
transiciones de esa misma Task; la comprobación física posterior confirma
una Event y una Task, sin duplicación en sus nombres exactos. No se
modificó código de producto, configuración PROD ni datos PROD. Las notas
ficticias quedan identificadas por su nombre para poder limpiarlas cuando
proceda, sin confundirlas con datos reales.

**Decisión:** rutas principales de Event y Task comprobadas desde GUI
funcionalmente PASS. No declarar «sin regresiones en toda la aplicación»;
seguimiento recomendado: p95 de latencia, detalle completo de flujo
Router en operaciones de Apps y pruebas de Work Sessions/subtareas con GUI.
