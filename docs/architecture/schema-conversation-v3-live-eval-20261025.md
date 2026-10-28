# Odyssey: evaluación real V3 — 25 de octubre de 2026

**40/40 llamadas autorizadas**, modelo `gpt-6-luna`/`low`, JSON estricto, sin herramientas, `store=False`, sin reintentos, sobre frases sintéticas y registros temporales. Sin notas, confirmaciones ni despliegues.

Prompt SHA256 `18daa35c99fb72764a88cc2325c3049348eec811dad705052aad720a1a08e92e`. Tokens: 64894 entrada + 6706 salida = 71600. Mediana de latencia 2.583 s. Importe facturado no disponible.

| Cohorte | Coincidencias de operación | Total |
|---|---:|---:|
| Regresión | 22 | 24 |
| Holdout | 9 | 12 |
| Repeticiones | 2 | 4 |
| **TOTAL** | **33** | **40** |

**Coincidencia de operación NO equivale a éxito semántico.** Una respuesta rechazada (`INVALID`) entre las primeras 36; otras propuestas pasaron formato pero no criterio semántico.

## Riesgos observados

- **BLOQUEANTE ISBN:** `es_unique_attribute` crea un campo ISBN sobre `document` en dos intentos, sin demostrar que Document sea el tipo correcto de los libros anteriores.
- **BLOQUEANTE exclusión:** `es_exclusion` fue `INVALID` por cita en la primera pasada y `ADD_TYPE` en la repetición, pretendiendo aplicar exclusión de plantas laborales mediante una simple descripción del tipo. El esquema no ejecuta ese filtro.
- `fr_reuse`: ABSTAIN frente a REUSE, luego REUSE correcto; inestabilidad en francés.
- `fr_new_specific`: CLARIFY la unidad de duración en vez de crear Film; pregunta prudente.
- `en_future_conditional`: ABSTAIN ante hipótesis futura, segura aunque esperada CLARIFY.
- `es_new_simple`: tipo «Libro leído» estrecha «libros que leo»; revisar identidad de tipo.
- `es_correction`: altura se propone como string; revisar medición/unidades.

## Decisiones individuales

| Cohorte | Caso | Esperado | Observado | Coincide |
|---|---|---|---|---|
| regresión | `es_new_simple` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regresión | `es_new_existing_duplicate` | `REUSE` | `REUSE` | sí |
| regresión | `es_property_existing` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regresión | `fr_new` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regresión | `fr_reuse` | `REUSE` | `ABSTAIN` | NO |
| regresión | `fr_ambiguous_property` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `en_new` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regresión | `en_existing` | `REUSE` | `REUSE` | sí |
| regresión | `es_fact_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regresión | `es_task_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regresión | `es_calendar_not_schema` | `ABSTAIN` | `ABSTAIN` | sí |
| regresión | `es_partial_date` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `es_known_full_date` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regresión | `es_unknown_attribute` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `es_negative` | `ABSTAIN` | `ABSTAIN` | sí |
| regresión | `es_conditional` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `fr_multiple_targets` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `es_app_owned` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `es_same_word_twice` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `fr_property_generic` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| regresión | `es_too_broad` | `CLARIFY` | `CLARIFY` | sí |
| regresión | `en_attack` | `ABSTAIN` | `ABSTAIN` | sí |
| regresión | `es_correction` | `ADD_TYPE` | `ADD_TYPE` | sí |
| regresión | `es_unique_attribute` | `CLARIFY` | `ADD_PROPERTY` | NO |
| holdout | `es_new_specific` | `ADD_TYPE` | `ADD_TYPE` | sí |
| holdout | `fr_new_specific` | `ADD_TYPE` | `CLARIFY` | NO |
| holdout | `en_new_specific` | `ADD_TYPE` | `ADD_TYPE` | sí |
| holdout | `fr_person_property` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| holdout | `es_unknown_existing` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `en_future_conditional` | `CLARIFY` | `ABSTAIN` | NO |
| holdout | `fr_negation` | `ABSTAIN` | `ABSTAIN` | sí |
| holdout | `es_both_changes` | `CLARIFY` | `CLARIFY` | sí |
| holdout | `en_fact_only` | `ABSTAIN` | `ABSTAIN` | sí |
| holdout | `es_exclusion` | `CLARIFY` | `INVALID` | NO |
| holdout | `es_date_complete` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| holdout | `fr_partial_birth` | `CLARIFY` | `CLARIFY` | sí |
| repetición | `es_partial_date` | `CLARIFY` | `CLARIFY` | sí |
| repetición | `fr_reuse` | `REUSE` | `REUSE` | sí |
| repetición | `es_unique_attribute` | `CLARIFY` | `ADD_PROPERTY` | NO |
| repetición | `es_exclusion` | `CLARIFY` | `ADD_TYPE` | NO |

## Decisión

**V3 NO APROBADA; flags DEV apagadas.** La propuesta puede ser estructuralmente válida y seguir siendo semánticamente incorrecta. Los casos de reserva no se reetiquetan. Los JSON de respuesta están en diez archivos `/tmp/schema-v3-authorized-*-20261025.json` del Pi, con permisos 0600; no se incluyen credenciales ni datos personales.

Próximo contrato V4: resolver equivalencia/granularidad real de tipos y restricciones no representables; sin heurísticas específicas para libros o plantas. Necesita otra evaluación real autorizada y posterior prueba E2E desde la app. **V4 no evaluada.**
