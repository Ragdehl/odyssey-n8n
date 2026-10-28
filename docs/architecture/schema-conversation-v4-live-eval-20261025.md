# Odyssey — evaluación real V4 (25 octubre 2026)

**Experimento terminado, todavía NO aceptación de producto.** Se gastaron exactamente 40/40 llamadas autorizadas a `gpt-6-luna` (`low`, JSON estricto, `store=False`, sin tools/retries, timeout 30 s, salida máxima de 1.200 tokens), exclusivamente en textos sintéticos contra registros de esquema desechables. Sin modificar vault, DEV, PROD, notas ni confirmaciones.

- Prompt SHA256: `b52def8fca2037d1260aac595b8b10d9fd8db756b254c3c0a7369e26dad5bd2a`.
- JSON Schema SHA256 sin modificar: `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- Evidencias: ocho archivos del Pi `/tmp/schema-v4-real-{holdout,regression}-XX-20261025.json`, modo 0600, cada uno con entradas sintéticas y respuesta completa. No contienen claves; la prueba de regresión reutiliza casos ya conocidos y **no cuenta como holdout independiente**.
- Tokens medidos por proveedor: **77425 entrada + 6550 salida = 83975 totales**. Mediana 2.771 s, máximo 5.753 s. Importe facturado no disponible.

## Puntuación de etiqueta (NO de semántica completa)

| Muestra | Llamadas | Etiquetas correctas | Rechazos |
|---|---:|---:|---:|
| 16 casos nuevos holdout V4 | 16 | **16/16** | 0 |
| 24 casos conocidos de regresión V1 | 24 | **23/24** | 0 |
| **Total** | **40** | **39/40 (97,5 %)** | **0** |

La única discrepancia de etiqueta fue `fr_reuse`: ante «Je veux enregistrer des détails sur les personnes que je connais», la respuesta `CLARIFY` preguntó por los detalles concretos, en vez de recomendar reutilizar directamente `person`. No es una propuesta de escritura incorrecta, pero dificulta el recorrido.

## Inspección semántica de las propuestas y aclaraciones

- **Bloqueantes de V3 que no reaparecieron en esta muestra:** `es_unique_attribute` ahora pregunta dónde están guardados los libros, en lugar de adjuntar ISBN a `document`; los ejemplos de exclusión (`es_exclude_work_vehicles`, `fr_exclude_gifts`, `en_paid_invoices_only`, `es_same_word_twice`) piden aclaración y reconocen que la descripción no filtra por sí misma. El caso nuevo `es_existing_containers` tampoco atribuye `receta` al tipo genérico `document` por defecto.
- **Inspección de atributos:** el tipo `Novela` contiene género (`string`) y capítulos (`integer`); `Vinyl Record` declara número de catálogo (`string`); `Persona` añade idioma materno (`string`); `Aquarium` propone volumen sin inventar una unidad (`string`). Se conservaron los destinatarios canónicos declarados cuando el usuario los especificó.
- **Idioma incorrecto, visible al usuario (NO aprobado):** `en_paid_invoices_only` recibe pregunta y explicación en francés pese al mensaje inglés. `fr_reuse` recibe pregunta y explicación en español pese al mensaje francés. `es_new_simple` propone el tipo `Book` en inglés pese al mensaje español. La etiqueta estructural no detecta esta deriva.
- **Intención hipotética, matiz pendiente:** `es_future_conditional` elige `CLARIFY`, pero pregunta qué tipo de notas de buceo organizar, sin verificar primero si el usuario realmente solicita definir el esquema ahora.
- **Precisión de fechas:** `es_partial_date` elige `CLARIFY`, pero ofrece guardar el año como texto como posible salida; no se ha aprobado como modelo parcial estructurado. No se creó propiedad ni fecha inventada.
- `es_correction` propone `Planta` con `altura` tipo texto por falta de unidades; no fabrica centímetros, aunque queda pendiente decidir una estrategia de mediciones generales.

### Decisiones individuales congeladas

| Cohorte | ID del escenario | Esperado | Obtenido | Etiqueta |
|---|---|---|---|---|
| holdout | `es_existing_cameras_unknown_type` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `fr_existing_dogs_unknown_type` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `en_existing_cars_unknown_type` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `es_explicit_people_property` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| holdout | `fr_explicit_people_reuse` | `REUSE` | `REUSE` | sí |
| holdout | `en_new_music_collection` | `ADD_TYPE` | `ADD_TYPE` | sí |
| holdout | `es_exclude_work_vehicles` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `fr_exclude_gifts` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `en_paid_invoices_only` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `es_future_conditional` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `en_fact_not_model` | `ABSTAIN` | `ABSTAIN` | sí |
| holdout | `fr_explicit_negation` | `ABSTAIN` | `ABSTAIN` | sí |
| holdout | `es_generic_books_are_not_documents` | `ADD_TYPE` | `ADD_TYPE` | sí |
| holdout | `fr_optional_measurement_unit` | `ADD_TYPE` | `ADD_TYPE` | sí |
| holdout | `en_multi_change` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `es_existing_containers` | `CLARIFY` | `CLARIFY` | sí |
| regression | `es_new_simple` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regression | `es_new_existing_duplicate` | `REUSE` | `REUSE` | sí |
| regression | `es_property_existing` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regression | `fr_new` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regression | `fr_reuse` | `REUSE` | `CLARIFY` | **NO** |
| regression | `fr_ambiguous_property` | `CLARIFY` | `CLARIFY` | sí |
| regression | `en_new` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regression | `en_existing` | `REUSE` | `REUSE` | sí |
| regression | `es_fact_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regression | `es_task_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regression | `es_calendar_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regression | `es_partial_date` | `CLARIFY` | `CLARIFY` | sí |
| regression | `es_known_full_date` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regression | `es_unknown_attribute` | `CLARIFY` | `CLARIFY` | sí |
| regression | `es_negative` | `ABSTAIN` | `ABSTAIN` | sí |
| regression | `es_conditional` | `CLARIFY` | `CLARIFY` | sí |
| regression | `fr_multiple_targets` | `CLARIFY` | `CLARIFY` | sí |
| regression | `es_app_owned` | `CLARIFY` | `CLARIFY` | sí |
| regression | `es_same_word_twice` | `CLARIFY` | `CLARIFY` | sí |
| regression | `fr_property_generic` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regression | `es_too_broad` | `CLARIFY` | `CLARIFY` | sí |
| regression | `en_attack` | `ABSTAIN` | `ABSTAIN` | sí |
| regression | `es_correction` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regression | `es_unique_attribute` | `CLARIFY` | `CLARIFY` | sí |

## Decisión y continuación

**No se activa el asistente.** V4 ha superado por primera vez los 16 casos nuevos en etiqueta y la mejora de identidad/alcance es real en esta muestra. Sin embargo, no hay puntuación automatizada de verdad semántica y tres fallos de idioma más una pregunta hipotética imprecisa. La frontera de autorización sigue intacta; mostrar la vista previa y exigir clic humano no exime de validar el comportamiento real en la app.

**Siguiente paso sin gastar llamadas nuevas:** reforzar consistencia idiomática y temporal en un contrato posterior, añadir criterios semánticos específicos *sin* parches por ejemplo, verificar el flujo app desde navegador usando vault sintético cuando el gate semántico sea aceptable. La V4 ejecutada queda ligada a su hash exacto y las matrices permanecen congeladas; cualquier edición del prompt crea una versión nueva no evaluada.

**Presupuesto:** gastado por completo (40 llamadas). No hay autorización residual para una nueva campaña.
