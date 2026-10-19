# P4 — webhook HTTP real de n8n en entorno sin red (19-10-2026)

## Resultado demostrado

Prueba nueva reproducible en `scripts/odyssey_n8n_isolated_webhook.py --run`. Se usa **n8n 2.33.7 real**, instalado ya en Docker, pero arrancado en un contenedor efímero con SQLite propia, `--network none`, filesystem de solo lectura, sin privilegios, sin montar directorios de DEV/PROD, credenciales ni sockets. Se monta exclusivamente un archivo JSON de workflow **sintético**, bajo `/tmp/odyssey-n8n-real-webhook-*/workflow.json`, no un archivo de la cuenta.

El workflow temporal incluye un **nodo Webhook real**, un validador de la petición sintética, un nodo IF que separa peticiones autorizadas y denegadas, un Code que transporta el resultado P4 auténtico del Writer, **el nodo Code exacto de DEV** `Route bounded product result` (extraído sin modificar de `/data/odyssey-dev/runtime/n8n-render/odyssey-online.json`), y sendas respuestas HTTP 200/403.

El Writer P4 se ejecuta realmente ANTES de crear el workflow; usa el caso grabado `maya_simple` con un actor y un vault completamente temporales, de modo que crea físicamente un Day y una Person, ambos con procedencia verificada. El workflow **no invoca el Writer dinámicamente por el webhook**, sino que recibe una copia inmutable de su resultado. Se mantiene explícita esta distinción: **n8n real y su endpoint HTTP sí están probados; la integración dinámica entre el webhook y el Writer/GPT en vivo no**.

Desde **dentro del contenedor aislado**, Node envía `fetch` al webhook `http://127.0.0.1:5678/webhook/odyssey-p4-isolated-fixture-20261019`. El servidor HTTP escucha únicamente en el espacio de red del propio contenedor y no publica puertos hacia el host.

## Pruebas HTTP positivas y adversariales

La última ejecución real terminó `RC=0`, `passed=true`, con resultado:
- POST correcto con ID y texto sintéticos exactos: **HTTP 200**, `status=completed`, `kind=acknowledgement`, **2 recibos Core** de éxito y **2 Notes** afectadas con gráfico conservado.
- POST con identificador incorrecto: **HTTP 403**; sin devolver esas notas como propias.
- POST con mismo ID pero texto diferente: **HTTP 403**.
- GET contra webhook definido solo para POST: **HTTP 404**.
- Resultado sigue sin exponer credenciales ni datos personales; el vault temporal se elimina después de la ejecución.

Durante las pruebas se detectó un comportamiento importante: **una excepción lanzada desde un nodo Code de n8n puede responder HTTP 200** sin entregar el resultado válido. Un error interno no es un mecanismo suficiente de autorización ni una señal de éxito del producto. El workflow sintético de prueba usa una bifurcación IF explícita hacia `Respond to Webhook` HTTP 403 para las dos negativas; conserva el nodo original de Odyssey intacto.

La ejecución también evidenció una ventana de preparación: durante el arranque, n8n puede responder 200 sin contener aún el resultado P4 esperado. El runner ya no acepta ese 200 como éxito; exige el JSON con `request_id`, `status=completed` y `kind=acknowledgement`, con intentos limitados y mensajes de fallo acotados. En la última repetición hicieron falta **10 intentos de disponibilidad** antes de recibir el resultado autenticado por el fixture. Esta medida **NO representa la latencia del n8n DEV ya activo**, y nunca atribuye a GPT los retrasos del contenedor efímero.

## Garantías técnicas

Los tests deterministas `tests/runtime/test_n8n_isolated_webhook_contract.py` verifican: exactamente siete nodos de tipo conocido sin credenciales, bifurcación entre original y denegado, rechazo de respuesta Writer con ID incorrecto/estado no completado/grafo sin writes/ruta extra, guardias de source+request ID, salida HTTP 403, Docker `--network none`, `--read-only`, `--pull never`, no puertos publicados, no montajes de vault/secretos, y ruta de archivo temporal propiedad del usuario. Este test forma parte de `scripts/odyssey_cross_surface_gate.py` y se ejecuta sin Docker ni red.

El test real de contenedor se ejecuta únicamente con `--run` (no en CI por coste de inicialización y uso de RAM); en la Pi usa una imagen ya presente, sin descargas ni acceso al n8n real. El runtime P4 no ha sido redeplegado. DEV continúa en `b0fc9b21`, PROD no recibe tráfico de prueba.

**Pendiente antes de aceptar P4:** navegador autenticado Cloudflare → webhook real DEV conectado al Writer contra usuario/vault exclusivamente sintéticos → GPT real → resultado n8n → Markdown → Notes/gráfico persistidos y pruebas multi-App/N:M. Sigue pendiente también separar la autenticación y el egress de las sesiones online de Codex con permisos OS verificables. La presente prueba no autoriza modificar PROD, DEV ni notas privadas.


## Regresión transversal

Tras introducir las nueve pruebas, se ejecutó la batería transversal completa: **1175 Python PASS + 7 subtests PASS, 178 JavaScript PASS**, Ruff y formato PASS. El ledger de aceptación conserva **18 invariantes / 41 anclas** y marca **P4 DEV UNAUTHORIZED** porque siguen faltando la integración dinámica GPT/n8n/Writer y la prueba autenticada del navegador.
