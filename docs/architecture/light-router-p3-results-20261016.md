# P3 — contrato Core de mensaje íntegro y aceptación aislada, 16-10-2026

**Estado final: P3 contractual y persistencia AISLADA demostrados; activación en chat/n8n/UI sigue bloqueada. Sin cambios DEV/PROD.**

## Código

- `odyssey_core/whole_message_coverage.py`: contrato de fuente íntegra tipado. Conserva el digest de fuente y del plan, prueba cardinalidad 1:N por cita original unívoca, orden de hechos, fechas normalizadas, dependencias hacia hechos anteriores, scopes Core/Tasks y referencias simbólicas `{{ref:N}}`. Rechaza referencias duplicadas, participantes ausentes, Markdown inventado y citas no respaldadas. **Un review de IA nunca es autoridad de escritura.**
- `odyssey_core/whole_message_identity_guard.py`: preflight conservador contra duplicados cuando una mención parcial/alias coincide con una persona real. Un parecido no equivale a identidad. El nombre completo único se sigue resolviendo en el Writer existente. La resolución general de «Ana»→«Ana López» sigue pendiente: por ahora se bloquea de forma segura.
- `odyssey_core/whole_message_relationship_proof.py`: relación SELF autenticada por `SelfBindingRepository`, procedencia actual de un único fact Markdown mediante `RelationshipEvidenceProjector`, enlaces canónicos de todos los miembros y revalidación de hash/membresía antes de escribir. Es genérico: el span exacto de relación debe ser probado por la capa semántica y no se atribuye por un nombre.
- Las pruebas PoC siguen en `benchmarks/application_router/light_router_poc_20261016/`, no se han copiado a la aplicación ni se ha creado un Writer paralelo. La ruta desplegada conserva el antiguo Router.

## Campaña con IA REAL y 97 Notes DEV clonadas/destruidas

| Caso | Resultado |
| --- | --- |
| «Ayer hablé con Maya» | Escritura Core, Maya nueva, fecha de ayer y backlinks comprobados |
| «Hoy he conocido a Guillermo» | Reutiliza la persona existente |
| «Ayer cené con Maya y hoy he vuelto a hablar con ella» | Dos hechos en dos días, UNA Maya |
| «Hoy he hablado con Ana y Luis...» | Bloqueo correcto SIN modificaciones al faltar identidad confirmada de «Ana» frente a «Ana López» |
| «Hoy he conocido a Maite, mañana tengo que llamarla» | Nota persona + hecho + Task pendiente para mañana, mismo ID y dos backlinks |
| «Hoy compré pan y mañana compraré leche» | Dos hechos fechados, SIN inventar una Task |
| «Mis hijos fueron al parque, después comieron un helado y por la tarde vieron una película» | **3 hechos escritos** en Person SELF de prueba sin inventar fecha, con Cloe y Bruno acreditados por relación canónica y backlinks desde ambas notas; cero notas genéricas o personas nuevas |

La última prueba de «mis hijos» obtuvo revisión independiente nueva de GPT-5.6 y pasó el contrato Core (3/3 facts). En `p3_children_real_write.json` figuran exactamente 3 facts nuevos y readback/backlinks; la cifra de backlinks de Cloe y Bruno incluye sus otros enlaces que YA existían, no debe interpretarse como enlaces nuevos totales. El resto del recorrido grabó respuestas nuevas Router GPT-6 + Planner GPT-5.6 + revisión GPT-5.6. El 16-10 se verificó además el HTTP `GET /healthz` en runtime DEV y n8n (200), pero eso **NO implica que la nueva ruta haya atravesado n8n**.

## Campaña ampliada con 5 situaciones difíciles

`p3_extended_receipts.json` conserva resultados con Router y Planner nuevos, más revisor real. Todos detuvieron la escritura **sin mutaciones**, y las razones muestran tareas pendientes:
- `children_subject` en la ruta antigua del PoC, sin prueba familiar entregada al revisor: se bloqueó, mientras la nueva prueba separada P3 con prueba de relación válida sí guardó correctamente.
- `maite_variant`: coincidencia parcial Nora frente a Nora Test; bloqueo canónico necesario hasta disambiguación.
- `independent_apps`: preferencia sobre jazz SIN fecha sin una decisión autorizada de propietario; bloqueo hasta contrato Core de ownership.
- `gender_disambiguated`: Ana sin identidad canónica probada; no promover por deducción.
- `ambiguous_two_males`: pronombre «él» con Eric y Luis, aclaración necesaria; ninguna escritura.

No declarar 5 bloqueos como «5 fallos de IA»: son una combinación de abstenciones seguras y funcionalidades pendientes. El modelo puede equivocarse aun cuando el contrato estructural pase; se requiere investigación adversarial semántica antes de activar escritura real.

## Evidencia técnica y condiciones de despliegue

- Nuevo test `tests/core/test_whole_message_coverage_p3.py`: 31 comprobaciones de contrato, citas, fechas, permisos, referencias y manipulación adversa.
- `tests/core/test_whole_message_relationship_proof_p3.py`: 8 comprobaciones de re-grounding de grupos, actor autenticado y prueba que se vuelve inválida cuando cambia el Markdown.
- En el mismo entorno han pasado las suites de Core, runtime, Tasks, E2/E3 y UI indicadas en el roadmap. Ninguno de los tests web existentes cubre todavía la NUEVA ruta de P3 porque no está conectada a `RuntimeComposition`.
- **Sin deploy en DEV/PROD**. El commit de P3 es sólo código de contrato opt-in, pruebas y PoC.
- **P4 obligado:** portar el planificador íntegro y la revisión semántica del banco de pruebas a componentes productivos sin importar `benchmarks` ni `tests`; definir owner tipado de facts sin fecha y source digest + scopes; validar semántica negativa/condicional y alusiones, crear ejecución multi-App con E3 delivery/idempotencia, hacer índices verdaderos; probar llamadas nuevas completas HTTP+n8n+UI/graph+donut y rendimiento/CPU/memoria en sandbox DEV antes de autorizar activación. Aplicar gates de no duplicado, pruebas de parciales y rollback. **No pedir aún pruebas manuales al usuario.**
