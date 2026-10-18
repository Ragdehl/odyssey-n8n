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
