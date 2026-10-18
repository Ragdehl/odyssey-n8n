# Aislamiento offline de pruebas y Chromium real de DEV — 19 octubre 2026

## Qué se ha probado (evidencia sin datos privados)

El host Raspberry Pi Debian arm64 tiene `bubblewrap 0.11.0` funcionando sin root y conserva un navegador Chromium 154 en caché con bibliotecas de usuario bajo `/tmp/odyssey-p4-browser-deps`. No se instalaron paquetes, no se alteró Cloudflare, no se tocó PROD, ni se desplegó la rama P4 en DEV. DEV sigue en `b0fc9b21`, PROD con `/healthz` 200.

### A. Aislamiento real de procesos **offline**

`scripts/odyssey_agent_offline_sandbox.py` prepara un `bwrap` en espacio de nombres de usuario, PID y red completamente separado. Solo monta como escritura `/workspace` una ruta sintética `/tmp/odyssey-agent-sandbox-*` perteneciente al usuario; monta `/usr`, `/lib` y `/bin` solo lectura, usa `/etc` y `/tmp` efímeros y no monta `/data`, `~/.ssh`, `~/.codex`, el repositorio ni los directorios DEV/PROD. Un programa Python real desde dentro pudo escribir `/workspace/synthetic-marker.txt`, pero reportó AUSENTES el hogar privado, `~/.codex`, `~/.ssh`, directorios de DEV/PROD y `/data`; también reportó que no podía conectarse a `127.0.0.1:28780`. Cuatro tests reales (incluyen alias symlink a ruta prohibida y rechazo de introducir una carpeta del vault) pasan con el kernel del dispositivo. El control se añade al grupo `runtime_http_and_isolation` del gate transversal.

**Límite fundamental:** este aislamiento es **para tests offline**, NO el encapsulado actual de las sesiones Codex que necesitan acceso a proveedores remotos. Codex sigue usando su sandbox workspace-write/read-only con variables de entorno filtradas y worktree dedicado, pero sin garantías OS suficientes contra acceso de red a PROD ni exposición accidental de credenciales. NO afirmar que los agentes con acceso a modelo están listos para funcionar solos sobre archivos y servicios personales. Para ese paso falta un broker de credenciales y política de egress o una VM/usuario OS restringido, validado desde el propio host.

### B. Navegador real, lectura de DEV por proxy loopback sin mensajes nuevos

Se reutilizó el proxy local existente `/tmp/odyssey-p4-browser-proxy.mjs` (frontend instalado DEV + solicitudes `/api/*` al puerto DEV local) y el Chromium ARM64 cached; no se accedió a Cloudflare Access del móvil ni se enviaron nuevas escrituras de Notes. Script ad hoc reproducible en este host: `/tmp/odyssey-safe-dev-browser-inspect-20261019.cjs`; resultado JSON `/tmp/odyssey-safe-dev-browser-inspect-20261019-result.json`. Las vistas móvil 390×844 y desktop 1280×960 verificaron carga HTTP 200, frontend desplegado `b0fc9b21...`, 41 elementos de interacción antes y después de recarga, 20 botones de detalles técnicos antes/después, hoja de detalle abriéndose, SVG presente y cero excepciones JS de página. No se registraron textos de las conversaciones.

Segunda inspección ad hoc `/tmp/odyssey-dev-graph-readonly-20261019.cjs`, resultado `/tmp/odyssey-dev-graph-readonly-20261019.json`: clic y cierre reales en **20 de 20** botones de detalle, los 20 se renderizan con SVG; **5** contienen `Estado de ruta` y pruebas de escritura Core con **10 recibos** agregados; **0** recibos Core duplicados dentro de su detalle, **0** avisos falsos de historial anterior. Esta comprobación abarca la evidencia persistida presente, no la semántica completa N:M ni el 100% de los mensajes anteriores. El ultimo detalle del chat probado por separado no contiene recibos Core; no extrapolar.

**Límite de producto:** el proxy loopback no comprueba Cloudflare Access y no se efectuó una entrada nueva `browser autenticado → n8n → GPT → Writer → readback → gráfico` con el P4 de la rama (aún sin deploy). Estas inspecciones NO autorizan P4, E4, E5 ni E6. El siguiente gate de producto debe usar identidad y vault exclusivamente sintéticos, browser de extremo a extremo y validar identidad SELF, Tasks, dependencias y grafo, sin tocar PROD. Las pruebas previas de P4 Core que existen en DEV están descritas con sus releases en `p4-dev-latency-graph-20261017.md`.

## Cómo reproducir

Offline: crear una carpeta desechable `/tmp/odyssey-agent-sandbox-<id>` con propietario actual y ejecutar `python3 scripts/odyssey_agent_offline_sandbox.py --workspace <ruta> --smoke`. Unit tests `python -m pytest -q tests/runtime/test_agent_offline_sandbox.py` requieren `bwrap` disponible para efectuar comprobaciones reales (en otros hosts sin Bubblewrap se saltan las dos pruebas específicas del kernel). El comando protege la ruta con `Path.resolve(strict=True)`, ownership y prefijo de scratch, para no montar accidentalmente un vault real.

Chromium: con proxy local aislado DEV activo en `127.0.0.1:29871` y librerías extraídas, `LD_LIBRARY_PATH=/tmp/odyssey-p4-browser-deps/root/usr/lib/aarch64-linux-gnu node /tmp/odyssey-safe-dev-browser-inspect-20261019.cjs`. **No iniciar un proxy ni un browser hacia PROD**. El navegador y el proxy son herramientas de inspección temporales, no parte del runtime de Odyssey.

## Resultado final de regresión

Se ejecutó el gate completo tras introducir el runner y sus pruebas: **1156 Python PASS, 7 subtests PASS y 174 JavaScript PASS** en la Raspberry. Ruff del runner y tests PASS, ledger E2/E3 continúa marcado P4 DEV no autorizado. El código quedó solo en la rama de desarrollo local, sin cambio del frontend ya desplegado.
