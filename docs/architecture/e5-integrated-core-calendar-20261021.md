# E5 — Integración incremental posterior a E4 (21 octubre 2026)

## Alcance real y estado

Rama de trabajo: `feat/e5-events-integration-20261021`, basada en el
checkpoint E4 `7b09266`. DEV sigue desplegado con la versión E4 `d03737f`.
E5 **no** se ha desplegado ni está lista para mensajes de usuario.

El carril E5 anterior aporta `EventInterpretation`, el validador de
propuestas fuente-anchadas, CREATE/UPDATE/CANCEL/QUERY/ABSTAIN y nueve
propuestas GPT reales de intención. Esa evidencia sigue siendo exclusivamente
interpretación, no un E2E de producto.

## Integración nueva, demostrada con datos sintéticos

- `EVENT_SCHEMA_EXTENSION` registra `event` mediante el mecanismo genérico
  `compose_application_schema` junto con Tasks. El Core sigue siendo dueño
  de identidad, permisos, notas Markdown, timestamps y Writer.
- Metadata Events: `event_status` separado de `task.status`, `start_date`
  obligatorio, `end_date` inclusivo opcional, horas con offsets explícitos,
  `recurrence_weekday` entero 0–6 dentro de un intervalo **finito**.
  Una repetición horaria queda pendiente del contrato DST/zona de Temporal;
  se rechaza en lugar de copiar un offset incorrecto.
- Calendar lee la declaración de proyección del tipo registrado y muestra
  fechas/intervalos/eventos con hora/recurrencias semanales y cancelaciones
  en mes, día y agenda 1/3/7. El tipo `Event` no se transforma en `Task`.
  Se han ampliado las respuestas/validadores del cliente web, icono y
  sección Eventos; no existe aún edición desde el navegador.
- `EventMutationService` usa **preflight_write_action**, Core
  `materialize_create`/`materialize_update` y
  `CanonicalMutationGate` para crear, reprogramar y cancelar. Identidad,
  ruta y asignación de IDs las decide Core. UPDATE/CANCEL requieren Note ID
  autorizado, revisión/hash actuales y readback; solicitudes de tipo ajeno o
  con CAS obsoleto se rechazan. Cancelar conserva el Markdown original.
- Estas pruebas del servicio son **comandos confiables inyectados en fixtures**,
  no una ruta accesible a modelos. No incluyen aún manifest de idempotencia
  de entrega de chat, ni la autorización de usuario/n8n; está prohibido llamar
  al servicio desde un modelo sin esas fronteras.

## Pruebas y aceptación

`tests/apps/events/test_event_calendar_vertical.py`,
`test_event_core_e3_mutations.py`, interpretación, propuestas y
`tests/apps/calendar`: **132 PASS**. Cliente Calendar JavaScript
`tests/odyssey_web_calendar.test.mjs`: **15 PASS**. Las pruebas adversariales
incluyen fecha inválida, rango invertido, tiempo sin offset, recurrencia no
acotada y repetición con DST inseguro, alias de estado Task/Event, clase de
nota incorrecta, CAS obsoleto y cambios que no pueden generar una Task.

La aceptación de producto E5 todavía exige un caso completo
GPT real → n8n → Router/E2/Temporal → E3 Writer → Markdown →
Notes/Calendar/Chromium y replay sin duplicados; casos CREATE, UPDATE,
CANCEL y QUERY, mezcla Task+Event, varias entidades, fechas ambiguas y
mensajes largos. No se fingirá un PASS a partir del servicio aislado.

## Siguiente integración, acotada

Conectar la operación tipada Events al dispatcher genérico y su actor
autenticado; incluir verificación de fuente/fecha de Temporal y
manifest de entrega E3 antes de permitir cualquier operación con efecto.
Después ejecutar la matriz E5 sobre vaults sintéticos con prueba de interfaz
y aceptación funcional, **sin repetir las cuatro auditorías masivas**.
DEV/PROD, Cloudflare y las notas personales permanecen fuera de esta etapa.

## Integración E5 del Router (22-10-2026) — todavía pendiente n8n/Chromium

Se ha ampliado el **Router híbrido solo cuando Events esté habilitada** con kind fuente `event`, manteniendo `occurrence` para hechos personales y `task` para tareas. El intérprete Events usa GPT real (esquema JSON estricto) y cita exacta del nombre; E2 Temporal resuelve las fechas y `EventMutationService` reutiliza Core/E3. El resultado de escritura va al `ApplicationResult` estándar; el mismo ID de entrega conserva el manifest/replay de producto existente. Se han añadido guardas: actor autenticado, referencia Event inequívoca, rechazo de herencia de fechas entre rutas no validada y `PARTIAL` con ID afectado si la lectura posterior falla. No se activan Event ni rutas nuevas en PROD.

**Ensayos observados**: 3/3 solicitudes sintéticas con GPT real + Temporal + Core E3 + Markdown PASS (crear, reprogramar y cancelar; una sola nota Event); calendario cancelado sin evento visible. Una primera prueba de Router real dio 4/5: CREATE declarativo mal clasificado como `occurrence`; se corrigió el prompt opt-in y una nueva llamada real confirmó `event → events`. Regresiones transversales finales: **1.697 Python +181 JavaScript +7 subtests PASS**, Ruff PASS. Dos tests adicionales prueban que un fallo postwrite nunca se transforma en falso NO_WRITE y que QUERY sin lectura conectada se abstiene.

**Pendientes que impiden declarar E5 lista:** conectar lectura QUERY con presentación visible, recurrencia semanal de lenguaje natural al contrato compartido de Temporal (sin adivinar días o DST), aprobar flujo mixto Event+Task, y **ejecutar HTTP n8n real → runtime E5 → Core/Markdown → Chromium móvil/escritorio y replay** tras un despliegue de DEV con `ODYSSEY_ENABLED_APPLICATIONS=tasks,events`. En este ensayo el servicio DEV sigue con `tasks` y commit E4 `d03737f`; todavía no se ha realizado ese despliegue ni la comprobación de navegador. NO afirmar E5 end-to-end/producto aprobada hasta superar esas pruebas. Las evidencias solo emplean vault efímero sin datos personales.

**Siguiente prueba preparada, no ejecutada:** `scripts/e5_real_hybrid_e3_vertical.py` reúne Router híbrido real, intérprete Events real, Temporal, Core E3 y lectura Calendar sobre bóveda efímera. Solo se han validado sintaxis y Ruff; el intento de lanzarla en una unidad efímera fue bloqueado por controles de seguridad de la herramienta remota, por lo que NO constituye evidencia de resultado. El servicio n8n de DEV aún apunta a E4 y no tiene Events habilitada. Mantener la aceptación E5 pendiente.
