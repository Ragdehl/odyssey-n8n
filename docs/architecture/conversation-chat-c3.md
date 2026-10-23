# C3 — Chat, ayuda y continuidad segura (23-10-2026)

**Estado:** contrato de código local y pruebas de modelo reales acotadas; **no integrado en el flujo browser/n8n/DEV**. No está disponible aún para el usuario final. Core/E3, vault y PROD no se han modificado.

## Resultado y límites

- `odyssey_runtime/conversation_chat.py` reutiliza `OpenAIConversationGateway._complete`: una salida estricta con `outcome`, `answer`, `supporting_ids`; sin herramientas, plan, escritores, reintentos ni permiso de escritura.
- La clasificación de entrada C1/C2 es anterior e independiente. Solo después de recibir `CHAT` sin decisiones canónicas pendientes, un segundo modelo barato puede etiquetar `HELP` o `GENERAL`. `ROUTER` se conserva íntegro (texto original, sin parafrasear), y una referencia conversacional pasada por `CONTEXT` puede recibir `PRIOR_CONVERSATION` con fuentes verificables.
- `dispatch_before_chat` inspecciona el `LocalClarificationStore` y `CandidatePendingRepository` existentes ya vinculados al actor; si queda alguna decisión Core pendiente, conserva la ruta de continuación de Core. No intenta resolver opciones ni reescribir el pedido original. Estado corrupto: falla cerrado. Una validación final y el consumo/almacenamiento corresponden a la ruta Core original.
- `load_verified_help` lee la ayuda versionada **solo** para un conjunto inyectado por el servidor de capacidades realmente desplegadas. No acepta contenido arbitrario ni una ruta externa. La rama `GENERAL` recibe cero párrafos de ayuda; la rama `HELP` recibe únicamente secciones aceptadas. **Aún falta el adaptador de despliegue que obtenga capacidades reales de la instalación,** no se debe aceptar una lista suministrada por el navegador o la propia IA.
- `PRIOR_CONVERSATION` usa hasta 8 turnos ya recuperados del almacén actor-bound, máximo 4096 bytes; citar IDs de turnos no certifica una identidad para Core. Preguntas de conocimientos personales guardados se siguen enviando al Router y su answerer fundamentado actual de n8n, no al Chat social.
- Respuestas `ChatReply.product_response` son compatibles con el endpoint existente `/conversation/assistant-response` y su protocolo de respuesta, sin un segundo historial ni una escritura directa desde C3. Una prueba HTTP sintética verifica persistencia, no duplicación y rechazo entre actores.

## Evidencia

- Pruebas focalizadas C1/C2/C3 y continuaciones previas: **93 PASS** después de añadir HTTP y rechazo de texto de ayuda falsificado.
- Primera campaña real `gpt-6-luna` / esfuerzo low / `store=false` (máximo 8 llamadas, 750 tokens de salida por llamada): **6/8**. Fallos en abstenciones semánticas; no se aceptó la versión.
- Prompt revisado con regla explícita de abstención y citas vacías cuando faltan pruebas: **8/8** en la matriz sintética ES/FR, hash `4f953ef7f9f6697d`. Evidencia `/tmp/odyssey-c3-real-prompt-matrix-v2-20261023.log`.
- Clasificador CHAT general/ayuda separado, 8 llamadas reales máximas / 120 tokens de salida: **8/8** en matriz ES/FR, hash `136e7f79fb56e994`. Evidencia `/tmp/odyssey-c3-real-help-purpose-20261023.log`.
- Son pruebas de un solo intento por frase; **no demuestran estabilidad bajo reformulaciones**, eficacia de producto ni integración browser → n8n → GPT → Markdown → UI. No se ha promovido ni probado en PROD.

## Para activar C3

1. Inyectar el actor y los almacenes Core pendientes desde `RuntimeComposition`, sin construir un nuevo pendiente ni saltarse el orden preexistente de `execute_product`. Hacer fallar cerrado la ambigüedad/estado ilegible.
2. Obtener las capacidades de la versión realmente desplegada mediante un adaptador interno, pasar solo las confirmadas; añadir almacenamiento duradero del **turno de usuario** en el camino CHAT mediante el contrato ya existente, idempotencia y errores seguros.
3. Conectar a n8n y al navegador como rama opcional de DEV sin alterar la ruta actual; evaluar mensajes mixtos (guardar + conversar), llamadas lentas, historial ausente, preguntas de notas, ayuda bilingüe, intercalado de aclaraciones y mensajes duplicados.
4. Pasar nueva revisión independiente, matriz real repetida y E2E de la aplicación de principio a fin, comprobando que cualquier mutación ocurre solo por Core/E3 y que el Markdown/UI refleja el resultado. Requerir permiso explícito de despliegue/PROD por separado.

**Decisión arquitectónica:** PROCEED solo en incremento read-only. La ruta de persistencia de conversación y la continuación Core ya existen; crear un motor de chat paralelo, un historial nuevo o un escritor duplicado añadiría riesgo sin beneficio. La etiqueta de ayuda añade una llamada breve únicamente después de `CHAT`, y su coste/latencia deberá medirse en una integración real antes de adoptarla.
