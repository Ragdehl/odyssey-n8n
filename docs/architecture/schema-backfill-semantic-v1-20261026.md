# Backfill semántico automático V1 — candidato en código, NO desplegado

**Producto:** una vez que la persona acepta añadir un tipo o propiedad, Odyssey trabaja autónomamente. No se debe pedir permiso nota por nota, ni requerir 50 clics para analizar 1.000 fuentes. El usuario recibe un resumen de cambios y excepciones agrupadas, con historial recuperable. El objetivo continúa siendo funcionamiento local en el dispositivo; consultar un proveedor externo para análisis semántico será una opción diferenciada, con consentimiento claro y alternativa local para operaciones sin IA.

**Código:** odyssey_core/schema_auto_backfill.py ejecuta escrituras validadas mediante CanonicalMutationGate, update_entity, lectura física, GitHistoryRecorder local y CAS de revisión + hash. odyssey_runtime/schema_backfill_interpreter.py añade un intérprete semántico y un **segundo pase con instrucciones de revisor independientes**, reutilizando el OpenAIConversationGateway._complete, con esquemas JSON cerrados. El modelo no recibe una vía de mutación ni puede devolver IDs distintos a los que suministra Core.

## Decisiones de autoridad

- El lector scan_schema_sources es la única fuente de SourceNote (IDs, revisiones, hashes y hechos marcados). Ejecutar el escaneo completo **antes** del backfill: las escrituras cambian el inventario, invalidando cursores activos.
- Caso rápido: declaración exacta propiedad: valor con **un único hecho marcado**, sin Markdown legacy no trazado y validación de tipo: completar sin gasto IA. Si hay otros hechos, texto legacy, conflictos, fechas parciales o valor previo explícito, no inferir sobre esa frase de manera aislada.
- Caso semántico: pasar el contenido completo y **acotado** de una nota (máximo 16 hechos, 12.000 caracteres; no omitir hechos para fabricar certeza) a odyssey_schema_backfill_interpret_v1. Una segunda llamada distinta, odyssey_schema_backfill_review_v1, revisa la propuesta exacta contra todos los hechos, identidad del sujeto, temporalidad, negaciones y contradicciones. Solo si ambos coinciden en localizador, cita literal única, valor y estado presente, se produce un objeto interno ReviewedSemanticBackfill.
- Core sigue verificando tipo, hash, revisión, fuente y localizador exactos, cita única, tipo de dato, ausencia de valor preexistente, contradicción con declaraciones explícitas, preflight de historial, escritura y readback. Se devuelve una evidencia de cambio recuperable, no una confirmación de IA. Nunca eliminar, fusionar entidades, sobrescribir datos preexistentes ni reclasificar.
- SemanticBatchEnricher.run_batch integra la vía rápida y el doble modelo para **hasta ocho** SourceNote preleídos por llamada, devuelve recibos y un resumen, sin autorización humana individual. No publica endpoints y no se ha activado en el trabajo de DEV ni PROD. Los fallos técnicos o de historial después de escribir detienen la ejecución: no reintentar a ciegas.
- El lector legacy sin localizador no autoriza mutaciones. El módulo **no** crea nuevas entidades; la resolución/deduplicación de identidad y el backfill de otras clases de propiedades siguen siendo otro corte.

## Evaluación y limitaciones

**Prompt interpret SHA256:** 19f28887aeb3fc9d1aec0482034650e409f599c3226b48c8883480fb2443d0bd.

**Prompt reviewer SHA256:** 23322dd95519d18b8d39403d50ea356b2d56e060b38da6fd1316df60c4e77199.

**Holdout previo a llamadas reales:** tests/fixtures/schema_backfill/evaluation_v1.json, 18 casos sintéticos ES/FR/EN: pasado/presente, negación, condicional, referencia ajena, homónimos, corrección, conflicto entre hechos, declaración citada/instrucciones maliciosas, fechas completas/parciales, enteros con intervalos. Cada caso conserva fuentes y resultado esperado **pero no afirma que un modelo haya acertado**. Tests unitarios y vertical sintético verifican parsers, revisión, coincidencia de citas, rechazo de tipos/IDs de fuente falsos, preferencia determinista y cambios reales a un vault temporal con Git local.

**No se ha realizado una campaña nueva contra el proveedor real.** No asignar PASS de semántica a modelos reales basándose en fakes. El segundo pase no es una prueba matemática de la verdad y comparte proveedor/modelo; las dos llamadas pueden coincidir equivocadamente. Antes de habilitar el intérprete como escritor: autorización de llamadas facturables y de transmisión de hechos sintéticos, campaña congelada con modelo/esfuerzo de producción (mismatches revisados cualitativamente, especialmente falsas escrituras), prueba de ablación de revisor y coste/tokens/latencia, más Chromium DEV sintético → n8n/Core/E3 físico y los cuatro auditores Codex en SHA fijado. **Un falso positivo automático o contradicción no detectada bloquea promoción**; un output JSON correcto no basta.

**Actualización del 26-10:** el [diario reanudable](schema-backfill-journal-v1-20261026.md) ya materializa los candidatos antes de mutar, registra intención previa, reconcilia interrupciones contra Markdown y Git, y mantiene los casos sin IA como deferred. La conexión Notes/n8n/índices existe ya en fuente solo para hechos deterministas bajo bandera DEV desactivada; no se ha instalado en el servicio DEV ni existe aún un worker móvil. Los commits por nota son provisionales y falta la UX de resultados/deshacer y evaluación con modelo real.

**Estado de origen:** rama feat/schema-confirm-activation, PR #156 Draft. DEV sigue con checkout anterior y las flags de IA/scan/confirmación apagadas; no se han escrito notas reales.
