# Schema conversation V6 — propiedades, medidas e idioma (solo fuente; sin pruebas reales)

## Motivo y evidencia

En las **24 llamadas reales de V5** (24/24 autorizadas, hash `c34023593fb021384013e77c862afee580e8dc04795f4b65b46b8ae423bb3ca4`) hubo 22/24 coincidencias estrictas de etiqueta pero no aceptación semántica. [Informe completo V5](schema-conversation-v5-live-eval-20261025.md). Persisten: interpretar un atributo posesivo como posible clase independiente (`guitarras y sus marcas`), `número de jugadores` como texto, una explicación en español a un usuario inglés, y sugerir entero para la fecha parcial «año de nacimiento». La abstención en un caso futuro era segura pese a una expectativa histórica `CLARIFY`, y no se cambia retroactivamente.

## Cuatro invariantes generales V6

1. **Relaciones posesivas:** una solicitud de notas por cada X «con su Y» / «and their Y» / «avec Y» normalmente describe **una clase X con propiedad Y**, salvo que el usuario quiera explícitamente Y como entidad autónoma con fichas propias. No inferir dos tipos por una conjunción sin esa prueba. No hardcodear dominios ni resolver identidad canónica fuera de Core.
2. **Cardinalidad:** atributos de recuento entero («número de participantes», «número de páginas», «número de ruedas») deben proponer `integer` incluso si el mensaje no incluye el valor concreto. No inventar unidades para medidas con dimensión desconocida; para etiquetas/códigos alfanuméricos, preferir `string`.
3. **Precisión temporal:** una parte de fecha es una fecha parcial; no proponer de forma espontánea convertir año/mes/día de nacimiento en entero o texto, porque perdería semántica temporal. La pregunta `CLARIFY` puede reconocer que no existe aún soporte parcial sin fingir que la fecha completa es conocida.
4. **Idioma:** antes del JSON final revisar los campos nuevos visibles al usuario, mantener el idioma dominante del mensaje reciente; conservar sin traducción IDs canónicos y citas fuente originales. No añadir un segundo modelo, traducción automática o detección por palabras clave.

Mantener todos los controles previos: una llamada `OpenAIConversationGateway`, JSON estricto, cita exacta de intención, catálogo canónico, `UserSchemaRegistry.preview` con CAS, sin autorización ni escritura. `ABSTAIN` sigue permitida ante hipótesis futuras; no se relajan condiciones de mutación. **Un prompt no es un verificador determinista de equivalencia, idioma o fidelidad semántica.**

## Matriz y estado

- **Prompt V6 SHA256:** `310eb7922ca8f283fb209c134a92242600df48f8c7f6118f2f6f437eedabae6a`.
- **JSON schema SHA256 inalterado:** `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
- `tests/fixtures/schema_suggestion/evaluation_v6_holdout.json` contiene **12 casos nuevos sintéticos** ES/FR/EN, que no aparecen en los corpus anteriores. Se ha congelado **antes de cualquier llamada real V6**, con revisión semántica obligatoria de contenido, tipo/propiedad, idioma y fechas. Un único caso hipotético acepta como operaciones seguras `CLARIFY` o `ABSTAIN`; `ADD_TYPE`/`ADD_PROPERTY` nunca son alternativas aceptadas.
- **0 llamadas reales V6.** Las 24 llamadas autorizadas para V5 se consumieron. Ninguna llamada posterior está autorizada. Tests de prompt y evaluador locales no prueban comportamiento del proveedor real.
- Antes de permitir uso: evaluación real acotada V6 bajo nueva autorización explícita y revisión de propuestas completas, repetición de los casos inestables y aceptación Chromium→n8n→Core desde la app como usuario sintético con vault de pruebas. No desplegar ni aprobar PR sin estos gates.

Las banderas DEV del asistente y de confirmación siguen apagadas; PROD y los datos personales no se tocan. Sin retipificación de notas antiguas, índices especulativos `PendingReference`, backfill o descubrimiento retrospectivo nuevos en este corte.
