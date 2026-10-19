# P4 — n8n real 2.33.7 con código DEV real, sin red ni datos del usuario — 19-10-2026

## Objetivo y prueba

El E2E anterior ya probó Chromium real → HTTP → Runtime P4/Writer real → notas Markdown → gráfico/readback, pero reemplazaba n8n por un pequeño finalizador de prueba. Este bloque cierra **parcialmente** esa falta: **el motor real de n8n 2.33.7 y el nodo Code realmente desplegado en DEV** procesan ahora una salida producida por el Core Writer real sobre un vault desechable. No implica webhook real ni GPT en vivo.

**Artefacto original**, leído en modo solo lectura: `/data/odyssey-dev/runtime/n8n-render/odyssey-online.json`, commit DEV `b0fc9b21`. Nodo `Route bounded product result` de tipo `n8n-nodes-base.code`, código exacto sha256 **`7bc56e7c66497c694262a419e97d75ef6937b4fbcebc8c0205e72ac399ba84c9`**, 33216 bytes UTF-8. Se verifica que no lleve credenciales y que su única referencia cruzada sea `$('Odyssey product request')`. El código de ese nodo no se modifica ni se transpila en el test.

Se construye una ejecución sintética con cuatro nodos en un workflow JSON temporal: Manual Trigger → identificador de petición generado (Code) → resultado auténtico del Writer (Code que porta la respuesta ya materializada) → **Code original de DEV** `Route bounded product result`. La entrada real se obtiene de `tests/runtime/test_whole_source_light_product_p4.py`, snapshot fijo `maya_simple`, `RecordedClient` y `_fixture`, con un actor nuevo y un VaultRepository alojado en `tempfile.TemporaryDirectory`. El Writer produce dos receipts originales: Day `2026-10-15` + nota Maya, y una relación gramatical `(yo:` en Markdown.

El workflow temporal se monta en **un único archivo de solo lectura** dentro del contenedor n8n; el contenedor se ejecuta con `docker run --rm --pull never --network none --read-only --cap-drop ALL --security-opt no-new-privileges`, `/tmp` efímero y una **base SQLite exclusivamente efímera**. No se montan `/data`, `/home`, la DB de n8n DEV, credenciales, Docker socket ni endpoints PROD. La red del contenedor está completamente apagada. No se usan claves API ni conexión a GPT/Cloudflare. Se importa el workflow en esta base desechable y se ejecuta **con `n8n execute --id ... --rawOutput`** (la opción `--file` de n8n 2.33.7 está obsoleta y, aunque devolvió RC=0 en una prueba preliminar, NO ejecutó el workflow: fallo detectado y corregido, nunca contado como PASS).

## Ejecución real y verificación

El primer test completo dentro del contenedor terminó con **`status=success`, `finished=true`** y `lastNodeExecuted="Route bounded product result"`. El nodo Code original de DEV conservó:

- `route=direct`, `status=completed`, `kind=acknowledgement`;
- `request_detail.flow.routes` coherente, **dos writes Core** con `status=succeeded`;
- dos `affected_stable_note_ids`, y `note_result_snapshot.kind=affected_notes`, `total=2`;
- metadatos de ejecución reales de n8n, en vez de ejecutar JavaScript en `vm` o simular la salida del nodo.

Posteriormente la misma prueba se encapsuló en `scripts/odyssey_n8n_isolated_projection.py --run` y se reejecutó con **RC=0, `passed=true`**, validando automáticamente la forma de la respuesta desde el resultado de n8n (no solo el exit code). Resumen sin nombres/IDs privados: `/tmp/odyssey-n8n-isolated-projection-permanent-20261019.json`. El proceso Docker es **opt-in**, no parte de los tests rutinarios, pues hace migraciones iniciales n8n en la base temporal y tarda decenas de segundos en frío; no representa la latencia del n8n ya activo de Odyssey. Se mantiene la restricción de Pi de RAM: Docker avisó de que el kernel no aplicaba límites cgroup de memoria en la primera prueba; **NO se declara una garantía de límites RAM del contenedor**. Tras la ejecución, la Pi conservaba alrededor de 2403 MiB de RAM available y sus servicios siguieron disponibles.

`tests/runtime/test_n8n_isolated_projection_contract.py` tiene siete pruebas deterministas sin Docker: rechaza renderer de origen incorrecto, Code duplicado, credenciales, dependencia n8n no prevista, nodo HTTP externo, respuesta Writer ausente/fallida o con request_id malformado, y verifica los argumentos de Docker que bloquean red/privilegios y limitan los mounts. Incluido en `scripts/odyssey_cross_surface_gate.py`.

## Límites honestos antes de autorizar producto

Lo que ahora está **verificado**: Writer P4 real → objeto de resultado real → motor n8n y Code node exacto desplegado en DEV → respuesta de chat con notas y gráfico íntegros. Lo que NO se ha demostrado: conexión real navegador→webhook n8n; su autenticación Cloudflare; invocaciones GPT variables; enlace dinámico real del workflow completo con el Writer sobre una identidad/vault sintéticos; persistencia en la respuesta del webhook; postwrite/notes/donut del frontend conectado a n8n; aislamiento OS con red controlada de las sesiones Codex online. El Code está tomado de DEV desplegado `b0fc9b21`, no se garantiza que la rama P4 nueva ya esté compilada/desplegada allí. **El gate real P4 sigue PENDIENTE.**

El siguiente paso de menor riesgo es preparar la instancia de n8n de pruebas completamente separada, conectando **solo** un backend/runtime de vault sintético sin permitir egress hacia PROD; luego incorporar proveedor real con límite de llamadas, y finalmente browser autenticado/Cloudflare. No usar el n8n DEV/PROD principal como laboratorio de pruebas sin demostrar antes la separación de actor y almacenamiento; tampoco usar Codex con bypass de sandbox ni introducir nuevas credenciales de pago sin autorización.

## Cierre final del test de motor real

La versión definitiva con `--pull never` (Docker debe usar la imagen ya instalada, sin descarga externa) se reejecutó con **RC=0, `passed=true`** y los mismos resultados: n8n `success`, 2 receipts/2 Notes, flujo Core presente. Evidencia agregada `/tmp/odyssey-n8n-isolated-projection-hardened-20261019.json`. Gate transversal **1.166 Python PASS + 7 subtests PASS y 178 JS PASS**, con los 7 tests offline del nuevo contrato incluidos. Ledger de aceptación sigue en **18 invariantes / 41 anclas y P4 DEV UNAUTHORIZED**. No cambiar ese estado hasta el webhook real + GPT real + browser autenticado de identidad/vault separados.
