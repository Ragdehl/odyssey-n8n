# E5 — primer ensayo con IA realmente invocada (20-10-2026)

## Acceso al proveedor
Credencial ya autorizada en `/home/ragdehl/.config/odyssey/secrets.env`, inyectada **solo** en una unidad efímera `systemd-run --user --wait --collect --pipe -p EnvironmentFile=...`. No se imprime ni copia la clave al repositorio; la terminal Remote Desktop ordinaria no tiene `OPENAI_API_KEY` por diseño (AGENTS.md). El usuario autorizó expresamente nuevas pruebas de GPT real para E4 y E5 sin pedir de nuevo las credenciales. Sin DEV/PROD, ningún vault personal, red a n8n ni desplegar productos nuevos.

## Resultado de la prueba
Script `scripts/e5_live_intent_probe.py`, modelo **gpt-6-luna**, respuestas generadas AHORA mediante API Responses, `store=false`, `max_retries=0`, esquema JSON estricto y `max_output_tokens=1200` por petición. **No se utilizaron respuestas grabadas**. Cada salida se analizó mediante el validador real de interpretación E5 y el contrato `DomainInterpretation`; los textos son sintéticos.

| Escenario | Resultado del modelo | Oracle | Validación |
|---|---|---|---|
| Foto de clase el 22 de noviembre de 2026 | CREATE | CREATE | PASS |
| Campamento del 4 al 8 de julio 2027 | CREATE | CREATE | PASS |
| Piscina cada lunes hasta el 20 de junio 2027 | CREATE | CREATE | PASS |
| Cambiar reunión de martes a jueves | UPDATE | UPDATE | PASS |
| Cancelar excursión | CANCEL | CANCEL | PASS |
| Consultar eventos del colegio en noviembre | QUERY | QUERY | PASS |
| «Mañana tengo que llamar a Julia» (solo Task) | ABSTAIN | ABSTAIN | PASS, no usurpación Events |
| «El viernes hay excursión y tengo que preparar la mochila» (mixto) | ABSTAIN | ABSTAIN | PASS, se requiere división Router |
| «Hay dos excursiones el viernes. Cambia una al lunes» (referente incierto) | ABSTAIN | ABSTAIN | PASS, no seleccionar por descarte |

**9/9 respuestas reales PASS** en una sola ejecución, alrededor de 1,62–3,11 s por llamada. Artefacto bruto estructurado del ensayo: `/tmp/odyssey-e5-real-interpretation-20261020.json` en la Pi, sin datos privados. Contrato E5 extendido con `ABSTAIN`, prohibición de evidencia de mutación en abstención y tests negativos.

## Lo que NO certifica
Este es el **primer ensayo REAL del intérprete E5, todavía PRE-INTEGRACIÓN**. La fuente de E5 aún no está conectada al Router/producto, n8n, Temporal real, Writer, Markdown, Calendar ni navegador. Por tanto **no es E2E de Events** y no autoriza que el usuario use E5 ni merge/deploy. La propuesta de prompt será sometida a nueva evaluación al conectar la producción; un solo resultado por caso no mide variación estocástica del modelo. No se midieron costes API ni p95. Toda E5 con GPT real, navegador, n8n y Writer sigue exigida por [Matriz de aceptación](e5-acceptance-matrix-20261020.md).
