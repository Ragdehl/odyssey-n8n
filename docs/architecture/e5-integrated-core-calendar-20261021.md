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
