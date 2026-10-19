# P4 — Chromium → HTTP → Core Writer → Markdown → navegador, sintético (19-10-2026)

## Qué demuestra esta nueva prueba

Se han unido por primera vez en una prueba local reproducible el **frontend real actual del branch P4**, un navegador **Chromium arm64 real**, transporte HTTP localhost, el **RuntimeComposition/WholeSourceLightExecutor real**, el **Writer real** y sus ficheros Markdown, la conversación persistida por el runtime, un NotesQueryService real, el gráfico de ejecución y el reintento E3 sin modificar nada dos veces.

- **Mensaje de prueba**: `Ayer hablé con Maya.`, exclusivamente sintético.
- La prueba usa **un actor nuevo**, un bind SELF a `self.md`, índices SQLite y un **VaultRepository independiente** dentro de `tempfile.TemporaryDirectory(prefix="odyssey-synthetic-browser-",dir="/tmp")`. La carpeta completa desaparece al acabar cada ejecución.
- El plan lingüístico (Router, Planner, Coverage y dos revisores Speaker) proviene de `benchmarks/application_router/light_router_poc_20261016` y pasa mediante `RecordedClient`, un stub de respuestas grabadas. **No consulta GPT en vivo** ni consume tokens del proveedor.
- El frontend real vive en `odyssey_web/` de la **rama local** y se sirve desde un HTTP local temporal. Su API `/api/request` pasa a un **puente sintético** que envía por HTTP real al runtime `/execute` e inyecta la identidad sintética. El puente realiza la proyección de presentación equivalente a la responsabilidad de n8n, validada con `odyssey_core.conversations._validate_request_detail`. **NO ejecuta el motor real de n8n**, ni autentica Cloudflare.
- El resultado original del runtime reporta dos escrituras Core reales: creación del Day `2026-10-15` y de la nota Maya. El Day contiene literalmente el hecho con referencia implícita `(yo:`; el archivo Markdown del día y la nota de persona se reabren desde el repositorio real de la prueba.
- El resultado visible `Guardado`, el `request_detail` (8 SVG observados), los dos recibos Core y el conjunto `Ver 2 notas` se persisten primero mediante la ruta HTTP real `/conversation/assistant-response` y reaparecen en la conversación de `/conversation/main` después de una **recarga efectiva de Chromium**. El navegador abre Notes y muestra dos resultados de la consulta.
- Tras cerrar el navegador, un replay al RuntimeComposition con el **mismo request_id** devuelve `delivery_replayed=True`; compara literalmente todos los archivos Markdown con el snapshot físico anterior: **ninguno cambia** y `RecordedClient.rows` sigue vacío. E3 probado sobre las clases reales, no una función simulada.
- La API sintética solo acepta las operaciones necesarias en un puerto `127.0.0.1` asignado por el sistema y devuelve 403 a otras operaciones; no reenvía mensajes a DEV. El subprocess Node recibe una allowlist explícita de variables de entorno sin claves API.

## Ejecuciones en Raspberry Pi

`scripts/odyssey_browser_synthetic_p4.py --viewport mobile` y `--viewport desktop` han devuelto RC=0, `pass=true` cada uno, con vaults distintos. El script llama a `scripts/odyssey_browser_synthetic_p4.cjs` y usa Chromium/Puppeteer del caché local ARM64. Para este host se añadió al comando `LD_LIBRARY_PATH=/tmp/odyssey-p4-browser-deps/root/usr/lib/aarch64-linux-gnu`. Resultados JSON agregados, sin contenido de notas personales:

- `/tmp/odyssey-synthetic-browser-p4-mobile-final-20261019.json`
- `/tmp/odyssey-synthetic-browser-p4-desktop-final-20261019.json`

**En cada viewport**: una petición navegador, 1 nota de Day con fact y SELF, 1 nota nueva Maya, 2 recibos Core con SVG antes y después de reload, 1 texto de confirmación persistido, 1 botón detalle y 1 botón de notas persistentes, Notes mostrando 2 resultados, cero excepciones JS, un solo guardado de respuesta del servidor y replay E3 sin modificaciones físicas. La API local observó ~20 solicitudes privadas en total, incluidas numerosas consultas Notes, y rechazó dos operaciones no permitidas; estos números son del fixture y no una métrica de latencia real de DEV.

En la UI, la clase CSS `message-acknowledgement` se aplica durante el render del resultado inmediato, **pero no después del reload**: se conserva el texto y las pruebas de Core/notas, pero cambia el estilo porque el turno persistido no conserva el tipo de presentación `kind`. Se registra como deuda UX; no introducir una heurística por texto literal `Guardado` para fingir que el backend preserva ese atributo.

## Tests permanentes y límites exactos

`tests/runtime/test_browser_synthetic_p4_contract.py` incluye tres regresiones offline: proyección del resultado real a esquema válido, persistencia de dos turnos y sus metadatos, y rechazo de gráfico falsificado con una dependencia imposible. Queda incluido en `scripts/odyssey_cross_surface_gate.py`. El navegador real es una prueba de aceptación **opt-in**, pues requiere Chromium, Puppeteer y librerías del host; en la suite por defecto solo se ejecutan los tests Python deterministas.

**No es todavía la aprobación P4 ni E4/E5/E6.** Sustituye n8n por un adaptador HTTP de prueba y GPT por respuestas grabadas, no autentica Cloudflare, no utiliza el código actualmente desplegado en DEV (`b0fc9b21`), y no prueba variabilidad de modelos reales ni ejecuta la app completa contra su infraestructura real. Requisitos pendientes para habilitar la adopción: aislamiento efectivo OS/red/credenciales de Codex online, un E2E con n8n real y GPT real contra identidad/vault específicamente sintéticos en DEV (y luego sesión de navegador autenticada), readback multi-app y gráfico/latencia con varios casos.

## Cierre y resultados del gate

El gate oficial ejecutado DESPUÉS de incorporar los tres tests de proyección informó **1159 Python PASS + 7 subtests PASS y 178 JavaScript PASS**; acceptance ledger: **18 invariantes/41 anclas**, resultado explícito `P4 DEV UNAUTHORIZED`. Ruff y formateo correctos, Chromium sintético pasó de manera separada en móvil y escritorio. Ninguno de estos resultados equivale a autorización para modificar DEV, PROD, Cloudflare o los datos personales.
