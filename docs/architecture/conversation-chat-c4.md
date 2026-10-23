# C4 — explicación segura de fallos a partir de recibos verificados

**Estado (23-10-2026):** implementado y probado en fuente; desactivado por defecto.
El checkout **DEV** y el marcador desplegado siguen en `ae281d1` con C3 activo;
C4 requiere además `ODYSSEY_CHAT_C4_ENABLED=1`, limitado por fábrica a
`ODYSSEY_DEPLOYMENT_ENV=DEV`. No se ha desplegado C4 ni tocado PROD.

## Problema y límites

C1 ya incluía `VerifiedFailure`, el prompt `ERROR_INSTRUCTIONS`, Luna
`OpenAIConversationGateway.explain_error`, una salida de solo enums y mensajes
controlados. No tenía un puente desde el `ApplicationResult` real de Core/E3
hasta la respuesta de n8n. C4 **no** interpreta excepciones arbitrarias ni
actúa como Router: es posterior a una ejecución tipada, con el mismo actor y
request, y solo aporta una explicación. No hace replay, altera decisiones de
Core, elige identidades, propone mutaciones ni convierte un fallo de proveedor
en una solicitud de escritura.

## Implementación

- `odyssey_runtime/conversation_error.py`: valida el recibo tipado y
  `application_result_to_response`, incluyendo request ID, estado,
  `product_outcome=CANNOT_ANSWER` y código estricto. Lista finita de
  orientaciones para familia temporal, ambigüedad de persona/tarea, capacidad
  ausente, reformulación, fallo operativo o desconocido. Una causa no
  reconocida obtiene `UNKNOWN` sin invocar al modelo.
- El número de escrituras procede **solo** de los identificadores afectados
  que devuelve Core. Una lista vacía **NO** se convierte en una afirmación de
  cero escrituras: la salida es `UNKNOWN` salvo confirmaciones positivas
  `SOME`. La etiqueta `ZERO_CONFIRMED` no se genera en este primer
  puente; requiere prueba independiente sobre el escritor físico.
- Una llamada opcional con el gateway C1 recibe solo estado, código y
  `write_evidence` (sin request ID, Markdown, nombres, prompt del usuario
  ni credenciales). Para aceptarla, los dos enums deben coincidir con la
  orientación autorizada por el código verificado y no autorizar retry. Un
  fallo de transporte/JSON/semántica mantiene la recomendación determinista.
- `RuntimeComposition._finish_product_result` adjunta
  `error_guidance` antes de crear el recibo inmutable (con protección
  contra excepciones del intérprete); no se ejecuta en success ni ante las
  aclaraciones con opciones verificadas. La fábrica incorpora un interruptor
  **específico de C4**: activar C3 no lo activa implícitamente.
- La proyección `workflows/odyssey-online.ts` solo renderiza C4 si coincide
  la totalidad de claves esperadas, estado y razón de Core, metadatos de
  escritura `UNKNOWN/SOME` y los enums permitidos. **La redacción final
  es una plantilla de n8n**, nunca texto libre del modelo; si la propuesta es
  inválida conserva la respuesta previa. Las escrituras parciales conservan
  su estado, botón/snapshot y evidencia.
- C4 no convierte una pregunta posterior de Chat («¿por qué falló?») en
  una consulta libre a resultados de otros actores; esa recuperación
  actor-scoped, con comprobación de frescura del recibo, queda pendiente.

## Evidencia y límites

- Gate transversal final: **2.017 Python + 195 JavaScript PASS**, 12 grupos,
  registrado en `/tmp/odyssey-c4-source-gate-20261023.json` y su `.log`.


- Tests `tests/runtime/test_conversation_error.py`:
  razón/modelo/error/transporte, evidencia parcial/unknown, mismatch,
  actor autenticado, fallback y replay.
- Tests de la proyección **real compilada** en
  `tests/odyssey_chat_c3_workflow.test.mjs`: fracaso temporal, parcial,
  cuerpo malicioso, campos ocultos, estado erróneo y razón contradictoria.
- Matriz real con `gpt-6-luna`, esfuerzo `low`, `store=false`, **seis
  llamadas acotadas, ≤3300 tokens de salida presupuestados** y recibos
  exclusivamente sintéticos. Prompt inicial: **3/6**; tres respuestas fueron
  demasiado genéricas. Tras aclarar la semántica de códigos existentes sin
  relajar la seguridad: **6/6**, prompt SHA256
  `8024cf1defc4854055059caaca1dbeffb7d20734f5532a9eb511d9d03f4b044c`.
  Logs `/tmp/odyssey-c4-live-errors-20261023.log` y
  `/tmp/odyssey-c4-live-errors-v2-20261023.log`.
- La matriz no es navegador→DEV ni usa Core o n8n desplegados.
  **APP E2E NOT VERIFIED.** La aceptación requiere auditoría independiente,
  copia/rollback DEV y test real desde Chromium, incluyendo fallo
  sin escrituras confirmadas, fallo parcial, aclaración normal y replay,
  sin modificar datos personales.
