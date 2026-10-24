# C4 — explicación segura de fallos a partir de recibos verificados

**Estado real (24-10-2026):** C4 está desplegado **solo en DEV** en
`75404428e085b70b3dbce0c29a972b50af3a9bb3`, junto con C3;
`ODYSSEY_CHAT_C4_ENABLED=1` funciona únicamente cuando
`ODYSSEY_DEPLOYMENT_ENV=DEV`. La fuente puede ir por delante del marcador
DEV; PROD no se ha modificado. **APP E2E NOT VERIFIED** globalmente:
la orientación de identidad sí pasó browser real, pero falta un parcial C4
natural desde el servicio desplegado y autenticación externa completa.

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
- **Aprobación de despliegue DEV recibida** y adopción real del commit inmutable
  `a75685252c666609d0f2b9f3880ec357c2d87753`. C4 activo solo en
  el servicio DEV por `c4-chat.conf` con `ODYSSEY_CHAT_C4_ENABLED=1`, C3
  sigue activo, sin cambios en PROD. El estado anterior y el volumen de n8n
  están respaldados con `tar` y **SHA256** en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-dev-adoption-20261023/`;
  rollback `ae281d1bd53b048b5a5f192c8bf4657b1a399cb8`.
- **Aceptación interna desde Chromium con frontend desplegado, n8n real, Core/E3
  real y actor DEV sintético**, enviando texto con el formulario y el botón:
  - **C3 regresión:** «Hola, Odyssey. ¿Qué tal estás?» → respuesta social
    legible, persistida tras recarga, sin notas nuevas; ~10,6 s observados.
  - **C4 caso real:** iniciar una sesión para la tarea inexistente
    `C4NoExisteEnsayo231026` → **`needs_attention`**, Core
    `WORK_SESSION_TASK_UNRESOLVED`, `product_outcome=CANNOT_ANSWER`,
    `write_evidence=UNKNOWN`, `SPECIFY_IDENTITY/ASK_USER`. La UI respondió:
    «No puedo confirmar todavía qué parte de la solicitud se ha guardado.
    ¿Puedes indicar el nombre o identificador del elemento al que te refieres?»;
    visible tras recarga. Duración total del envío ~41,6 s. El recibo persistido
    contiene 0 IDs afectados, pero **eso no prueba cero escrituras**.
  - **Aclaración normal** de una solicitud para enviar un correo sin cuenta
    conectada: `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`, outcome `CLARIFY`,
    **sin C4**. La UI pidió precisar el ámbito; ~17,6 s. Una solicitud mixta
    (crear tarea sintética y empezar sesión de otra tarea inexistente) también
    fue `CLARIFY` **antes de guardar**, no `partial`; ~42,6 s.
  - En las tres campañas **166 notas Markdown antes y después**, cero nuevas;
    chat/error/clarificación visibles tras reload. Evidencias
    `real-c4-user-browser-01.log`, `real-c4-user-browser-unsupported.log`,
    `real-c4-user-browser-mixed.log` y capturas en el directorio del ensayo.
  - Gate de UI de solo lectura móvil+escritorio sobre ese mismo marker:
    **PASS**; 16 paneles de detalles renderizados con SVG en el perfil de
    escritorio, cero duplicados visuales o advertencias legacy; mutaciones
    por el proxy de solo lectura rechazadas HTTP 403.
- **Límites y siguiente paso:** prueba desde **frontend DEV real servido por
  un proxy local protegido por cookie**, sin validar la sesión pública de
  Cloudflare Access desde un dispositivo externo. El modelo real/n8n forman
  parte del runtime desplegado, pero una orientación C4 podría haber usado su
  fallback determinista si Luna falló. **No se pudo inducir desde UI un fallo
  parcial después de alguna escritura, ni se certificó desde UI un reenvío
  literal con el mismo request ID**; ambos están comprobados solo por pruebas
  de contrato y E3 aislado. Tampoco hay nueva auditoría de los cuatro
  revisores sobre `a756852`. Las latencias observadas (10,6–42,6 s) son altas:
  falta un presupuesto medido por etapa y concurrencia con el proveedor real.
  **C4 funcional en DEV en el caso de identidad, APP E2E NOT VERIFIED como
  aceptación global.** Ningún dato personal ni PROD fue modificado.

## Verificaciones suplementarias de DEV (23-10-2026, mismo SHA)

Se mantiene desplegado **`a75685252c666609d0f2b9f3880ec357c2d87753`**;
no ha habido redespliegue ni cambio de código ni de credenciales.

- **Replay real por la misma ruta desplegada:** se partió de un mensaje
  sintético **ya tecleado y enviado anteriormente desde Chromium** (error
  `WORK_SESSION_TASK_UNRESOLVED`, `needs_attention`). Una solicitud diagnóstica
  posterior a n8n DEV con **idéntico texto, conversation_id y request_id**
  respondió HTTP 200 en **910 ms** con la misma orientación y texto. El
  SHA256 byte a byte del recibo E3 actor-bound permaneció igual y los 166
  archivos Markdown conservaron las mismas rutas. Esto verifica el replay
  técnico desplegado, **no un botón de reintento de la UI**: la segunda
  entrega se envió por HTTP como test complementario. Log
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-dev-adoption-20261023/c4-replay-diagnostic.log`.
- **Frontera pública anónima:** HEAD/GET sin cookies ni credenciales sobre
  `https://odyssey-dev.ragdehl.com/`, `/api/odyssey` y `/api/request`
  obtuvieron **403 de Cloudflare**. No demuestra por sí solo que la regla
  responsable sea Cloudflare Access; sin una sesión de prueba externa
  autorizada no es posible certificar el recorrido autenticado, aún pendiente.
  No se modificó ninguna regla, token ni permiso de Cloudflare.
- **Casos parciales históricos:** el actor de DEV tiene **6 recibos previos
  `partial` con IDs afectados**; cuatro de ellos `CANNOT_ANSWER`. Estos
  recibos son anteriores a C4 y no contienen `error_guidance`; no sirven como
  demostración del renderizado C4 de un parcial nuevo. Uno provenía de una
  solicitud sintética con 3 hechos calendáricos y otro de 4 hechos.
- **Nueva variante de 3 hechos desde Chromium:** fue **completed / ANSWER**,
  3 acciones y 3 IDs afectados; mostró «Guardado» y tardó **38,8 s**. El
  contador de Markdown permaneció en 166 porque Core **actualizó** los días
  DEV `2026-10-12`, `2026-10-13` y `2026-10-14` (operaciones `UPDATED` y
  `REFERENCE_BOUND`), añadiendo tres etiquetas de ensayo que empiezan por
  `C4Parcial`. Estos cambios son **reales y sintéticos**, no ausencia de
  escritura: los recibos son la autoridad, no el contador de archivos.
- **Variante de 4 hechos desde Chromium:** generó
  `needs_attention / CLARIFY`, código
  `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`, sin ID afectado y sin
  `error_guidance`, en **37,9 s**. No escribió ninguno de los cuatro hechos
  sintéticos. Ambas variantes sobreviven a reload; la falta de parcial
  confirma que **no se puede garantizar un fallo parcial mediante frases
  diseñadas para un reproducer antiguo**. Se detienen las pruebas
  exploratorias de escritura para evitar acumulación de notas.
- **Lectura móvil adicional:** la UI y su marker cargaron HTTP 200;
  scroll de historial y recarga no alteraron **ni un byte del vault** (SHA256
  agregado idéntico con 166 notas). Los recibos parciales históricos no
  aparecieron en la página de conversación reciente, por lo que tampoco se
  declara visualmente aceptada esa ruta. Evidencias de navegador y
  recibos originales en el directorio de ensayo citado arriba.
- **Rendimiento observado:** fallo C4 de referencia ~41,6 s en navegador
  versus ~27,6 s de ejecución registrada por Core; el tramo
  `tasks.work_session_resolution` consumió ~12,2 s. La variante de tres
  actualizaciones consumió ~23,35 s de Core y ~38,8 s desde el navegador.
  Esto **no** identifica una única causa ni separa completamente clasificación
  C1, bloqueo serializado, n8n, modelo y presentación. Se necesita una traza
  de etapas con marcas coherentes para medir el sobrecoste de C4. No se
  cambió la arquitectura de concurrencia ni se eliminó Luna.

**Situación:** caso C4 real de identidad y replay desplegado comprobados,
frontera anónima de Cloudflare comprobada; **APP E2E NOT VERIFIED** como
aceptación completa hasta poder verificar escritura parcial post-C4,
reintento iniciado desde UI si existe ese affordance y autenticación externa
real. PROD y datos personales sin tocar.

## Reproductor aislado de parcial post-escritura (23-10-2026)

- En `tests/runtime/test_c4_isolated_partial_real_core.py` se reutiliza el
  escenario **general F14**, con respuestas auténticas grabadas del proveedor
  en `benchmarks/application_router/hybrid_remaining_diag_20261013/F14.json`;
  la llamada al proveedor **NO** se repite. El Core/Writer real procesa el
  texto sin cambios en un **vault temporal nuevo** con notas sintéticas.
- Se induce solo en el proceso pytest una excepción del **readback posterior
  a la mutación**. El primer hecho queda físicamente persistido en Markdown,
  el dependiente se bloquea y Core devuelve `partial / CANNOT_ANSWER`, un ID
  afectado `date:2026-10-03` y una etapa fallida
  `candidate.postwrite_verification`. **No se ha modificado código Core para
  introducir un interruptor de errores**, ni DEV habitual o PROD.
- RuntimeComposition consume el resultado real por el guard E3 actor-scoped,
  proyecta C4 `status=partial`, `write_evidence=SOME` y orientación
  `UNKNOWN / EXPLAIN` para la causa no reconocida (no inventa diagnóstico).
  `scripts/odyssey_c4_isolated_route_renderer.mjs` ejecuta el **routeCode
  verdadero** de n8n extraído de la fuente y valida su respuesta con
  `odyssey_web/client.js`: estado `partial`, mensaje «ha guardado parte de
  la información», nota afectada disponible en snapshot, **sin prometer que
  toda la solicitud se completó** ni permitir reintento automático.
- Se reenvía el mismo request ID sobre **el mismo runtime y almacén E3
  aislados**. `delivery_replayed=true`, el escritor y las llamadas congeladas
  del modelo siguen con **una única ejecución**, el Markdown original no
  cambia y no se añade otro hecho. El test está incluido en el gate
  transversal `conversation_front_door_contract`; pytest focalizado PASS.
  **Gate global ejecutado tras el cambio: 2.021 Python + 199 JavaScript PASS,
  12 grupos**, artefactos `/tmp/odyssey-c4-isolated-partial-global-20261023.json`
  y `.log`. La presentación con la causa `UNKNOWN_FAILURE` usa la plantilla
  de causa desconocida de C4, sin inventar «reformular» ni una causa temporal.
- Límite explícito: aunque este test une **Core físico → E3 → C4 → n8n JS
  auténtico → validador del navegador**, usa proveedor histórico/fijado y no
  navega por una sesión real de Chromium con n8n desplegado. Por tanto,
  **NO sustituye una aceptación E2E pública de un parcial C4 natural**.
  Las aclaraciones `partial / CLARIFY` legítimas siguen siendo competencia
  de Core y no se reetiquetan artificialmente como error C4.

## Optimización de la interpretación C4 (24-10-2026, desplegada en DEV)

- **Problema medido:** para una causa **conocida y verificada por Core**, la
  tabla `odyssey_runtime/conversation_error.py::_REASON_KIND` ya fija de manera
  inequívoca `guidance_kind/hint`, y `workflows/odyssey-online.ts` valida la
  misma relación. Antes, además se llamaba a `OpenAIConversationGateway.explain_error`
  **dentro del bloqueo de ejecución**, aunque la salida del modelo solo podía
  coincidir con esa tabla o descartarse. El proveedor añadía latencia y coste
  sin poder cambiar la presentación autorizada.
- **Solución sin modificar semántica ni prompt:** `RuntimeComposition` mantiene
  `conversation_error_guidance_enabled` y separa de él
  `conversation_error_model_advisory_enabled=False`. El camino normal devuelve
  la misma interpretación cerrada directamente tras validar el recibo Core;
  **cero llamadas adicionales a Luna por C4**. Se conserva el modo de
  comprobación por modelo con
  `ODYSSEY_CHAT_C4_MODEL_ADVISORY_ENABLED=1`, pero solo cuando además están
  activos **C3 y C4** y `ODYSSEY_DEPLOYMENT_ENV=DEV`; C4 por sí solo sigue
  dando orientación determinista, sin activar inadvertidamente C3. Incluso
  en el diagnóstico, un consejo diferente de la
  categoría verificada se descarta y jamás autoriza guardar o reintentar.
  C1/C2/C3, el Planner y las llamadas de resolución de identidades no cambian.
- **Verificación:** prueba aislada actor-scoped/E3 con `partial`, `SOME` y
  modelo espía: orientación exacta y replay idéntico tanto con modo normal
  (0 llamadas a `explain_error`) como con diagnóstico opt-in (1 llamada,
  resultado malicioso ignorado, 0 en replay). Reproductor Raspberry
  `python -m scripts.odyssey_chat_c4_perf_gate` contra el mismo runtime con
  proveedor **simulado** de retardo fijo 180 ms: mediana **2,1 ms**,
  p95 (nearest rank) **5,0 ms**, cero llamadas al proveedor; con
  `--model-advisory`: mediana **182,4 ms**, p95 **546,2 ms**, siete llamadas.
  Los p95 incluyen tres solicitudes solapadas y bloqueo serializado. Archivos
  `/tmp/odyssey-c4-optimized-default-perf.json` y
  `/tmp/odyssey-c4-optimized-advisory-perf.json`. No son medidas con Luna real;
  la anterior campaña de seis errores con Luna (1,4–8,4 s observados)
  permite estimar el coste evitado por C4, no una ganancia total garantizada.
- **WorkSession:** se conserva `resolve_existing_entity` sin shortcuts ni
  umbrales nuevos. La etapa DEV real `tasks.work_session_resolution` costó
  ~12,2 s, pero incluye búsqueda exacta, semántica y posible decisión
  contextual; los recibos no desglosan esa etapa. No está demostrado qué
  subpaso domina y es **incorrecto reducir candidatos o saltarse el
  razonamiento contextual** sin verificar identidad y ambigüedad. El siguiente
  análisis debe desglosarla en vault sintético con instrumentación acotada y
  comparar exact, sin candidatos, candidatos ambiguos y resultado positivo.
- **WorkSession, perfilado seguro adicional:** `/tmp/odyssey_work_session_safe_profile_20261024.json`
  desglosa cuatro caminos del mismo resolver genérico sobre notas exclusivamente
  sintéticas, indexador fake y contextualizador fake con retraso impuesto de
  180 ms. Resultado: identidad exacta ~0,82 ms / **0 llamadas contextuales**;
  sin candidatos ~0,14 ms / **0 llamadas contextuales**; candidato semántico
  ~181,35 ms / **1 llamada contextual simulada**; ambigüedad de alias
  ~183,32 ms / **1 llamada contextual simulada**. La búsqueda exacta y
  semántica local fue submilisegundo **solo en estas fixtures**; no permite
  atribuir los 12,2 s observados en DEV a Luna porque el indexador y el
  modelo reales no estaban cargados. Se conserva la decisión contextual para
  evitar confusiones entre entidades. Perfil de producción sin privados y
  sin escrituras todavía pendiente.
- **Revisión independiente del commit `add3814`** detectó un defecto
  de adopción (P2): activar diagnóstico C4 sin C3 marcaba el modo como
  habilitado, pero no había gateway. En vez de crear uno nuevo que pudiera
  activar C3 inesperadamente, ahora el opt-in exige también C3. Las seis
  combinaciones relevantes de DEV/PROD/C3/C4 se verifican en pruebas.
  Resultado de revisión: **hallazgo corregido**, no una aprobación de los
  cuatro auditores sobre este nuevo commit.
- **Gate transversal de código corregido:** **2.029 Python + 199 JavaScript PASS**,
  12 grupos; `/tmp/odyssey-c4-opt-reviewed-gate-20261024.json` y `.log`.
- **Adopción en DEV (24-10-2026):** `75404428e085b70b3dbce0c29a972b50af3a9bb3`
  desplegado solo en DEV por el procedimiento existente, tras CI independiente
  **PASS** (`40032888073`), segunda revisión independiente sin nuevos hallazgos,
  backup SHA256 del estado/notas (~2,3 MB) y n8n (~113 MB), rollback conservado
  en `a75685252c666609d0f2b9f3880ec357c2d87753`. Frontend, runtime,
  marcador y n8n coinciden; DEV y PROD health HTTP 200. Ninguna configuración
  de red, credenciales o PROD fue modificada.
- **Chromium con aplicación DEV auténtica (proxy local de prueba actor-bound,
  NO Cloudflare Access externo):** un usuario sintético envió por el formulario
  una instrucción para iniciar WorkSession sobre una tarea inexistente
  `C4EnsayoRapidez241026`. Fue **`needs_attention`** con
  `WORK_SESSION_TASK_UNRESOLVED`, `CANNOT_ANSWER`, `write_evidence=UNKNOWN`,
  `SPECIFY_IDENTITY/ASK_USER`; el navegador mostró la explicación esperada y
  la recuperó tras recargar. Runtime/n8n y modelo de clasificación reales,
  sin segunda llamada Luna por C4 (`MODEL_ADVISORY` desactivado).
  **37,890 ms observados** desde el envío en Chromium, frente a **41,649 ms**
  de la muestra anterior; los mensajes, historia y carga difieren, de modo
  que **NO es un A/B controlado ni acredita un ahorro fijo de 3,8 s**.
  El recibo de Core registró **22.747 ms** frente a ~27.600 ms históricos;
  `tasks.work_session_resolution` tardó **8.851 ms** frente a 12.184 ms
  anteriores, por lo que **WorkSession sigue siendo el cuello de botella**.
  Las tres advertencias genéricas del proxy de ensayo aparecieron también
  en la prueba anterior; la prueba de UI terminó PASS, sin errores JS,
  pero no se atribuye ni se ignora ese ruido sin más diagnóstico.
- **Integridad:** SHA256 combinado del contenido de **166 Markdown** idéntico
  antes del despliegue, antes del navegador y después del navegador; ninguna
  mutación accidental. Copias y resultados en
  `/home/ragdehl/projects/.odyssey-agent-runs/c4-optimized-dev-adoption-20261024/`;
  logs `deploy.log`, `optimized-browser-e2e.log`, `backup-sha256`, huellas de
  vault y captura de Chromium. RAM disponible ~1,5 GiB, swap usado ~738 MiB,
  temperatura ~48,5 °C (instantánea posterior, no pico).
- **Pendientes:** el resultado aislado de `partial / SOME` sigue probado por
  Core físico, E3, n8n JS y browser-validator, pero NO en Chromium público
  sobre un fallo parcial natural con Luna real; sesión Cloudflare Access
  externa autenticada, trazas detalladas de WorkSession y **aprobación formal
  de los cuatro auditores sobre el SHA desplegado** siguen pendientes.
  **No promover a PROD.**

## Diagnóstico seguro de WorkSession (24-10-2026, SOLO FUENTE)

La aceptación DEV de `7540442` mostró `tasks.work_session_resolution` a
**8.851 ms**, con otra muestra de **12.184 ms** y resoluciones de otras tareas
sintéticas en **23, 59 y 61 ms**. Estos tiempos son etapas completas, no
una separación de consulta local, embedding y razonador contextual. No está
justificado saltar la validación semántica ni fijar un umbral de confianza.

- Core `resolve_existing_entity` admite ahora un `SpanRecorder` opcional que
  mide `exact_lookup`, `semantic_search` (incluye embedding e índice),
  `candidate_validation`, `relationship_context`, `provider_evidence`,
  `contextual_provider` y `decision_validation`. El resolvedor conserva
  íntegramente su selección, candidatos, límites, respuesta y excepciones.
  Cada subetapa registra **nombre cerrado, estado, desplazamiento temporal y
  duración**; ante una excepción marca el span fallido sin ocultar la causa.
  No registra texto fuente, títulos, IDs, puntuaciones, contenido de candidatos,
  prompt, respuesta del modelo ni credenciales.
- La composición de Tasks lo inserta **solo** si
  `ODYSSEY_DEPLOYMENT_ENV=DEV` **y**
  `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED=1`. No hay llamadas extra
  a proveedor, escrituras nuevas ni cambios de reglas de identidad. Las
  mediciones cuelgan de la etapa original como **substeps nativos**; no se
  duplican los milisegundos en el tiempo total, el donut ni las coberturas.
  PROD no puede activarlo por una única bandera.
- Regresiones con notas de personas y tareas **sintéticas**: coincidencia
  exacta sin consulta semántica, ausencia de candidatos sin razonador,
  candidato semántico con resolución contextual, fallo de proveedor que
  sigue propagándose, nombres fijos, aislamiento de la proyección, conservación
  de `OperationalEvidence.total_duration_ms` y cobertura de intervalos anidados.
  Una revisión independiente detectó que se usaba inicialmente el reloj global
  en vez del reloj inyectado del `SpanRecorder`; corregido y cubierto con
  un reloj determinista que verifica offsets, tiempos y etapa fallida.
  Se añaden al gate transversal de Work Sessions; no requieren IA de pago.
  Gate global tras la corrección: **2.051 Python + 199 JavaScript PASS**, 12
  grupos (`/tmp/odyssey-worksession-reviewfixed-gate-20261024.json` y `.log`).
  La segunda revisión independiente del diff con la corrección del reloj
  terminó **sin hallazgos accionables**; no sustituye la futura auditoría
  formal de los cuatro roles de la etapa completa.
- **Estado final 24-10-2026:** instrumentación de `7cade85566d536f32abf74075aa186e41d9479e1`
  **desplegada solo en DEV**, revisada y CI `40067639565` aprobado.
  Bandera `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED=1` **habilitada
  solamente durante las dos pruebas** y después retirada con reinicio de
  runtime, salud DEV/n8n/PROD HTTP 200. No se modificaron reglas de identidad,
  modelo, prompt ni configuración de PROD. **No promover a PROD.**

### Aceptación desde la app y aislamiento del arranque en frío (24-10-2026)

- **Precondiciones:** fuente limpia fijada en `7cade85`, gate transversal
  **2.051 Python + 199 JavaScript PASS**, CI GitHub `40067639565` success,
  revisión independiente detectó fallo de reloj inyectable y su segunda
  revisión tras corregirlo no tuvo hallazgos accionables. Antes de desplegar,
  se detuvieron solo servicios DEV y se guardaron **backups verificados SHA256**
  del vault/state (~2,3 MB) y volumen de n8n (~113 MB) en
  `/home/ragdehl/projects/.odyssey-agent-runs/worksession-timing-dev-adoption-20261024/`.
  **Rollback**: `75404428e085b70b3dbce0c29a972b50af3a9bb3`.
- **Prueba usuario real desde Chromium ARM64 móvil → app desplegada → n8n
  auténtico → proveedor → Core/E3 → recibo → navegador y recarga** usando
  una petición sintética de WorkSession sobre una tarea inexistente,
  sin autorizar su creación. Proxy localhost restringido con cookie de prueba;
  **no** se probó autenticación pública Cloudflare Access. Dos ejecuciones
  secuenciales con IDs nuevos, ambas `needs_attention`, código
  `WORK_SESSION_TASK_UNRESOLVED`, `write_evidence=UNKNOWN`, consejo
  `SPECIFY_IDENTITY/ASK_USER`, UI correspondiente y recuperación tras recarga.
  El contenido **de los 166 Markdown fue idéntico antes/después/tras retirar
  la bandera**, comprobado con SHA256. Los logs del proxy conservaron 2–3
  avisos de peticiones canceladas; no invalidaron la aceptación del flujo.
- **Recibo en frío** (primera llamada sin proceso ONNX previamente cargado):
  Chromium **44.803 ms**; Core **30.038 ms**; WorkSession **17.473 ms**.
  Subetapas: `exact_lookup` 67,5 ms; `semantic_search` **14.957,4 ms**;
  `candidate_validation` 1,3 ms; `relationship_context` 403,0 ms;
  `provider_evidence` 1,4 ms; `contextual_provider` 2.042,2 ms.
  Cobertura de intervalos WorkSession 99,997 %.
- **Recibo en caliente** (mismo runtime, proceso de embeddings local activo;
  nueva petición autenticada de prueba): Chromium **28.111 ms**;
  Core **21.161 ms**; WorkSession **1.992 ms**. Subetapas:
  `exact_lookup` 102,0 ms; `semantic_search` **153,3 ms**;
  `candidate_validation` 1,4 ms; `relationship_context` 402,9 ms;
  `provider_evidence` 1,6 ms; `contextual_provider` 1.330,2 ms.
  Cobertura de intervalos 99,964 %.
- **Interpretación y límite importante:** `ODYSSEY_EMBEDDING_SUBPROCESS=1`
  y `ODYSSEY_EMBEDDING_IDLE_SECONDS=900` ejecutan FastEmbed en un proceso
  local reutilizable. El proxy de pruebas **ignoraba `presence`**, por lo
  que la primera solicitud cargó el worker de embeddings bajo demanda, y la
  segunda reutilizó el worker caliente. `semantic_search` incluye IPC,
  posible carga del modelo, cálculo de embedding y consulta SQLite: los datos
  **sugieren fuertemente** arranque en frío como factor dominante, pero no
  separan esos subcostes ni prueban el precalentamiento normal de una pestaña
  autenticada externa. No usar una comparación de dos solicitudes como p95.
  No se eliminan llamadas contextuales ni se altera selección de candidatos.
- **Cierre seguro:** tras ambos tests se retiró el drop-in temporal de
  `ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED`, se recargó systemd y
  reinició solo runtime DEV. La comprobación inmediata coincidió con un
  instante de arranque (socket aún no listo); comprobación posterior: runtime,
  n8n y PROD **HTTP 200**, source/marker DEV `7cade85`, drop-in ausente y
  flags de unidad sin diagnóstico, backup SHA256 válido, notas inmutadas.
  No se desplegó ningún cambio en PROD.
- **Siguiente prioridad:** investigar los costes de Core restantes y medir
  el precalentamiento en una sesión Cloudflare Access externa autorizada. Las
  verificaciones con proxy local, tiempos de worker y SQLite se documentan a
  continuación; no autorizan por sí solas un cambio en RAM, TTL o modelo.

### Verificación real del precalentamiento sin escrituras (24-10-2026)

**La funcionalidad ya existía; no se necesitó código nuevo ni redespliegue.**
En el marcador DEV `7cade85566d536f32abf74075aa186e41d9479e1` y con
`ODYSSEY_EMBEDDING_SUBPROCESS=1`, el frontend `odyssey_web/app.js` carga
asíncronamente `presence.js`, que avisa `active` al abrir y `inactive` al
cerrar la pestaña. El workflow `odyssey-online.ts` autentica y reenvía a
`/conversation/presence`; `RuntimeComposition.embedding_presence` solo lo
acepta en DEV y delega al adaptador aislado de ONNX. En una sesión normal el
primer aviso no debe bloquear la hidratación ni autorizar escrituras.

- **Chromium móvil, frontend desplegado real, n8n y runtime reales:** un proxy
  localhost con **cookie de prueba** limitó las operaciones a `presence` y
  una lectura de conversación; **no permitió `/api/request` ni mutaciones**.
  La sesión abrió el Chat y emitió `active` a los **129 ms**, con HTTP 200 y
  `{ok:true}` de n8n/runtime; el proceso worker apareció a los **496 ms**.
  Su RSS alcanzó **~651 MB** a los **5.547 ms**. Tras cerrar la pestaña,
  llegó `inactive` con HTTP 200 a los **5.555 ms**. Que el RSS creciera no
  significa por sí solo que ONNX estuviera listo exactamente en ese instante.
  `externalCloudflareAuth=false`: **no** se certificó autenticación pública
  desde Internet. Hubo un aviso del proxy de prueba de una petición auxiliar,
  sin incidencia sobre las dos respuestas de presencia. La prueba no envió
  ningún mensaje al modelo y no modificó Markdown.
- **Medición local, solo entradas sintéticas, modelo cacheado offline:**
  creación de `FastEmbedTextEmbedder` **4.398 ms**; primer
  `embed_queries` **86 ms**, segundo/tercero **23 ms**; lectura SQLite de las
  **31 filas del índice de tareas** **6,8 ms** y cálculo vectorial sobre
  estas filas **1 ms**. Dos consultas completas en índice ya caliente
  ~**22 ms**. Estas medidas no son del recorrido browser→Core.
- **Worker aislado real, nueva instancia, sin proveedor ni índices privados:**
  arranque + precalentamiento mediante el protocolo privado `warm`:
  **4.624 ms**; primera inferencia una vez listo: **73 ms**, segunda **68 ms**.
  En ninguno de estos tests se hizo descarga de modelos ni llamadas externas;
  el modelo se cargó de la caché local en un proceso descartable. No se
  imprimieron IDs, títulos, candidatos o textos de notas.
- **Interpretación:** el efecto **frío 14.957 ms vs caliente 153 ms** en la
  etapa `semantic_search` de WorkSession está bien sustentado. La construcción
  del modelo y del proceso explica varios segundos; **no se puede atribuir
  cada uno de los otros segundos** sin un perfil conjunto bajo idénticas
  condiciones de carga, caché, memoria y concurrencia. Tampoco se ha probado
  que el cliente conectado por Cloudflare tenga el mismo tiempo de prewarm
  que el proxy de prueba. La latencia de la aplicación sigue teniendo
  otros tramos relevantes aun con ONNX caliente.
- **Retención y cierre:** `idle_seconds=900` mantiene el worker cargado hasta
  el plazo de gracia después de la última sesión. Las pruebas con worker
  sintético confirman `heartbeat`, `inactive`, expiración de pestañas perdidas
  y liberación del proceso al vencer el periodo de inactividad; esta prueba
  de navegador **no esperó 900 segundos** para verificar el reaper real.
  No se cambió el TTL ni se volvió permanente el uso de ~650 MB.
- **Evidencias:**
  `/home/ragdehl/projects/.odyssey-agent-runs/worksession-timing-dev-adoption-20261024/dev-presence-browser-acceptance.log`,
  `benchmark-onnx-readonly.log`, `benchmark-worker-warmup.log`, con scripts
  transitorios fuera del Git. Los SHA256 combinados de los **166 Markdown**
  permanecieron idénticos en ambos ensayos. DEV y PROD no han sido
  modificados, ni se han cambiado tokens o permisos.
