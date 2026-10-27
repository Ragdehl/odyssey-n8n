# E5: visita futura declarativa — incidente DEV 27-10-2026

**Estado:** V5 evaluado con GPT real 12/12 PASS y con tests de código PASS; corrección todavía **solo en fuente**, sin DEV ni E2E del nuevo commit. El DEV probado sigue en `250ae42`; cualquier otro estado debe contrastarse con su marcador real.

## Síntoma y prueba observable

- 21:41: «Hoy e ido de paseo por Paris con Manu e Iken» produjo `completed`, tres notas afectadas y readback Core/E3/Git; esto no demuestra que la siguiente frase se pudiera interpretar.
- 21:43: «Manu vendrá a Toulouse el 16 de noviembre de 2026», recibo DEV `web-fd8a7cea-4e52-4406-8a0f-520a2d635b7c`: Router seleccionó `events`, interpretación GPT-6 Luna (low) devolvió `ABSTAIN`, resultado `EVENT_ROUTING_ABSTAIN`, `actions=[]`, sin Core/E3 ni notas afectadas. La respuesta C4 fue genérica, sin explicación específica. Duración total observada ~22 s.
- Causa de contrato: V4 definía Event como ocurrencia programada, pero exigía título literal mediante **sintagma nominal**; una llegada o visita futura declarativa puede carecer de uno. No es un fallo de Git, Temporal ni identidad personal porque ninguna de esas etapas se alcanzó. El recibo no conserva el JSON íntegro del modelo, por lo que la influencia exacta del requisito nominal es una **hipótesis causal bien apoyada**, no una prueba del motivo interno de GPT.

## Revisión propuesta

- **Mismo E5 Events:** V5 hereda sin alterar V4; admite llegadas/visitas explícitamente fechadas y confirmadas descritas en modo declarativo. Si no hay título nominal, permite cita fuente de la cláusula verbal que describe el evento. Nunca inventa personas, títulos, identidades, horas ni datos de calendario.
- Continúa `ABSTAIN` para hechos fechados que no son eventos, preguntas, hipótesis, condicionales, predicciones inciertas, negaciones y recuerdos. El Router no autoriza escrituras; Temporal resuelve fechas; E3/Git conserva autoridad exclusiva.
- Evaluación de producción pendiente con GPT-6 Luna low: no equiparar candidatos congelados con predicciones reales. Antes de activar, medir una matriz de visitas ES/FR/EN frente a hipótesis, tareas, datos biográficos y negaciones. No repetir notas reales ni usar el vault DEV como corpus.

## Matriz congelada de evaluación de intención

| Familia | Ejemplo sintético | Esperado |
|---|---|---|
| Visita futura ES | Mi prima vendrá a Lyon el 16 de noviembre de 2026 | CREATE |
| Llegada futura ES | La vecina llegará a casa el 20 de noviembre de 2026 | CREATE |
| Visita futura FR | Ma cousine viendra à Lyon le 16 novembre 2026 | CREATE |
| Visita futura EN | My cousin arrives in Lyon on November 16, 2026 | CREATE |
| Incertidumbre | Quizá mi prima venga a Lyon el 16 de noviembre de 2026 | ABSTAIN |
| Condicional | Si mi prima viene a Lyon el 16 de noviembre de 2026, saldremos | ABSTAIN |
| Negación | Mi prima no vendrá a Lyon el 16 de noviembre de 2026 | ABSTAIN |
| Pasado | Mi prima vino a Lyon el 16 de noviembre de 2025 | ABSTAIN |
| Dato no evento | Mi prima tiene 30 años el 16 de noviembre de 2026 | ABSTAIN |
| Tarea | Tengo que llamar a mi prima el 16 de noviembre de 2026 | ABSTAIN |

**Prompt:** GPT-6 Luna low, `e5_event_intent_v5`; V4 SHA-256 `ae6d955030e54060111355e8c9be7a6f96306e11e3b04411fa54a299586a381c`; V5 SHA-256 `d43908fb880533dd81ac14dfd7717834dcb6d3f4f022f9c2787e104ae3317ad2`. La matriz anterior se ejecutó con llamadas nuevas al GPT real: **12/12 PASS**, sin escrituras y con datos sintéticos. Las pruebas deterministas adicionales validan esquema, procedencia exacta, ruta sintética Core/E3 y Calendar; ninguna sustituye al E2E de la app desplegada.

## Evidencia de evaluación con GPT real (27-10-2026)

El ejecutor de lectura scripts/odyssey_event_visit_v5_live_gate.py usó **OpenAIEventInterpreter de producción, GPT-6 Luna, effort low**, output estricto e5_event_intent_v5, store=False, guardia de entorno systemd y 12 llamadas máximas sin acceso al vault. El prompt exacto tiene hash SHA-256 d43908fb880533dd81ac14dfd7717834dcb6d3f4f022f9c2787e104ae3317ad2. Todas las 12 interpretaciones nuevas correspondieron a su expectativa congelada; se incluyeron 4 visitas ES/FR/EN, 6 abstenciones adversariales, un evento ordinario y una consulta. Títulos y fechas citados del texto original, validados por el intérprete tipado. Coste estimado: **0,0015024 USD** de acuerdo con la tabla de precios de 09-10-2026, no con una factura.

Recibo JSON privado en Raspberry: /home/ragdehl/projects/.odyssey-agent-runs/event-visit-v5-live-20261027/result.json. No contiene secretos ni hechos personales. La prueba NO invocó Router ni Temporal/Core/Writer, NO fue una sesión de usuario autenticada en navegador y NO valida que en DEV se hayan guardado nuevas notas. Debe mantenerse pendiente esta prueba vertical hasta el deploy del SHA final, sin realizar más llamadas GPT por repetición rutinaria.

## Corrección de respuesta al usuario

La rama `CANNOT_ANSWER` de `workflows/odyssey-online.ts` solo sustituye el error C4 genérico por «No he guardado ningún evento» cuando el recibo Core prueba `EVENT_ROUTING_ABSTAIN`, `needs_attention`, una única ruta Events pendiente, `actions=[]`, `affected_stable_note_ids=[]` y ausencia de `note_result_snapshot`. Nunca usa esta garantía si hay escrituras inciertas; el resto de errores conserva el comportamiento C4. Regresión ejecuta el propio `routeCode` del workflow y valida el mensaje ante ambos casos. **No desplegado aún.**

## Copia DEV anterior a cualquier despliegue nuevo

Directorio local privado de Raspberry: `/home/ragdehl/projects/.odyssey-agent-runs/dev-4db42bc-deploy-20261027/` (archivos 0600 y manifest con SHA-256). Vault y state completos, runtime operativo con copias SQLite por API y volumen n8n parado durante archivo y reiniciado después; excluye cache de embeddings regenerable y snapshots históricos del runtime. No compartir estas copias, incluyen credenciales y estado privado de DEV. Fuente y DEV no se han actualizado por la investigación.
