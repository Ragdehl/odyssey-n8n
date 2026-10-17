# P4 — DEV real: primera campaña de mensajes con n8n y GPT (17-10-2026)

## Despliegue autorizado, alcance de pruebas y evidencias

**Autorización del usuario en este turno** para instalar la rama en DEV y probar diversos mensajes end-to-end. Solo entorno aislado `/home/ragdehl/projects/odyssey-dev`, `/data/odyssey-dev`, actor sintético `odyssey-dev`; **PROD `/data/odyssey` y el servicio PROD no se han tocado**. Tras commit `e234d1e` (único flag `ODYSSEY_LIGHT_SOURCE_V1=1` añadido a la unidad DEV), `scripts/odyssey-dev deploy` informó éxito; el backend, frontend, n8n y configuración de Cloudflare marcaron el mismo commit, `workflow_source_provenance=MATCH` y `public_route_provenance=MATCH`, salud DEV/PROD 200. En la Raspberry no hay browser Chromium/Playwright disponible; la prueba ejercita **el propio módulo JS `odyssey_web/client.js` en Node contra el webhook n8n LOCAL `/api/request` y `/api/conversation`**. Esto prueba el recorrido real JS→n8n→GPT→runtime→Markdown y transcript, pero NO la visualización gráfica efectiva en navegador ni la animación real del donut. El gate estático Python→workflow-source→cliente del checkpoint anterior sigue siendo offline.

## Casos enviados por web client real a n8n real

| ID | Mensaje fuente sintético | Resultado observado de n8n | Prueba Markdown/historial |
|---|---|---|---|
| read02 | «¿Dónde trabajo?» | `completed`, answer «Trabajas en Synthetic Systems», 6 etapas | Sin mutación, respuesta visible persistente en historial |
| self01 | «Hoy he conocido a Irene Neblina.» | `failed`, `INCOMPLETE_EVIDENCE` | Planner identifica SELF y día, Calendar Day UPDATE falla; ninguna nota creada |
| date01 | «El 29 de septiembre de 2026 conocí a Nuria Niebla.» | `failed`, `INCOMPLETE_EVIDENCE` | Calendar Day CREATE falla; ninguna nota creada |
| plain01 | «Ayer limpié una lámpara de prueba.» | `failed`, `INCOMPLETE_EVIDENCE` | Calendar Day UPDATE falla; ninguna nota creada |
| task01 | «Crea una tarea llamada preparar informe Neblina para el 20 de octubre de 2026.» | `completed`, acknowledgement, 8 etapas | Archivo task real `57c46639-412d-4db6-b717-d62da5d87b67.md`, status pending, target_date 2026-10-20; turno user/assistant persistido |
| session01 | «Inicia una sesión de trabajo en preparar informe Neblina.» | `completed`, acknowledgement, 5 etapas | Comprobar Session Markdown física (tarea anterior) |
| stop01 | «Termina la sesión de trabajo de preparar informe Neblina.» | `completed`, acknowledgement, 5 etapas | Comprobar mismo Session Markdown y `ended_at` |
| task01 replay mismo ID | texto task01 idéntico | **BUG:** HTTP 200 con cuerpo vacío; frontend lanza error «unreadable response» | Immutable E3 receipt y Markdown task original existen; ninguna prueba de duplicación todavía |

Todos los IDs tienen prefijo `p4dev20261017-`; se verificó con `requestConversation(operation=main)` que las respuestas de primera ejecución **sí** reaparecen al volver a cargar el historial. Existe defecto separado en la respuesta HTTP al replay. Los E3 responses completos están almacenados en `.../state/conversations/<actor>/delivery-results/<sha256(request_id)>.json`.

## Diagnóstico y cambios de seguridad

Recibos internos de `self01`, `date01`, `plain01`: Core Planner completado, `action.write` SKIPPED con `reason="Calendar Day record failed"`, SELF `REFERENCE_BOUND` cuando corresponda, hecho dependiente aplazado. El `pending_recorder` opcional P4 no se inyectaba en composición productiva y devolvía «pending recorder is not configured»; se conectó al `PendingWorkRepository` EXISTENTE. En una prueba aislada `capture_calendar_day_literal` sí crea/actualiza Days, aun con `scoped_note_decode_cache` y metadata catálogo, así que hay que obtener la excepción física envuelta mediante diagnóstico acotado DEV, diagnosticar causa y corregir sin tocar otro Writer.

Se detectó en `workflows/odyssey-online.ts` que el camino directo `select.output(1)` acababa en `persistAssistant` **sin** enlazar a `Respond to Odyssey browser`; la primera respuesta se registraba, pero replay devolvía 200 vacío. Se conectó a `respond`. En backend `persist_product_assistant_response` ahora comprueba contra el turno ya guardado el mismo texto/status y devuelve su diagnóstico/snapshot original aunque cambien timings opcionales; ante texto/status conflictivo sigue rechazando con 400. `LocalConversationStore.find_turn` verifica índice y chunk físico para no confiar en metadatos sueltos. Tests HTTP de asistencia: 30 PASS. Hay un diagnóstico acotado a DEV `ODYSSEY_DEV_DAY_CAUSE` temporal que DEBE retirarse tras encontrar la causa Calendar.

**Estado del gate:** falta desplegar y verificar los fixes en DEV, repetir los casos fallidos con IDs NUEVOS (no reusar claims/recibos existentes) y comprobar replay HTTP/Markdown con el mismo ID. No proclamar E2E verde todavía. No usar información o nombres personales de usuario para la campaña. No habilitar PROD ni merges ni pushes.
