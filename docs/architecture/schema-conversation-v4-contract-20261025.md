# Conversación de modelo de notas — contrato V4 (histórico de diseño y preparación)

**Problema observado:** en la campaña V3, 33 de 40 respuestas tuvieron la etiqueta de operación prevista, pero eso no acredita la corrección de sus tipos ni el cumplimiento de las restricciones. En la regresión V3 se propuso ISBN sobre el tipo general `document` en lugar de aclarar cómo estaban representados los libros. En el holdout, una propuesta afirmó que una simple descripción del tipo `Planta` haría cumplir una exclusión por origen. Ambos son fallos de semántica y autoridad, no de JSON. Evidencias congeladas: [informe V3](schema-conversation-v3-live-eval-20261025.md).

## Cambio mínimo V4

Conserva **una** llamada `OpenAIConversationGateway._complete`, `gpt-6-luna`/`low`, `store=False`, presupuesto y límites actuales, el mismo esquema JSON estricto, los cinco resultados (`ADD_TYPE`, `ADD_PROPERTY`, `REUSE`, `CLARIFY`, `ABSTAIN`), el mismo `UserSchemaRegistry.preview` read-only / CAS y confirmación separada por clic. Sin nueva IA, cola, índice o sistema de tipos. El prompt mejora estas invariantes generales:

1. **Identidad/granularidad:** un tipo existente solo es reutilizable si representa el mismo concepto, no una categoría amplia que *podría* contenerlo. Las notas/objetos «ya guardados» no prueban su tipo canónico actual. No añadir propiedades a un contenedor genérico cuando el tipo de destino es incierto; preguntar cuál es. Los cambios de propiedad afectarían al modelo de **todas** las notas de ese tipo.
2. **Condiciones de alcance:** un esquema de tipos y propiedades no define un filtro ejecutable de qué objetos se pueden crear, importar, enlazar o descubrir a posteriori. No afirmar que una descripción impone exclusiones o condiciones. Pedir aclaración entre selección manual de entidades y una regla de filtrado realmente implementada (que **no** se implementa en este corte).
3. **Identidad estable:** no estrechar arbitrariamente el tipo por estados transitorios, como «leído», «terminado» o «archivado», ni inventar atributos. Mantener la clase de identidad pedida por el usuario.
4. **Unidades:** no inventar unidad o precisión en mediciones; representar como texto cuando eso conserve fielmente la expresión o pedir detalle cuando sea necesario, sin bloquear innecesariamente la creación de un tipo independiente claro.

La **vista previa de Notas** muestra advertencias deterministas: para `add_property`, el alcance es todo el tipo canónico indicado (no solo las entidades mencionadas); para `add_type`, la descripción no ejecuta exclusiones ni filtra automáticamente menciones previas. Las advertencias usan texto fijo con el nombre real devuelto por Core y nunca afirman que se haya configurado una regla.

## Límites explícitos: un prompt NO es un verificador semántico

La V4 aquí implementada **no demuestra** que la IA comprenda correctamente esas reglas. El validador estructural sigue comprobando citas fuente, tipos permitidos y CAS, pero **no puede demostrar equivalencia semántica de clases ni detectar todas las condiciones en todos los idiomas**. No confundir la revisión humana de la vista previa con una certificación automática de fidelidad. No introducir guardas de palabras sueltas, nombres de ejemplos, idiomas o casos del corpus: serían sobreajuste contrario al contrato de generalidad. Si V4 vuelve a producir un destino o una exclusión falsamente seguros, seguir bloqueando la activación y revisar un límite de autoridad más fuerte antes de continuar.

## Matriz y evaluación pendiente

- **Prompt V4 SHA256** `b52def8fca2037d1260aac595b8b10d9fd8db756b254c3c0a7369e26dad5bd2a`.
- **Schema JSON SHA256** `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50` (sin cambios).
- `tests/fixtures/schema_suggestion/evaluation_v4_holdout.json`: **16 escenarios nuevos sintéticos**, creados antes de cualquier llamada real V4: identidades inciertas, términos explícitos, exclusiones, medidas, negaciones, correcciones y cambios múltiples en ES/FR/EN. Incluye *semantic_checks*, que necesitan revisión de propuesta completa por una persona y no pueden puntuarse por simple coincidencia de etiqueta.
- V1 de 24 casos y el anterior holdout de 12 ahora **son regresión conocida**, NO un nuevo holdout independiente. No cambiar expectativas a posteriori para subir porcentajes. El evaluador reconoce la nueva matriz pero exige aprobación explícita, entorno aislado, presupuesto y evidencias en archivos locales 0600.
- **Actualización posterior (misma V4, hash inalterado):** el usuario autorizó otras 40 llamadas que se ejecutaron totalmente sobre este hash. La evaluación real nueva logró 39/40 coincidencias de operación, pero **tres fallos de idioma** y algún matiz de intención; detalles en [informe V4](schema-conversation-v4-live-eval-20261025.md). No confundir la preparación de este contrato con aceptación semántica; la autorización ya se agotó y sigue faltando Chromium→n8n→Core con vault sintético.

## Estado de habilitación

La bandera `ODYSSEY_SCHEMA_ASSISTANT_ENABLED` sigue **apagada**; confirmaciones reales requieren su propia bandera DEV y clic. No fusionar ni desplegar V4 como función lista para usuario. No se alteran `PendingReference`, ningún tipo existente, la persistencia Markdown, el backfill ni la detección retrospectiva, que permanecen pendientes.
