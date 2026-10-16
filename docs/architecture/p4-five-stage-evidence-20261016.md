# P4 — Cinco frentes de estabilización, pruebas y bloqueos (16 octubre 2026)

**Autoridad:** El estado vigente sigue en `docs/architecture/functional-roadmap.md`. Este documento conserva evidencia y contratos verificables. Se realizaron cambios exclusivamente en la rama `feat/light-router-poc-20261016` sobre copias aisladas del vault. No se modificaron Notes de usuario, PROD, DEV, workflow instalado ni historial personal.

## 1. Estabilidad del Router y validaciones de Core

- Modificado el contrato general del **Router ligero**: distingue ahora Task CREATE, estados, consultas, relaciones PARENT_TASK y **Work Session** start/stop/edit/registro de actividad; un progreso descrito dentro de una Work Session pertenece a Tasks, no debe crear automáticamente otro hecho de Core. El `self_relation_span` es una sugerencia no vinculante, no un ID ni un hecho.
- Reformulado el revisor independiente **Task CREATE mixto**: distingue crear una obligación nueva de modificar una Task existente, editar una sesión o registrar actividad en ella. Una obligación no necesita contener literalmente la palabra «tarea». El revisor no penaliza otros hechos `record` legítimos de Core y mantiene dos booleans de veto separados más cita completa exacta. No se ha añadido branch por nombre, frase o idioma.
- Batería con **modelos frescos** de Router + auditor + intérprete real Tasks en diez fuentes sintéticas (`scripts/p4_product_taskonly_intent_live.py`): **10/10** (`START_WORK_SESSION`, `STOP_WORK_SESSION`, `EDIT_WORK_SESSION`, `ADD_WORK_SESSION_ACTIVITY`, Task CREATE con PARENT_TASK, COMPLETE, REOPEN, QUERY, Work Session de subtarea, actividad fechada). Previo a aclarar Router: **8/10**, fallaban precisamente actividades Work Session clasificadas como Core. La prueba es **read-only en Tasks**, NO una escritura e2e con GPT.
- Batería de peticiones mixtas con modelos frescos (original + varias sondas): auditor de Task CREATE tras ajuste aceptó las cuatro revisiones de una tanda, pero el revisor general/Planner aún bloqueó **1/4** en esa tanda. La sonda de categoría `WholeMessageCoverageError` reveló que el plan traía `unresolved_count=1` (mientras todos los hechos propuestos coincidían en cardinalidad y referencia): Core debe **bloquear**, no borrar arbitrariamente incertidumbre de pronombre/identidad. No hay garantía de estabilidad longitudinal para mensajes mixtos.
- P4 sigue utilizando `whole_message_coverage`, la prueba de SELF, identidad canónica, compilador Core, preflight y Writer. Los cinco validadores estrechos históricos siguen confinados; ver `p4-validator-boundary-audit-20261016.md`.

## 2. E2, relaciones colectivas, Tasks y chat/UI

- **SELF/relaciones:** Router puede proponer una frase colectiva exacta del mensaje original, sin identidades. Core llama a `verify_self_relationship` para rederivar miembros únicamente desde un **hecho Markdown actual del SELF autenticado**. Solo sus nombres entran como contexto al Planner/revisor; `validate_whole_message_coverage` recibe el conjunto de miembros verificados. Core revalida `recheck_self_relationship` al acabar el análisis y **antes de CADA subescritura**. Miembros ausentes, frase inventada, relación desactualizada o cambiado el SELF → `needs_attention`/parcial, nunca identidades inventadas. El mecanismo no contiene una lista fija de hijos o alias; vale para una relación que cumpla el contrato Core.
- Test en `tests/runtime/test_p4_verified_group_e2.py`: dos personas existentes, backlink en Day, ningún contacto nuevo, replay; relación no demostrada sin cambios; mutación de SELF simulada mientras el modelo revisa → veto prewrite. **IA REAL** en `scripts/p4_product_verified_group_live.py`: `Mis hijos comieron helado hoy` y SELF canónico con dos miembros sintéticos → **completed**, enlaces a ambos y replay correcto. Sin datos de la familia real del usuario.
- Test `test_p4_taskonly_real_session_parity.py`: Task-only entra por nuevo Router/scope E2, ejecuta exactamente el `TaskWorkSessionService` canónico, luego la superficie `/notes` modifica/cierra misma Work Session, conservando E3.
- Test `test_p4_chat_to_ui_http_flow.py`: `POST /execute` Chat P4 → ejecución domain real → `POST /notes` detalle, actividad, stop por **HTTP real en localhost**, respuesta E3 replay y una sola Session física. Router y scope tienen outputs congelados; no se ha afirmado que este test use GPT, n8n o navegador.
- **Bloqueador actual:** Work Session o Task UPDATE mezclada con varios hechos Core **no** tiene aún una representación de operación E2 autoritativa y un gate E3 de composición completo; la ruta se abstiene, no finge Task CREATE. Subtareas Chat pasan reconocimiento GPT y la ruta Tasks-only legacy; todavía falta mostrar el *Chat GPT real → subtarea Markdown → navegador* completo.

## 3. E3, fallos y reintentos

- `LocalDeliveryResultStore.inspect_mutation_claim(request_id,fingerprint)` realiza una inspección **read-only** sin devolver fuente, huellas, IDs canónicos ni respuestas. Estados: `unseen`, `unresolved_attempt` (claim sin recibo; no reejecutar), `receipt_confirmed_with_stale_claim` (recibo validado; replay autorizado), `receipt_confirmed`. Comprueba formato, actor-scoping físico, fingerprint exacto, formato/sha de recibo y claim; no crea directorios ni levanta/reanuda writes. Tests: archivo ausente, claim pendiente, hash conflictivo, corrupción, caída entre recibo y cleanup, inspección sin side effects.
- **No existe** reconciliación automática segura si un crash ocurre después de crear hechos y antes del recibo: el claim pre-LMM no contiene manifest de los N hechos ya revisados, por lo que **no se puede declarar `completed` ni liberar el claim** sin una prueba independiente. Seguir bloqueando reintento automático; la futura reconciliación requiere un manifest E3 persistido antes del primer write y readback canónico exacto.

## 4. Rendimiento Raspberry y caché segura

- Perfil real con `cProfile` sobre 250 Notes sintéticas: en una sola petición `execute_request` + P4 hubo ~8.337 llamadas a `VaultRepository.read_text`, ~8.086 `parse_note`, 32 `list_markdown_paths`; `temporal._assert_unique_day_identity` fue invocado 9 veces, además de búsquedas repetidas de SELF, colisiones y `create_entity`. El **coste O(N) del Core sigue siendo el mayor problema**. No proviene solo de indexación completa.
- Nuevo `odyssey_core.notes.scoped_note_decode_cache()`, **opt-in únicamente desde P4**: `ContextVar` independiente por hilo/actor y petición, máximo 1024 Markdown y 1 MB de bytes. Solo reutiliza el análisis para contenido RAW **byte-idéntico** ya leído desde el vault físico, devolviendo copia profunda de metadatos cada vez; cambios de archivo generan una clave diferente y no se sirven Notes antiguas. La caché se descarta al finalizar la petición. Tests de aislar metadatos mutables, bytes cambiados, Markdown malformado, tres actores/hilos paralelos. No almacena datos en disco, no admite rutas/IDs como autoridad.
- Bench `scripts/p4_product_scale_isolated.py` con refresh incremental (1, cero full rebuild), ConstantEmbedder y sin GPT:

  | Notes sintéticas | Antes | Con caché | Mejora aproximada |
  |---:|---:|---:|---:|
  | 20 | 130 ms | 105 ms | 19 % |
  | 250 | 1.330 ms | 1.043 ms | 22 % |
  | 1000 | 5.230 ms | 4.100 ms | 22 % |

  Métricas de la Pi, /tmp/odyssey-p4-scoped-cache-performance.log. No es el p95 de la app, no incluye GPU/CPU de FastEmbed real, llamadas GPT, n8n ni DOM; **4,1 s con 1000 Notes aún es bloqueo de rendimiento**. Próxima optimización: E2/batched canonical identity inventory para evitar docenas de escaneos Core sin cachear identidades stale; nunca saltar preflight por rendimiento.

## 5. Gate de producto, alcance real de E2E

- Tests nuevos añadidos a `scripts/odyssey_cross_surface_gate.py`, reutilizable en CI: E2 grupos, Tasks-only chat/UI, HTTP chat→UI, E3 forensics, caché aislada y precaución sobre operaciones mixtas. El gate offline anterior estaba en 574 Python/168 Node; el resultado actual se registra en Functional Roadmap y `/tmp/odyssey-p4-five-stage-gate.log`.
- Webhooks `/execute` y `/notes` funcionan en pruebas TCP locales con runtime, Writer y Markdown reales; el modelo productivo real se ejerció en baterías HTTP aisladas previas. UI JS y workflow mapeado siguen cubiertos por tests Node/estáticos.
- La Raspberry **no dispone de Chromium/Firefox ni runtime Playwright/Puppeteer** para comprobar navegador real; el host tiene n8n operativo de DEV y PROD, pero no se ha iniciado otra instancia que pudiera consumir su escasa memoria y swap. Tampoco se ha modificado el n8n instalado ni conectado un browser externo al vault. **Por tanto NO se ha realizado todavía el E2E exigido navegador autenticado → n8n real → GPT → Markdown → n8n → navegador**, ni se ha verificado visualmente donut/gráfico/persistencia después de salir y volver. Mantener `real_full_product_e2e=false`.

## Decisión de seguridad y siguiente puerta

P4 sigue **desactivada por defecto**. DEV queda en `1474681`, PROD intacto. No elevar a pruebas manuales hasta demostrar la ruta completa en un sandbox con navegador/n8n y cuentas aisladas, cierre de Work Session + Core mixto y subtareas en chat, reconciliación probada de caídas, menos falsos rechazos de GPT y rendimiento aceptable con embeddings reales. No hay que volver a pedir al usuario que apruebe cada paso de pruebas sobre fixtures; nunca usar su vault ni hacer deploy implícito.
