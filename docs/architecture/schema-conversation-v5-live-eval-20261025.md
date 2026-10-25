# Odyssey — evaluación real V5 (25 octubre 2026)

**V5 NO APROBADA semánticamente.** Campaña autorizada y completada de **24/24 llamadas** a `gpt-6-luna` (esfuerzo `low`, JSON estricto, `store=False`, timeout 30s, salida máxima 1200 tokens, sin retries y sin herramientas). Solo frases sintéticas, `UserSchemaRegistry` temporal, sin tocar notas, usuarios, DEV, PROD o confirmar ningún cambio.

- Prompt SHA256 exacto: `c34023593fb021384013e77c862afee580e8dc04795f4b65b46b8ae423bb3ca4`.
- Schema SHA256 (invariado): `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- Tokens reales: **53,508 entrada + 4,053 salida = 57,561 total**. Latencia mediana 4.058s, máxima 14.987s. Importe facturado no disponible.
- Evidencia fuente: seis JSON sintéticos 0600 en `/tmp/schema-v5-real-{holdout,regression}-*-20261025.json` del Pi; no subir tokens ni credenciales al repo.

## Etiquetas de decisión, NO éxito del contenido

| Cohorte | Aceptadas | Llamadas | Rechazos de esquema |
|---|---:|---:|---:|
| 12 holdout nuevos V5 | **11** | 12 | 0 |
| 12 regresiones seleccionadas de V1 (estrictas) | **11** | 12 | 0 |
| **TOTAL** | **22/24 (91,7%)** | **24** | **0** |

La segunda discrepancia de etiqueta (`es_conditional`: esperado `CLARIFY`, observado `ABSTAIN`) es **segura y coherente con V5**, pero se conserva el criterio histórico de V1, no se reetiqueta a posteriori. La única discrepancia sustancial de ruta es `en_new_guitars`: `CLARIFY` innecesaria. La tasa de decisiones seguras puede ser mayor, pero **no es una tasa demostrada de éxito semántico**.

## Revisión del contenido completo

- **Bloqueante para aceptar V5:** `en_new_guitars` leyó “guitars and their brands” como posible orden de crear dos tipos («guitarras» y «marcas»), en vez de una ficha Guitarra con atributo Marca. Preguntó innecesariamente y perdió el flujo claro. No hubo mutación, pero incumple la intención.
- **Bloqueante de tipificación:** `es_new_board_games` generó «Juego de mesa» y el campo «Número de jugadores» correctamente anclados, pero asignó `value_type=string` en vez de `integer`. El contrato necesita conservar cardinalidad numérica sin fabricar una unidad.
- **Idioma:** `en_people_reuse_details` respondió con explicación en español pese a una solicitud íntegramente inglesa, aunque eligió `REUSE person`. V5 NO resuelve consistentemente la deriva de idioma.
- **Fecha parcial:** `es_partial_date` eligió `CLARIFY`, sin crear campos, pero preguntó si guardar el año natal como entero «aunque no sea un campo de fecha». Esa alternativa pierde las semánticas temporales que se habían decidido preservar. El soporte de fechas parciales continúa pendiente.
- **Regresión histórica de carácter hipotético:** `es_conditional` devolvió `ABSTAIN` en lugar de `CLARIFY`, respuesta no mutadora aceptable según V5. Conservar marcador histórico V1 como no coincidencia.
- **Puntos sólidos:** `fr_reuse` y los tres nuevos casos de personas `REUSE` reconocen `person`, sin propiedades inventadas; `es_unique_attribute` pide el tipo registrado antes de asignar ISBN; `fr_exclusions` pide aclaración sobre filtro que el esquema no implementa; `es_new_simple` propone `Libro` con autor texto y páginas entero en español. Las hipótesis futuras del holdout se abstienen sin preguntas ni acciones.
- **Otros matices:** `es_correction` guarda altura como texto, opción conservadora porque no se expresó unidad; no debe presentarse como dimensión numérica fiable. Los campos de dominio de un tipo son todos opcionales y filtrables, sin re-clasificar notas antiguas.

## Registro de las 24 decisiones sin cambiar expectativas

| Cohorte | Caso | Esperado | Obtenido | Coincide |
|---|---|---|---|---|
| v5_holdout | `es_new_board_games` | `ADD_TYPE` | `ADD_TYPE` | sí |
| v5_holdout | `fr_new_paintings` | `ADD_TYPE` | `ADD_TYPE` | sí |
| v5_holdout | `en_new_guitars` | `ADD_TYPE` | `CLARIFY` | **no** |
| v5_holdout | `fr_people_reuse_details` | `REUSE` | `REUSE` | sí |
| v5_holdout | `es_people_reuse_details` | `REUSE` | `REUSE` | sí |
| v5_holdout | `en_people_reuse_details` | `REUSE` | `REUSE` | sí |
| v5_holdout | `fr_missing_property` | `CLARIFY` | `CLARIFY` | sí |
| v5_holdout | `en_hypothetical_future` | `CLARIFY` | `ABSTAIN` | sí |
| v5_holdout | `es_hypothetical_future` | `CLARIFY` | `ABSTAIN` | sí |
| v5_holdout | `fr_exclusions` | `CLARIFY` | `CLARIFY` | sí |
| v5_holdout | `en_broad_documents` | `CLARIFY` | `CLARIFY` | sí |
| v5_holdout | `es_non_schema_fact` | `ABSTAIN` | `ABSTAIN` | sí |
| v1 | `es_new_simple` | `ADD_TYPE` | `ADD_TYPE` | sí |
| v1 | `es_new_existing_duplicate` | `REUSE` | `REUSE` | sí |
| v1 | `es_property_existing` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| v1 | `fr_new` | `ADD_TYPE` | `ADD_TYPE` | sí |
| v1 | `fr_reuse` | `REUSE` | `REUSE` | sí |
| v1 | `fr_ambiguous_property` | `CLARIFY` | `CLARIFY` | sí |
| v1 | `es_partial_date` | `CLARIFY` | `CLARIFY` | sí |
| v1 | `es_known_full_date` | `ADD_PROPERTY` | `ADD_PROPERTY` | sí |
| v1 | `es_conditional` | `CLARIFY` | `ABSTAIN` | **no** |
| v1 | `fr_multiple_targets` | `CLARIFY` | `CLARIFY` | sí |
| v1 | `es_correction` | `ADD_TYPE` | `ADD_TYPE` | sí |
| v1 | `es_unique_attribute` | `CLARIFY` | `CLARIFY` | sí |

## Decisión de producto

**No activar V5.** La misma llamada que acierta la operación puede equivocarse en idioma o propiedad. Se requiere un contrato posterior V6 que distinga nombres de entidades y atributos ligados por posesión, respete cardinalidad y evite convertir fechas parciales en enteros, además de fortalecer la concordancia idiomática. No crear reglas especiales para guitarras o juegos de mesa; no inventar un segundo clasificador o backfill especulativo.

**V6 no probada con el modelo real**. La autorización de 24 llamadas ha quedado agotada. Antes de habilitar, necesitan revisión semántica independiente y campaña de coste acotado, seguida de prueba desde la aplicación Chromium/n8n/Core en un vault sintético. Ambos flags de activación permanecen apagados.
