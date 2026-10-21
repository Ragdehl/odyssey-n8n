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
- Gate transversal: **1.516 Python PASS + 179 JS PASS**, exit 0,
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

## Verificación de la revisión final sobre bd0dc91 (21-10, tras congelar código)

- Se reejecutó la batería completa relevante del commit: **1.516 Python
  + 179 Node PASS**, ledger, Ruff y Markdown E2E determinista; resultado
  `/tmp/e4-v6b-cross-20261021.json`.
- Una nueva prueba viva de exactamente el mismo texto sintético
  (Chromium local autenticado → n8n real aislado → GPT) emitió
  `needs_attention`, código `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`,
  **sin escrituras y con gate browser FAIL**, log
  `/tmp/e4-v6b-final-live-20261021.log`. No hay evidencia del contenido
  exacto del dictamen modelo que explique el rechazo, y no se atribuye
  causalidad a la guarda de E2. El intento vivo precedente había pasado;
  esta variación **impide declarar estabilidad GPT**.
- La suite global pre-commit sobre esta familia de cambios completó
  **4.456 PASS, 80 SKIP, 9 FAIL históricos** (benchmarks congelados,
  presupuestos y hashes), no un full-suite PASS. El commit fuente con
  las guardas es `bd0dc91`.
- La auditoría independiente de cuatro especialistas sigue **SIN LANZAR**
  sobre v6: el pacing Codex local mostró 2.245.354 reportados hoy frente
  a cap 1.428.571; cuota real de la cuenta no observable. No se alteran
  supervisor, límites ni credenciales; sin DEV/PROD o deploy.

**Siguiente acción:** investigar las abstenciones vivas con telemetría de
rechazo acotada que no exponga mensajes privados, estabilizar las revisiones
semánticas sin reducir los vetos de seguridad; repetir piloto vivo, luego
cuatro auditores del SHA vigente y campaña de Performance.

## Investigación de la abstención GPT y corrección dirigida — 21-10-2026

Se recuperó el acceso remoto a Raspberry sin cambiar credenciales ni conectores.
El rechazo previo del commit `bd0dc91` solo conservaba
`FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`; ese código agrupa múltiples
salidas prewrite, por lo que **su causa exacta anterior sigue sin demostrarse**.

Se instrumentó únicamente una ejecución sintética efímera desde
`/tmp/e4_safe_trace.py`, con indicadores de Router, partición, cardinal,
revisiones y función/línea de abstención; sin claves ni datos de usuario
en la traza. Sobre la misma rama original, GPT vivo ahora aceptó el Router
Core+Tasks+Temporal, el split exacto, cardinal 2 y dos revisiones independientes
con dos personas. Chromium autenticado local + n8n offline aislado + GPT
+ Writer canónico + Markdown + recarga + backlinks + replay E3 pasó
(`/tmp/e4_safe_trace.log`). Esto demuestra **variabilidad**, no una
causa determinista del fallo anterior.

Se detectó una contradicción real en el contrato de particionado:
`DEPENDENT_TASK_PARTITION_PROMPT` describía un referente Person singular
aunque E4 exige también una Task propia con grupo finito de 2–8 Persons.
Se amplió la descripción de forma genérica (cohorte completa, una Task,
nunca selección parcial ni pronombre abierto). Además, una división inválida
ahora emite `dependent_partition_rejected` con tres booleanos no sensibles
y el código específico `DEPENDENT_SOURCE_PARTITION_UNVERIFIED`, antes de
cualquier escritura. No se retocaron la semántica Core, E3, los recibos
físicos ni el fail-closed de identidad.

Tras modificar el prompt, el MISMO E2E real sintético volvió a pasar,
incluidos **2 Person + 1 Task, 4 recibos visibles, 2 backlinks, 0 errores JS
y E3 replay byte-idéntico**, `/tmp/e4_safe_trace_postfix.log` (exit 0,
92,85 s). Los tests focales de prompt, negativo de particionado y
dependencia pasan **79/79**, Ruff PASS. No debe concluirse fiabilidad
estadística a partir de estas dos ejecuciones: la abstención anterior no
queda causalmente explicada y el resto de auditorías/Performance siguen
pendientes. Sin deploy, sin merge y sin notas privadas.

Gate transversal tras todas las modificaciones de esta sesión: `scripts/odyssey_cross_surface_gate.py`, salida 0, **1.516 Python PASS, 179 Node PASS y 7 subtests PASS**, registro `/tmp/e4-v7-cross-20261021.log`; Ruff PASS. Se conserva el historial de 9 fallos globales de benchmarks previos, no se declara la suite global PASS.
