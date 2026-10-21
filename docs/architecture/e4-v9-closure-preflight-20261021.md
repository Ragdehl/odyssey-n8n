# E4 v9 — cierre de Testing y preflight Performance (21-10-2026)

## Qué cambió después de la auditoría v7

La campaña real de GPT en bóvedas sintéticas detectó un **nuevo rechazo válido y reproducible**: «Hoy terminé el informe. Conocí a Ana y a Luis en el parque. Mañana tengo que llamar a los dos». Router propuso exactamente tres scopes (Core independiente, Core Ana/Luis y una Task), el modelo DAG y su revisor aprobaron el mismo conjunto y ambos revisores de Personas contestaron. La abstención efectiva **antes del primer WRITE** fue `DEPENDENT_N_PERSON_SET_UNVERIFIED`.

La causa exacta era un contrato demasiado estricto en `odyssey_apps/tasks/dependent_target.py`: `full_source == antecedent_source + dependent_source`. Para grupos independientes anteriores, esa igualdad es falsa aunque el sufijo esté completo. Se sustituyó por **sufijo original íntegro** `full_source.endswith(antecedent_source + dependent_source)`: el validador no inventa fuente ni elimina grupos; el grafo valida cada carácter del original y la etapa E2 vetará cualquier Person materializado en grupos Core omitidos. Nuevas pruebas positivas del prefijo independiente y negativas de fuente truncada/desordenada. Ruff PASS y tests focales **75 PASS**.

## Campaña real ampliada, no solo mocks

Script reproducible: `scripts/odyssey_e4_plural_model_campaign.py` (requiere `ODYSSEY_E4_LIVE_APPROVED=1`, credenciales existentes y bóveda efímera). [Recibo JSON con fases, tiempos y hash de logs](e4-v9-campaign-performance-receipt-20261021.json).

- «Clara y Hugo → ambos»: GPT **completed**, 2 Person, 1 Task, ambos backlinks físicos, replay inmutable, **47,092 s**.
- «Clara, Hugo y Nuria → los tres»: GPT **completed**, 3 Person, 1 Task, 3 referencias, replay, **58,473 s**.
- «Clara y Hugo → uno de los dos»: **needs_attention** (seguro), sin Task ni Person escritos, **21,016 s**; esta abstención NO se cuenta como aceptación positiva.
- «Terminé el informe; Ana y Luis en el parque → los dos»: primera ejecución **needs_attention** y 0 cambios (**40,19 s**); después del fix dos reejecuciones independientes: status `completed` en traza con 5 Notes sintéticas y prueba física **completed**, 2 Person y 1 Task, ambos enlaces, replay inmutable (**52,918 s**).

Los tres positivos directos fueron **47,092/52,918/58,473 s** (mediana observada 52,918 s); `application.router` reportó aprox. **35,3/42,1/45,7 s** en las respectivas ejecuciones; tiene subfases superpuestas con Core y **no deben sumarse** tiempos parciales. El Writer por acción es del orden de 17–32 ms, pero los modelos constituyen el coste dominante. Uso máximo RSS Python de la campaña: ~119 MiB. `ConstantEmbedder` sustituye embeddings durante la prueba; n8n y Chromium solo están presentes en la evidencia E2E separada de v8.

## Modelo de embeddings offline

Se intentó cargar `FastEmbedTextEmbedder` únicamente desde `~/.cache/fastembed` con `local_files_only=True`: **no existe una copia utilizable**. Resultado `blocked_cache_absent_or_unusable`, en ~4 s, sin descarga, sin acceder a cachés protegidas ni a datos privados. No se inventan medidas cold/warm. Este bloqueo ambiental permanece visible para Performance; no justificaría un PASS final del producto que utilice FastEmbed real.

## Presupuesto provisional de rendimiento para evaluación, NO SLA de usuario

- En la Raspberry con bóveda sintética: mediana de solicitud GPT directa positiva **≤60 s** y p95 objetivo **≤120 s**, a confirmar con **mínimo 20 casos independientes**.
- Navegador+n8n+GPT real E2E: mediana objetivo **≤90 s** y p95 objetivo **≤120 s**, a confirmar con **mínimo 20 ejecuciones heterogéneas**; hasta ahora hay solo unas pocas muestras exitosas.
- Readback de 1000 notas de relleno con dos enlaces: p95 empírico **≤750 ms** en 25 muestras (observado **453,747 ms**); RSS Python de la ejecución aislada **≤256 MiB**.
- FastEmbed en frío/caliente y cargas de índice real deben medirse en entorno **aislado, con el modelo disponible offline**, antes de declarar Performance PASS. La carencia se trata como `BLOCKED` de esos subgates, no como fallo del algoritmo ni como aprobado.

Estos umbrales son **objetivos experimentales de evaluación**, no compromisos de producción, y las tres muestras directas no constituyen p95 estadístico. Es mejor recibir un dictamen Performance BLOCKED específico que redefinirlo falsamente como PASS. Ningún cambio de DEV, PROD, E5, Vault personal, Cloudflare o credenciales.

## Gates

Tras el cambio, `scripts/odyssey_cross_surface_gate.py`: **1.532 Python + 179 Node + 7 subtests PASS**, y `ruff` PASS. Se preserva la evidencia previa de Chromium+n8n+GPT y los documentos v8; una nueva auditoría deberá leer el **diff completo** contra la base E3, los recibos inspeccionables y emitir sus cuatro dictámenes sin Builder. La suite global conserva nueve benchmarks históricos fallidos en la base; no afirmar PASS global.
