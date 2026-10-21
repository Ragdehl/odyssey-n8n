# E4 v6 — remediación de la auditoría v5c (21-10-2026, rama aislada)

## Dictamen origen y causa

Job `e4-plural-v5c-full-audit-20261021` sobre `b08451b`:
**Generality FAIL, Quality FAIL, Testing FAIL, Performance BLOCKED**;
364.497 tokens CLI reportados. No confundir fallos con aprobación.
Generality halló una anáfora de Task/Project capaz de escoger una de dos
entidades, y advirtió de un conjunto finito que omitía otro grupo Core.
Quality aceptaba un conjunto sin cardinal explícito («ellos»).
Testing detectó que el gate vivo filtraba Personas esperadas antes de
contarlas, por lo que una persona inventada adicional no causaría FAIL.
Performance carece de SLA y medición representativa de E4/FastEmbed.

## Remediación aplicada

1. `dependent_group_evidence.py`: la unicidad de la elección anafórica
   de una sola arista se exige para **todo tipo canónico**, no solo Person.
   Se reusa la misma comprobación contra recibos de Core físicamente escritos.
2. `dependent_group_graph.py`: una cohorte finita no puede omitir ningún
   grupo anterior Core; los casos de varios grupos sin cobertura exhaustiva
   quedan bloqueados antes de escribir, sin adivinar nombres.
3. `tasks/dependent_target.py`: una Task pluripersonal necesita cardinal
   finito explícito e igual al número completo de personas tanto en los
   dos revisores semánticos como en el carrier previo a Writer.
4. `odyssey_e4_live_browser_n8n.py`: el inventario físico debe tener solo
   SELF y exactamente las personas previstas, sin extras ni duplicados.
5. Regresiones adversariales: dos Tasks físicas y anáfora singular,
   tres grupos Core con una omisión, pronombres abiertos y persona
   inesperada en el gate. Conservados E2/E3 y casos plurales correctos.

## Evidencia verificada en la Raspberry

- 89 pruebas focales PASS al añadir las regresiones.
- Gate transversal: **1.515 Python PASS + 179 JS PASS**, exit 0,
  `/tmp/e4-v6-cross-20261021.json`, pytest/node exit 0.
- Ruff lint PASS y formato aplicado; diff sin errores de whitespace.
- 1.ª llamada real sintética al navegador/n8n/GPT:
  `FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE`, navegador FAIL,
  0 escrituras nuevas; no se etiqueta PASS.
- 2.ª llamada real sintética por unit temporal `systemd --user`
  con credentials EnvironmentFile (sin exponerlas), salida 0:
  navegador autenticado PASS, n8n y GPT real, 2 personas + 1 Task,
  4 recibos, enlaces/backlinks, recarga y replay E3 inmutable.
  `/tmp/e4-v6-diag-live-20261021.log` (sin claves); duración total
  ~91,77 s, no equivale a p95.
- No se tocaron notas privadas, DEV ni PROD; no se hizo deploy/merge.

## Pendientes de aceptación

**E4 aún no aprobada.** Un nuevo commit de v6 precisa dictámenes
independientes sobre el SHA exacto; no reutilizar aprobaciones de v5c.
Performance necesita presupuesto acordado para latencia/CPU/RAM/indexado,
cold/warm FastEmbed disponible y distribución representativa p50/p95 de la
ruta real completa, no solo consulta a 250 notas ni una ejecución viva.
La suite global tiene nueve fallos de benchmarks reproducibles previos
que no deben marcarse verdes. El donut en browser demuestra renderizado
a 0%, no progresión porcentual. Cloudflare Access DEV sigue pendiente
antes de cualquier aceptación operativa/despliegue.

El cap local de Codex observado el 21-10 en `pace` es 1.428.571
tokens/día frente a 2.245.354 ya reportados. Este proxy no prueba
cuota real de la cuenta ni habilita auditoría nueva por sí solo.

## Refuerzo posterior al commit 001b778

La prueba de tres predecesores incluyó tres escrituras reales de Persona por Core en bóveda sintética y un grafo finito manual que omite uno. Para que incluso ese uso directo del carrier quede fail-closed, el handoff físico de E2 repite el veto estructural y rechaza antes del consumidor; **23 pruebas físicas de handoff PASS**, sin crear Task. Se debe emitir un commit nuevo y reejecutar la batería transversal sobre él.
