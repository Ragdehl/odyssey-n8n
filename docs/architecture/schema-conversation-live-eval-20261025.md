# Evaluación real controlada: conversación del modelo de notas — 25 oct 2026

## Evidencia del prompt original V1

Esta campaña fue **real con el proveedor**, usando exclusivamente 24 frases **sintéticas** de `tests/fixtures/schema_suggestion/evaluation_v1.json` y un `UserSchemaRegistry` temporal desechable. Ejecutada por cuatro unidades efímeras systemd que leen la fuente de credenciales protegida sin imprimirla; sin llamadas a los vaults DEV/PROD ni mutación de Markdown, sin `schema_confirm`, sin despliegue ni cambios de notas.

- **Modelo efectivo:** `gpt-6-luna`, razonamiento `low`, `store=False`, JSON estricto, `max_output_tokens=1200`, `max_retries=0`, timeout 30 segundos. Un intento por caso, 24 llamadas en cuatro tandas consecutivas de seis.
- **Prompt SHA256 V1 probado:** `229a3f2e2072bb6c20a198ffc38318406218f7a4057b9d7b833898fc358ce085`.
- **Schema SHA256 V1 probado:** `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- **Resultado V1, NO APROBADO:** **17/24 coincidencias de etiqueta de operación** (70,8 %), **NO 17/24 propuestas semánticamente correctas**. Las otras siete respuestas fueron cinco rechazos del contrato y dos elecciones `REUSE` incompatibles con la intención esperada. Incluso entre las 17 etiquetas coincidentes puede haber propiedades o tipos incorrectos: hace falta revisar contenido, destino y atributos de cada propuesta. No reinterpretar rechazos como aciertos.
- **Tokens reportados por API:** 32.301 de entrada, 3.923 de salida (**36.224** en total). Mediana de latencia por caso **2.98 s**, máxima **10.85 s**; las cifras son de muestra pequeña, no un p95 de producción. No se dispone del importe facturado para esta campaña.

| Caso | Etiqueta esperada | Etiqueta recibida | ¿Coinciden las etiquetas? |
|---|---|---|---|
| `es_new_simple` | `ADD_TYPE` | `REUSE` | ❌ |
| `es_new_existing_duplicate` | `REUSE` | `REUSE` | ✅ |
| `es_property_existing` | `ADD_PROPERTY` | `INVALID` | ❌ |
| `fr_new` | `ADD_TYPE` | `INVALID` | ❌ |
| `fr_reuse` | `REUSE` | `INVALID` | ❌ |
| `fr_ambiguous_property` | `CLARIFY` | `CLARIFY` | ✅ |
| `en_new` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `en_existing` | `REUSE` | `REUSE` | ✅ |
| `es_fact_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_task_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_calendar_not_schema` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_partial_date` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_known_full_date` | `ADD_PROPERTY` | `INVALID` | ❌ |
| `es_unknown_attribute` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_negative` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_conditional` | `CLARIFY` | `CLARIFY` | ✅ |
| `fr_multiple_targets` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_app_owned` | `CLARIFY` | `CLARIFY` | ✅ |
| `es_same_word_twice` | `CLARIFY` | `REUSE` | ❌ |
| `fr_property_generic` | `ADD_PROPERTY` | `ADD_PROPERTY` | ✅ |
| `es_too_broad` | `CLARIFY` | `CLARIFY` | ✅ |
| `en_attack` | `ABSTAIN` | `ABSTAIN` | ✅ |
| `es_correction` | `ADD_TYPE` | `ADD_TYPE` | ✅ |
| `es_unique_attribute` | `CLARIFY` | `INVALID` | ❌ |

## Diagnóstico sin inventar causas

- `es_new_simple` y `es_same_word_twice`: el modelo eligió el tipo genérico `document` para libros; el primero exige un tipo propio y el segundo preservación de una restricción que la propuesta no puede expresar. Este es un **fallo semántico**, no de estructura JSON.
- `es_unique_attribute`: el modelo devolvió `ADD_PROPERTY` para `document` ante una petición de ISBN de «mis libros ya existentes»; ese target no está suficientemente demostrado. Además, el validador V1 rechazó un `description=null` en `ADD_PROPERTY`. Un formato reparado no convierte esta inferencia errónea en correcta. La decisión esperada sigue siendo `CLARIFY`.
- `es_property_existing`, `fr_new`, `fr_reuse`, `es_known_full_date`: el runner V1 no retenía todavía la salida exacta rechazada, así que **no se puede demostrar el motivo individual**. Se registran como errores no diagnosticados, sin afirmar que la reparación cubra los cuatro.
- El intérprete sigue **apagado por defecto** y no está listo para usuarios. Dos aprobaciones separadas (propuesta humana y flag DEV) no compensan falta de semántica válida.

## Corrección V2 (histórico del prompt, ya evaluada posteriormente)

Se cambia lo mínimo justificable: `ADD_PROPERTY` lleva `description=null` para el **tipo** y descripción obligatoria en su **propiedad**; se rechaza un intento de cambiar el texto del tipo por esa vía. Se aclara que `REUSE` requiere identidad semántica y granularidad equivalente, nunca solo pertenencia a una categoría general. Se pide `CLARIFY` ante posibles referentes existentes no identificados y exclusiones que el formato no pueda representar. Se mantienen citas exactas, abstención y Core CAS sin autoridad de escritura.

- **Prompt SHA256 V2:** `c0322c9bbaa6fb234c54ab67cdd97f54532fe61280ec10079bd96a9f11ef06c2`. El JSON schema del modelo es el mismo: `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- Casos de V1 **sin cambiar su respuesta esperada**, 12 nuevos casos *holdout* en `tests/fixtures/schema_suggestion/evaluation_v2_holdout.json`. Congelados antes de nuevas pruebas reales. No contabilizar suites deterministas o el replay de respuestas V1 como éxito de V2.
- **Auditoría del evaluador:** revisión independiente del primer script encontró un P1 de puntuación: comparar solo operaciones puede ocultar destinos/propiedades incorrectos. Queda corregido: en futuras campañas `decision_match_count` nunca equivale a `semantic_pass_count`; todas las salidas del modelo se marcan `awaiting_independent_review` hasta comprobar semánticamente el resultado. También se bloquea sobrescritura de archivos antes de consumir tokens, se admite CLI directo y las matrices están en una lista permitida. La puntuación histórica V1 se conserva únicamente como coincidencia de etiquetas; los cambios del evaluador NO recalculan ni mejoran sus resultados.
- **Resultado posterior V2:** se ejecutaron 24 llamadas reales sobre exactamente este hash, **20/24 coincidencias de decisión**, cuatro discrepancias, ninguna certificación semántica completa ni aceptación. Evidencia y casos: [V2 live evaluation](schema-conversation-v2-eval-20261025.md). El holdout permanece sin probar; la V3 preparada después tampoco tiene evaluación en vivo. El E2E Chromium queda condicionado a una evaluación semántica satisfactoria.
