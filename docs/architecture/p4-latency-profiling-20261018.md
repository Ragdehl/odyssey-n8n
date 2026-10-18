# Odyssey — perfil P4 de diez mensajes (18-10-2026)

## Medición antes de optimizar

Ruta real autenticada navegador → n8n → GPT → Core → Markdown, 10 peticiones sintéticas con IDs únicos en DEV. Datos JSON privados en /tmp/odyssey-p4-dev-live-p4lat26oct18-NOMBRE.json, resumen /tmp/odyssey-p4-latency-suite-results.log.

| Caso | Estado | Runtime (s) | Core writer (s) | Receipts |
|---|---|---:|---:|---:|
| simple | completed | 15.64 | 0.27 | 1 |
| yo implícito + persona nueva | completed | 31.17 | 4.31 | 2 |
| dos fechas | completed | 26.53 | 0.43 | 2 |
| N:M, cuatro personas | completed | 74.82 | 45.69 | 5 |
| pronombre | completed | 30.61 | 3.09 | 2 |
| corrección | needs_attention | 19.67 | 0 | 0 |
| negación | needs_attention | 14.90 | 0 | 0 |
| persona conocida | needs_attention | 25.33 | 0 | 0 |
| referencia conocida | completed | 24.86 | 0.32 | 1 |
| dos Tasks | needs_attention | 16.20 | 0 | 0 |

No se atribuyen como correctos los casos pendientes. Estos receipts no prueban por sí solos la visualización de todas las aristas del grafo.

En la nota simple: Router 2.66s, Planner 2.76s, coverage 2.40s, speakers A+B paralelos ~1.72s, escritura física ~0.27s. GPT domina.

Hallazgo crítico en N:M: action.write tarda 45.69s, pero los 5 materialize de Markdown suman ~0.15s. El preflight de Core consume 45.4s mediante CUATRO consultas consecutivas GPT de contextual_resolution de 1.97s / 23.02s / 1.67s / 14.40s, con 7514 / 10412 / 8092 / 8149 tokens de entrada. La lentitud no la causan embeddings almacenados ni SQLite. Hay que reducir las llamadas contextuales redundantes y estudiar resoluciones de identidades independientes en paralelo con snapshots verificados, sin permitir identidades inventadas ni bypass de CAS. Aún no implementado.

## Optimización preparada en rama, solo DEV

WholeSourceLightExecutor.parallel_coverage_speaker_reviews: después del Planner con hechos completos sin ambigüedad manifiesta, coverage y los dos revisores de sujeto A/B se ejecutan en paralelo con el MISMO input, todos antes de escribir. No se elimina ningún dictamen ni verificación. validate_whole_message_coverage, identidad_collision, validate_dual_speaker_review y Core Writer se mantienen obligatorios. SpanRecorder autenticado se recoge por hilo y se fusiona al terminar, sin copiar datos privados. Una cobertura rechazada puede consumir consultas speaker innecesarias: restringido a planes sin unresolved y hechos estructuralmente válidos; reversible en DEV y nunca habilitado en PROD.

Pruebas focales con retrasos simulados verifican solapamiento efectivo, cinco provider calls, self-link persistido, y rechazo seguro sin escritura ante speaker incorrecto: 30 tests PASS. Gate transversal completo 964 Python +174 JavaScript PASS.

Pendiente: commit y deploy DEV, E2E y comparar traza real. Prioridad siguiente: eliminar espera serial de Core por identidad con seguridad demostrada; analizar los casos needs_attention y enlaces/UI sin arreglos de ejemplo.

## Segunda optimización validada en pruebas (todavía sin deploy DEV)

Se ha preparado un cambio opt-in en Core, con `parallel_write_target_decisions` exclusivamente conectado desde el coordinador P4 en DEV; el resto de superficies mantiene el comportamiento secuencial. En un WriteAction de 2–8 unidades ordinarias independientes (sin relación explícita, reference-only, set completo, ni aclaración en curso), Core ejecuta `decide_write_target` en un pool de hasta 4 hilos **solo en fase de lectura**. Cada hilo recibe un reasoner `OpenAIContextualReasoner.fork_for_parallel_read()` independiente (mismo modelo, esfuerzo, timeout, calibración, salida), un wrapper de embeddings con spans propios; `_ProviderCallRecorder` usa lock para guardar metadatos de llamadas sin mezcla ni pérdida. El modelo ONNX hijo del runtime maneja las consultas en su propio serializador seguro. El Writer sigue siendo único y secuencial.

El contrato comprueba `repository.note_version_snapshot()` global antes y después de resolver. Si un archivo externo cambia, la preparación aborta; ninguna identidad nueva ni nota se materializa. Solo después de terminar **todas** las decisiones pasa por `_materialize_decision` secuencial y asigna identificadores/paths en el orden original, evitando colisiones y preservando targets/referencias, validators, readback y CAS. Si el provider no permite fork o el shape de relación no es elegible, camino secuencial antiguo sin cambios. No se paraleliza una escritura ni una ruta dependent Task.

Tests nuevos `tests/core/test_reference_preflight_parallel.py`: 4 decisiones retrasadas 160ms que arrancan casi simultáneamente y tardan menos del 55% del secuencial, identidades asignadas exactamente en el orden de referencia, cero Markdown escritos en preflight; mutación externa produce `ReferencePreflightError` y ninguna escritura; reasoner no forkable usa el camino secuencial. 60 pruebas focales de preflight/P4 PASS, gate completo **964 Python +174 JS PASS**. Los 4 GPT consecutivos observados en N:M (1.97+23.02+1.67+14.40s) **son el beneficio potencial**, pero NO se debe prometer eliminación de esos ~40s sin una captura real post-deploy.

Primer cambio P4, `7d7ffa2`, ya desplegado DEV: coverage y revisores A/B se solapan tras plan. E2E adicionales: simple `p4opt26oct18-simple` completed 16.02s runtime; persona conocida `p4opt26oct18-implicit` completed 18.53s runtime, los tres reviews parten en el mismo offset; `p4opt26oct18-nm` ended needs_attention 17.27s **sin escribir** y no constituye prueba de mayor rapidez. Son ejemplos diferentes de la línea de base y contienen variabilidad de GPT; no afirmar ahorro causal salvo solapamiento medido.

SQLite context graph en DEV: `date:2026-10-11` posee enlaces a Irene, Leo, Nadia, Pablo y SELF; dates 08,12,17 también enlazan a SELF. Se han comprobado mediante SELECT de `note_links`, no todavía UI navegada tras último deploy. La primera prueba del endpoint de UI durante redeploy devolvió connection refused por reinicio n8n, se repetirá cuando sistema estable.

## Verificación física posterior al despliegue 06105f9 (18-10-2026)

Marcador real DEV = 06105f996e4d10309459c048868822646c64b938, salud DEV 200 y PROD 200. Recuperadas todas las capturas E2E anteriores al cambio de chat: p4par26oct18-simple COMPLETED en 19,36 s runtime, 0,23 s Writer; p4par26oct18-dates COMPLETED en 12,86 s runtime, dos escrituras de 0,21 y 0,19 s; p4par26oct18-nm needs_attention 13,73 s; p4par26oct18-person needs_attention 18,94 s. En las respuestas completadas las tres revisiones coverage / speaker A/B comienzan al mismo offset; no demuestra ahorro causal total entre textos distintos.

Tres capturas nuevas: p4parallel20261018-fresh-a N:M needs_attention 17,09 s; p4parallel20261018-fresh-b con dos personas COMPLETED 17,92 s, tres receipts en una ruta Core, action.write 5,61 s con DOS contextual resolutions GPT secuenciales (1,98 y 1,79 s); p4parallel20261018-fresh-c N:M needs_attention 18,12 s. La prueba con identidad ya existente p4parallel20261018-nm-known también devolvió needs_attention antes del preflight. Ninguna abstención se considera éxito; investigar por qué N:M no siempre supera revisores prewrite.

Hallazgo de elegibilidad: fresh-b alcanzó Core con 4 unidades (Day, 2 personas y referencias), pero excluir universalmente reference_lookup_only impidió paralelizar las 2 llamadas GPT (spans con offsets 0,04 s y 2,62 s). Modificado en rama: se admiten únicamente referencias ORDINARIAS sin relational_reference, mediante el MISMO _decide_reference_only_target y semantic_set_selector original. Se siguen excluyendo relaciones complejas, completas y clarificaciones. Inventario físico global se revalida y Writer mantiene el orden. Un test adicional mezcla cuatro unidades ordinarias/reference-only con dos decisiones simultáneas y mismo resultado/IDs que la ruta serial. El gate completo y el nuevo despliegue siguen pendientes al escribir esta línea.

## Comprobación Graph / Notes (no confundir con captura visual)

API real POST /api/notes operation=detail, días 8/11/12/17: todos contienen enlace a SELF; 11 de octubre contiene además las cuatro personas Irene, Leo, Nadia y Pablo. La operación backlinks de SELF devuelve 23 notas entrantes (antes 22). Contratos de rutas y etapas verificados por requestProductResult y tests JS. No se navegó visualmente Chromium en Pi: validada la capa HTTP, no el aspecto visual del gráfico.
