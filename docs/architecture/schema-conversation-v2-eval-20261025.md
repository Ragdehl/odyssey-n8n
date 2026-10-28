# V2: evaluación real controlada del asistente de esquema — 25-10-2026

**Evidencia observada con el proveedor real, pero NO aceptación semántica ni de despliegue.** Se usó la matriz congelada V1 como regresión del prompt V2, con mensajes totalmente sintéticos y un registro temporal. Ningún vault personal/DEV/PROD, Markdown ni confirmación fue tocado.

- **Configuración:** `gpt-6-luna`, `low`, strict Responses JSON, `store=False`, timeout 30 s, sin herramientas, sin reintentos. Cuatro unidades efímeras systemd protegidas, seis llamadas por tanda (24 llamadas).
- **Hash V2 probado:** `c0322c9bbaa6fb234c54ab67cdd97f54532fe61280ec10079bd96a9f11ef06c2`.
- **Hash del JSON Schema:** `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- **Coincidencia solo de decisión:** **20/24 (83,3 %)**, mejor que las 17/24 coincidencias V1 (70,8 %). **No equivale a 20 propuestas correctas**, porque también deben comprobarse tipo destino, propiedades y semántica. Cuatro casos no coincidentes, uno de ellos rechazado por el validador.
- **Tokens reales reportados:** 35.613 de entrada, 4.531 de salida (40.144 en total). Mediana de latencia 2.71 s, máximo 5.30 s; no es estimación de latencia p95 ni de importe facturado.
- **Confidencialidad:** las respuestas JSON originales están en `/tmp/schema-v2-real-batch{0,6,12,18}-20261025.json` del Pi (permisos 0600) y proceden solo de prompts sintéticos. Este documento conserva decisiones y discrepancias sin tokens ni credenciales.

| Caso | Esperado | Decisión V2 | Etiqueta coincide |
|---|---|---|---|
| `es_new_simple` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `es_new_existing_duplicate` | `REUSE` | `REUSE` | ✅ |
| `es_property_existing` | `ADD_PROPERTY` | `ADD_PROPERTY` | ✅ |
| `fr_new` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `fr_reuse` | `REUSE` | `REUSE` | ✅ |
| `fr_ambiguous_property` | `CLARIFY` | `CLARIFY` | ✅ |
| `en_new` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `en_existing` | `REUSE` | `CLARIFY` | ❌ |
| `es_fact_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_task_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_calendar_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_partial_date` | `CLARIFY` | `ADD_PROPERTY` | ❌ |
| `es_known_full_date` | `ADD_PROPERTY` | `ADD_PROPERTY` | ✅ |
| `es_unknown_attribute` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_negative` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_conditional` | `CLARIFY` | `CLARIFY` | ✅ |
| `fr_multiple_targets` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_app_owned` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_same_word_twice` | `CLARIFY` | `INVALID` | ❌ |
| `fr_property_generic` | `ADD_PROPERTY` | `ADD_PROPERTY` | ✅ |
| `es_too_broad` | `CLARIFY` | `ABSTAIN` | ❌ |
| `en_attack` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_correction` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `es_unique_attribute` | `CLARIFY` | `CLARIFY` | ✅ |

## Análisis de los cuatro fallos

- **`en_existing` — REUSE esperado / CLARIFY recibido:** el modelo reconoció que Project ya existe pero preguntó qué diferencia justificaría duplicarlo. Es una decisión prudente, pero menos útil que recomendar reutilizar el tipo idéntico cuando no se aporta ninguna distinción.
- **`es_partial_date` — CLARIFY esperado / ADD_PROPERTY recibido:** propuso un campo `integer` para «año de nacimiento». Aunque un número entero sea técnicamente válido, **cambia la semántica de una fecha parcial sin soporte específico**. Es un bloqueo real; la V3 no puede activarse por pasar tests de formato.
- **`es_same_word_twice` — CLARIFY esperado / INVALID recibido:** la respuesta real hacía una pregunta útil para precisar qué libros prestados excluir, pero acompañada de una cita `libros` que aparece dos veces. El parser la rechazó por unicidad. En V3 se ignora esa cita auxiliar solo en CLARIFY/ABSTAIN; para propuestas y reutilización la cita única continúa siendo obligatoria.
- **`es_too_broad` — CLARIFY esperado / ABSTAIN recibido:** «Organízame todo mejor» es una solicitud vaga en el editor de esquemas, así que conviene preguntar qué quiere organizar en vez de no ofrecer continuidad.

## Prompt V3 posterior (histórico): evaluado, NO aprobado

- **Hash V3 actual no probado:** `18daa35c99fb72764a88cc2325c3049348eec811dad705052aad720a1a08e92e`.
- V3 explicita reutilización de tipos equivalentes incluso cuando se pide otra copia, prohibición de sustituir fechas parciales por enteros/texto y aclaración ante peticiones genéricas. El validador ignora citas no decisorias de CLARIFY/ABSTAIN sin permitir referencias sin evidencia en una propuesta mutadora.
- Nota histórica previa a la campaña V3: las pruebas SDK simuladas y del validador no acreditaban comportamiento real. **Actualización:** V3 ya fue evaluada con 24 regresiones, 12 holdout y 4 repeticiones dentro de un presupuesto posterior autorizado, y sigue NO aprobada; véase el informe V3.
- **Condiciones pendientes actuales:** reparar bloqueos semánticos del contrato, autorizar y evaluar V4, revisar los cambios completos, después aceptación Chromium→n8n→Core/Notas en un vault de prueba. Flags DEV y confirmación continúan desactivados; PROD intacto.

**Actualización posterior:** V3 fue evaluado sobre esta regresión y 12 casos holdout, con cuatro repeticiones; [informe V3 real](schema-conversation-v3-live-eval-20261025.md). No extrapolar ninguna puntuación a la semántica ni activar la funcionalidad.
