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
  `SOME`, incluso cuando se afectan más de 64 notas. Para conservar el esquema
  bounded de C1, la magnitud privada se trunca en 64 y sirve **solo** para la
  clasificación SOME/UNKNOWN, nunca como contador exacto mostrado al usuario.
  La etiqueta `ZERO_CONFIRMED` no se genera en este primer puente; requiere
  prueba independiente sobre el escritor físico.
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
- Las respuestas con orientación C4 mantienen el **status exacto de Core** (`failed`, `partial`, `needs_attention`), incluso cuando el resultado es parcial pero no hay ningún conteo de escritura verificable. No se convierte `partial` en `failed` por defecto.
- La proyección `workflows/odyssey-online.ts` solo renderiza C4 si coincide
  la totalidad de claves esperadas, estado y razón de Core, metadatos de
  escritura `UNKNOWN/SOME`, el código que autoriza cada clase de consejo y
  los enums permitidos. Las aclaraciones de identidad son neutrales al tipo
  de entidad o App. **La redacción final
  es una plantilla de n8n**, nunca texto libre del modelo; si la propuesta es
  inválida conserva la respuesta previa. Las escrituras parciales conservan
  su estado, botón/snapshot y evidencia.
- C4 no convierte una pregunta posterior de Chat («¿por qué falló?») en
  una consulta libre a resultados de otros actores; esa recuperación
  actor-scoped, con comprobación de frescura del recibo, queda pendiente.

## Evidencia y límites

- Gate transversal final: **2.017 Python + 196 JavaScript PASS**, tras ajustar la conservación del estado parcial/needs_attention, 12 grupos,
  registrado en `/tmp/odyssey-c4-final-gate-20261023.json` y su `.log`.


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

## Auditoría independiente y corrección focalizada (23-10-2026)

- Job `c4-independent-four-audit-20261023` sobre SHA fijo `5765587`, base
  `3c27341`, solo lectura; supervisor ejecutó pruebas propias y los cuatro
  revisores **una sola ronda** (263.380 tokens CLI reportados, no cuota real
  verificada). Dictámenes del SHA antiguo: **Generalidad FAIL**, **Calidad
  FAIL**, **Pruebas BLOCKED**, **Rendimiento BLOCKED**. Resultados en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-independent-four-audit-20261023/round-1/`.
- Generalidad halló texto que limitaba `AMBIGUOUS_REFERENCE` a personas/tareas;
  se corrigió a **elemento de cualquier App**. También halló que la evidencia
  positiva de más de 64 notas se etiquetaba erróneamente UNKNOWN y n8n
  rechazaba SOME con más de 64: ambos corregidos. Nuevas pruebas Python y JS
  con 70/71 IDs afectados y una App de entidad futura, sin contadores inventados.
- Calidad y Pruebas señalaron que el test denominado «replay» podía ejecutar
  Core dos veces. Nuevo test usa el **guard de mutación E3 y el repositorio real
  de recibos en un actor efímero**, y exige exactamente una ejecución,
  `delivery_replayed=true` y orientación idéntica. También señalaron que un
  par válido pero **incompatible con `product_reason`** podía sobreescribir el
  consejo; n8n contrasta ahora la tabla de razones y lo rechaza. Regression
  JS con `OPERATIONAL_FAILURE` + `SPECIFY_DATE/ASK_USER` falsificados.
- Rendimiento solicitó medición Pi y concurrencia, no solo tiempos generales
  de pytest. `python -m scripts.odyssey_chat_c4_perf_gate` reproduce siete
  fallos sintéticos y sus replays en el *mismo runtime protegido*, con un
  proveedor **FAKE de latencia impuesta de 180 ms**, concurrencia 3, y sin
  escribir notas. Medición Raspberry Pi 4 GiB: p50 ~182 ms, p95 ~546 ms por
  serialización bajo concurrencia; RSS del proceso de ~36–37 MiB, swap del
  proceso **0**, MemAvailable ~1,8 GiB, temperatura **46–48 °C**, sensor de
  ventilador ~2.450 RPM (no confirma la curva en uso real). Fuente:
  `/tmp/odyssey-c4-pi-performance-reproducible-20261023.json`. **No** son
  latencias de GPT ni pruebas con embeddings cargados; no convierten el
  dictamen de Rendimiento en PASS.
- La última campaña previa con **Luna real** sobre seis recibos sintéticos
  dio ~1,4 a 8,4 segundos por llamada (mediana ~1,8 s; p95 *nearest rank*
  ~8,4 s), **secuencial**. No representa concurrencia real ni frío/caliente
  de Odyssey. La llamada opcional al modelo está hoy dentro del bloqueo de
  ejecución; la aceptación de rendimiento de C4 en DEV deberá medir su
  impacto real antes de aumentar el uso. No se han repetido llamadas pagadas
  después del arreglo: el prompt/modelo de consejos permaneció idéntico.
- Se repitió el gate transversal sobre las cuatro correcciones: **2.020
  Python + 199 JavaScript PASS** (12 grupos),
  `/tmp/odyssey-c4-post-audit-final-gate-20261023.log`. Las correcciones son
  posteriores al SHA auditado y **no heredan sus veredictos**.
- Pendientes de aceptación: revisión de las correcciones, autorización
  explícita para desplegar un SHA nuevo en DEV con backup/rollback y pruebas
  user-driven desde Chromium **autenticado** con n8n, Luna y Core/E3 reales,
  incluyendo errores sin evidencia de cero y de escritura parcial; medir
  recursos/latencia con proveedor real y no tocar datos personales ni PROD.
  **APP E2E NOT VERIFIED para C4.**
