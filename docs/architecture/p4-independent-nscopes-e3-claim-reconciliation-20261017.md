# P4 — N ámbitos independientes y reconciliación E3 de recibos confirmados (17-10-2026)

## Qué se ha implementado

1. La topología del Router `separable` debe coincidir elemento por elemento con todos los ámbitos exactos `Core/Tasks` validados por el revisor independiente. Cualquier grupo adicional, omitido, reordenado o marcado dependiente se rechaza antes de persistir.
2. En la fábrica productiva, la interpretación de cada grupo Tasks y su Temporal (cuando corresponde) se preparan antes de la primera escritura Core, bajo el instante del mensaje. El grupo Tasks posterior ejecuta la interpretación ya preparada mediante `execute_tasks` habitual. Sin segundo Router/TaskInterpreter para la misma operación, ni Writer distinto. Si la preparación falla, todo el mensaje se abstiene antes de cualquier WRITE.
3. Si un segundo Core necesita buscar contexto después de que un grupo anterior mutase Markdown, hay un refresco intermedio **incremental y estricto** de los IDs afectados. No se admite fallback a rebuild total en esta fase de ejecución; un fallo deja los resultados anteriores visibles como `partial`, sin ejecutar acciones restantes y sin reintento ciego. La actualización habitual al final permanece.
4. `LocalDeliveryResultStore.reconcile_confirmed_claim` solo elimina una reserva huérfana después de comprobar el recibo inmutable final y su fingerprint, con validación de claim, checksum, identidad y symlinks. Sin recibo terminal no libera el claim, no altera el vault ni reejecuta el Planner/Writer; continúa `unresolved_attempt`.

## Evidencia aislada

- `tests/runtime/test_p4_independent_mixed_scopes.py`: tres grupos Core→Tasks→Core con SELF y sesión física y `execution_flow` completo, replay byte-idéntico. Otro ensayo fuerza fallo del refresco antes del tercer Core y verifica `partial` durable, sin tercer hecho ni duplicados. Cuatro grupos con Task-only del último inválido quedan bloqueados prewrite. Se rechazan discrepancias de orden/topología del Router, Task preflight erróneo, ausente o incompatible.
- `tests/runtime/test_p4_e3_claim_forensics.py`: reserva sin recibo no reconciliable; recibo con claim huérfano sí puede limpiar la reserva sin escribir Markdown; fingerprint incorrecto y symlink se rechazan.
- Gate transversal final: **833 pytest PASS y 168 Node PASS**. Acceptance ledger: **15 invariantes, 26 pruebas ancla**. `ruff check` y formato de módulos cambiados PASS. Suite global: **3737 Python PASS, 80 SKIP, 52 subtests PASS y los mismos 10 fallos históricos congelados de benchmarks/precios**; ninguna regresión nueva.
- `scripts/p4_nscope_fresh_isolated.py`: **1/1 con GPT real** bajo `systemd --user` y EnvironmentFile protegido, nunca con secretos en el repo. El modelo propuso tres ámbitos independientes `core/tasks/core`; TaskInterpreter identificó una única `START_WORK_SESSION`; dos hechos se materializaron en SELF, una sesión real quedó vinculada a la Task y el replay del mismo ID no modificó ningún byte. Son datos sintéticos en `TemporaryDirectory`, sin navegador/n8n desplegado. Un acierto no demuestra estabilidad estadística ante expresiones nuevas.
- `tests/runtime/test_p4_dependent_factory_product.py`: con Tasks habilitada confirma la inyección de preparación Task y refresco intermedio estricto; sin Tasks, ambos adaptadores independientes permanecen desactivados.

## Restricciones que siguen bloqueando adopción

- N:M con **dependencia cruzada** entre hechos y Tasks, varios padres canónicos, pronombres ambiguos y operaciones entre sesiones requiere probar cada arista E2 (antecedente↔dependiente), todos los modelos prewrite y resultados parciales sin perder semántica. Se conserva el rechazo en el coordinador P4 para más de un antecedente y una Task dependiente.
- No se reconstruye un recibo de un claim sin resultado a partir de conteos de Notes: puede haber múltiples escrituras, llamadas parciales o operaciones sin marcador de fact. Hay que diseñar un manifiesto durable de operaciones con readback físico antes de habilitar recuperación automática postwrite.
- Core Planner de un grupo Task CREATE independiente aún puede planificar después de escrituras de hermanos. Esta etapa adelanta Task/Temporal, no todas las decisiones genéricas de escritura de Core; un error posterior da `partial` seguro.
- La prueba definitiva sigue siendo navegador autenticado → n8n real → GPT → Writer/Markdown → UI, con gráfico, donut e historial, usando vault sintético, sin alterar datos personales.
