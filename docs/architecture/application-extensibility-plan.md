# Plan de continuidad: arquitectura híbrida y aplicaciones reutilizables

**Dirección aprobada por el usuario el 13-10-2026.** Este documento define el objetivo, los contratos deseados, las etapas, sus criterios de aceptación y las reglas de continuidad entre agentes/chats. **El estado vivo, el siguiente paso y el historial de ejecución tienen un único dueño: [Functional Roadmap](functional-roadmap.md), apartado «Seguimiento activo — DEV híbrido y extensibilidad».** No duplicar aquí indicadores de ejecución.

## Objetivo y motivación

Permitir incorporar Events, Projects y otras capacidades sin replicar la interpretación común, la resolución de identidades, el transporte de evidencias, la autorización de cambios ni la escritura canónica. Mantener la arquitectura Router híbrido → grupos semánticos → Temporal/aplicaciones → Core Planner/validación → persistencia Markdown; una aplicación debe aportar **solo** su semántica/lifecycle diferencial. Evitar transformaciones o parches específicos de frases del corpus. Adoptar Clean Architecture **incrementalmente**, sin refactorización global ni bloqueo preventivo de DEV.

## Prioridad aprobada el 14-10-2026 — consolidar antes de seguir ampliando casos

El usuario confirma como **orden obligatorio entre chats/agentes**, sustituyendo la secuencia abierta anterior: **(1) finalizar sólo las correcciones E1 ya detectadas** (atribución genérica del actor implícito, relación actor/fact en el gráfico, progreso y diagnóstico de extremo a extremo, recibos/readback e idempotencia), **(2) ejecutar E2 — contrato común de contexto**, **(3) ejecutar E3 — puerta común de mutaciones**. Sólo después retomar una campaña extensa de pruebas manuales y E4/E5. No cambiar la arquitectura híbrida aprobada ni usar Clean Architecture como excusa para reescribir módulos: separarla incrementalmente mientras se trabaja en E2/E3.

**Criterio de trabajo ante cada fallo:** clasificar antes de modificar el código si pertenece a interpretación semántica, contrato/transmisión entre etapas, implementación local o representación/telemetría. Para fallos de contrato corregir el mecanismo compartido y probar **todos los consumidores**, no el caso textual concreto; evitar excepciones por frase, idioma, nombre, ID, verbo o número fijo de entidades. Conservar la evidencia de origen y los rechazos seguros.

**Gates transversales de E2/E3:** verificar que no desaparecen identidades verificadas ni relaciones, que ninguna hipótesis hereda autoridad sin prueba, que todas las mutaciones pasan por las mismas garantías de autorización, referencia, concurrencia, idempotencia, recibo y readback, y que el resultado llega sin pérdida runtime→n8n→web (etapas, coste cuando exista, gráfico y donut). Tests deterministas + adversariales/multilingües + end-to-end con datos desechables y App ficticia; aceptar de forma explícita incertidumbre semántica en vez de fabricar certezas. No declarar terminada una etapa sólo por suites aisladas ni prometer ausencia total de errores de modelos.

**Alcance inmediato:** esta decisión actualiza el planning, NO autoriza deploy, merge, escrituras sobre datos reales ni refactorización completa. El estado operativo y el próximo paso exacto se mantienen exclusivamente en Functional Roadmap.

## Evidencia de partida (auditoría de lectura, 13-10-2026; no sustituye la validación DEV)

- `odyssey_core/materialization.py` y `odyssey_core/persistence.py` ya centralizan mecánicas canónicas de creación, actualización y eliminación; `odyssey_core/application.py` proporciona el recorrido ordinario de preflight/ejecución. **No existe aún una única puerta de entrada de mutación con exactamente las mismas garantías para todos los casos**.
- `odyssey_apps/tasks/mutations.py` reutiliza `materialize_create` y `materialize_update` para acciones directas; `odyssey_apps/tasks/work_sessions.py` llama a `create_entity`, `update_entity`, `soft_delete_entity`. Esta diferencia puede ser legítima por semántica, pero las garantías transversales deben poder verificarse sin duplicación.
- `odyssey_core/domain_interpretation.py` contiene un contrato reutilizable (`DomainInterpretation`, `DomainEvidence`); `odyssey_apps/tasks/scoped_evidence.py` contiene `TaskScopedEvidence`, y `odyssey_runtime/candidate_route_dispatch.py` tiene adaptación específica de Task y handoffs de fecha/sujeto/evento. Falta verificar que una nueva App no exige editar el despachador central en cada ampliación de contexto.
- `odyssey_apps/tasks/planning.py` (`TaskCorePlanner`) modifica `RequestPlan` y construye `KnowledgeUnit`/referencias; tensiona el invariante de AGENTS.md que reserva esas decisiones genéricas a Core. Debe revisarse la propiedad semántica, sin romper el comportamiento de Tasks.
- `odyssey_core/candidate_sequential_contacts.py` conserva validación gramatical histórica usada por recorridos no híbridos; no copiarla al híbrido. `odyssey_core/candidate_continuation_guard.py` valida una frase concreta para un piloto F14/F27: no es contrato general ni debe activarse como si lo fuera.
- La rama de trabajo había registrado 25/27 escenarios totalmente resueltos y 2 ambiguos correctamente pendientes, con 3039 tests correctos, 80 skipped y 10 fallos históricos según el último log; **no son resultados de DEV**, y no justifican afirmar que la continuación conversacional ya está conectada a la UI.

## Principios de diseño obligatorios

1. **Un solo dueño por decisión**: Router plantea hipótesis ancladas a la fuente; Temporal devuelve evidencias temporales verificables; las Apps interpretan únicamente intención y reglas propias; Core determina identidades, hechos, destino, permisos de mutación y persistencia.
2. **Contexto común sin autoridad implícita**: un futuro contrato tipado de ejecución puede transportar fuente original/fragmento/procedencia, candidatos y dependencias, evidencias temporales, identidades verificadas o pendientes, contexto relevante y control de ejecución. Los campos son opcionales y limitados; cada consumidor elige qué usa. No basta que una App reciba un ID o una pista del Router para que pueda escribir.
3. **Una puerta común de mutación canónica**: la misma frontera debe proporcionar garantías de validación de esquema, targets, concurrencia/estado anterior, referencias, autorización, historial, idempotencia donde corresponda y lectura posterior. Puede exponer casos de uso distintos; **un checkbox determinista no debe llamar al LLM** y las Work Sessions pueden tener reglas propias.
4. **Extensión por composición/registro**, no herencia forzada: agregar una App no debería requerir ampliar una cadena de `if capability_id == ...` o reconstruir los mismos handoffs en su interior.
5. **Nada de reescritura**: factorizar solo duplicación demostrada; preservar límites de confianza intencionadamente duplicados, rendimiento y vault local-first. Sin LangGraph, nuevo servicio, broker ni base de datos.
6. **Corrección verificable**: ningún test concreto autoriza un parche de nombre, verbo, orden o número fijo de participantes. Tests generales de diferentes formas y tamaños, replay de casos reales y readback físico de Markdown.

## Etapas y definición de terminado

### E1 — DEV seguro para pruebas del usuario (primera prioridad)

- Revisar la rama/PR y la diferencia contra el runtime DEV existente; preparar incorporación controlada del híbrido sin tocar PROD ni vaults reales sin autorización.
- Cablear solo funciones verificadas. F14/F27 son pendientes por ambigüedad real: la selección autenticada y su continuidad deben validarse **de extremo a extremo en DEV**, no asumir que una prueba aislada del guard equivale a UI funcional. El guard de frase fija continúa siendo piloto, no solución general.
- Mantener Planner Core en GPT-5.6 durante esta etapa salvo nueva decisión explícita. Comprobar prerequisitos, compatibilidad y límites de la recuperación de contexto (>5000 Notes se sabe limitado en el hint scanner experimental).
- **Aceptación**: tests/gates de despliegue, verificación de versión efectiva DEV, capturas seguras de escrituras/pending en datos de DEV desechables, lista reproducible de casos para el usuario. El usuario realiza pruebas reales antes de convertir observaciones en nuevos compromisos de arquitectura.

#### E1.x — Independencia semántica de Router: contrato v6 experimental en rama, NO desplegado

**Implementado en rama tras la instrucción del usuario de generalizar (14-10-2026):** Router v6 opt-in emite JSON version 2 con semantic_relations por candidato (independent_assertion, attribute_of, purpose_of, condition_of, shared_predicate, unresolved), parent_unit referido sólo a candidato anterior y evidence que debe repetir una cita literal del propio candidato. Ningún valor de salida concede autoridad de escritura o de identidad. Router v1-v5 y el comportamiento de DEV/PROD no se alteraron. Validador de esquema cerrado y revalidación independiente en el compilador. V2 conserva juntos candidatos no demostrablemente separables en una misma cláusula, aun cuando el modelo marque independent_assertion, y exige predicado propio + límite de oración/fecha local antes de separar. Si agrupar mezclaría mutaciones Task/Core u operaciones Task incompatibles, falla cerrado.

**Traza pura creada, NO aún expuesta por n8n/web:** candidate_decision_trace devuelve hash del texto, offsets, IDs, roles, relaciones propuestas, asignaciones de ruta y códigos de validación; no conserva textos personales completos ni justificaciones libres o razonamiento privado. Falta instrumentar su exposición únicamente en DEV con alcance de actor/conversación, retención acotada y contrato runtime->n8n->web.

**Pruebas realizadas:** 3.092 passed, 80 skipped, 10 fallos históricos sin variación en la suite global antes de añadir cinco variantes positivas extra (validadas focalmente después); pruebas v6 multilingües/adversariales y 4 llamadas reales a Router solo: 3 aceptadas estructuralmente (incluidos dos hechos fechados, propiedades compartidas y una Task con hecho), 1 rechazada sin escritura por referencia interna no demostrada. Ninguna llamada escribió en vault. Este resultado NO constituye prueba semántica exhaustiva de Core.

**Revisión semántica independiente de Core antes de escribir (14-10-2026; implementada opt-in, NO integrada en DEV):**

- `odyssey_core/source_boundary_review.py` define `CoreSourceBoundaryInput` y `CoreSourceBoundaryReview` correlacionados por hash del mensaje original y hash de la partición, con índices, roles/etiquetas y texto fuente completo. El revisor `OpenAICoreSourceBoundaryReviewer` usa **GPT-5.6 low**, `store=False`, JSON de decisión cerrado `accept / revise / needs_attention`, índice y motivo de un enum reducido. Nunca propone notas, hechos, destinatarios ni cambios a Markdown. Modelos distintos y nuevos tipos de App no implican copiar el revisor a cada fase.
- `odyssey_runtime/candidate_route_dispatch.py` lo solicita **antes de Temporal, Planner, Tasks o Writer** sólo si el contrato Router es v6 y hay al menos dos rutas. Si sólo existe un grupo, las revisiones normales de Core/Planner/cobertura siguen siendo obligatorias sin llamada extra. Si el revisor está ausente para varias rutas, falla cerrado sin efectos.
- Para `revise` se envía a Router únicamente el índice problemático y motivo enumerado, jamás contenido de notas ni una explicación libre. Se admite **una sola llamada adicional a Router** con el mismo mensaje original. Se revalida y recompila todo, y, si vuelven a quedar varias rutas, se repite una revisión Core. **Nunca más de 2 propuestas Router y 2 revisiones Core en total.** Si Core vuelve a objetar, si algo falta o cambia el texto, `needs_attention` sin ninguna escritura. Si Core aprueba, esto NO sustituye al Planner ni a la verificación semántica candidato↔hecho ni al readback canónico existentes.
- Coste incremental: cero llamadas de revisión de límites para una sola ruta; una llamada de Core GPT-5.6 low para varias rutas en caso normal; sólo ante rechazo una segunda Router y potencialmente segunda revisión Core. No añade una IA detrás de cada IA ni validación global después de escribir.
- Tests provider-free comprueban las tres decisiones, hashes alterados, esquema cerrado, ausencia de Writer ante error, desactivación si falta revisor, un único reintento y conservación de la versión v5 anterior. Suite Python completa al cerrar este bloque: **3127 passed, 80 skipped, 10 fallos históricos invariables**. Prueba real sólo con frases sintéticas: Core detectó un adjetivo/finalidad como `DEPENDENT_SOURCE_FRAGMENT`; al reenviar ese motivo acotado, Router propuso dos candidatos relacionados que el compilador unió en **un** grupo, preservando la fuente. Una segunda consulta real aprobó dos oraciones independientes con `boundary_index=0`. Un primer rechazo por el modelo de un `accept` con índice mal formado se corrigió **aclarando el contrato del prompt, sin relajar su validador**.

**Límite explícito:** es una revisión de SEGMENTACIÓN, no un verificador infalible del significado de cada plan; si Core detecta un fallo más tarde en la comprobación candidato↔hecho, debe bloquear la escritura correspondiente, pero **no** reabrir automáticamente Router tras posibles escrituras previas. Sigue pendiente convertir la traza de revisión y coste en telemetría autenticada runtime→n8n→web y validar a fondo la variabilidad, referencias internas y los reintentos con IDs repetidos. La composición DEV continúa en v5 y no proporciona todavía el revisor v6; NO desplegar sólo por pasar estas pruebas locales.

**Falta para despliegue:** revisar semánticamente de forma independiente las divisiones propuestas y su efecto en Core N:M, cláusulas causales y referencias internas; integrar la traza en detalles técnicos con privacidad y estabilidad de esquema; tests de variabilidad, de ida/vuelta del progreso/graph y de idempotencia de reintentos con el mismo request ID. Probar sin cambiar hechos del usuario en DEV antes de activar v6. El contrato no sustituye a Planner/Writer.


**Motivo observado:** en n8n una ejecución de «Hoy he comido una pera roja para probar el indicador de progreso de Odyssey» se dividió en tres rutas, incluyendo «roja» y «para probar...». El esquema actual de Router v5 sólo demuestra que las citas son literales y tienen roles; no certifica que una unidad forme una afirmación autónoma. El compilador puede convertir candidatos sin dependencia explícita en rutas separadas. La propuesta JSON exacta del modelo en aquella ejecución NO se conserva: el adaptador devuelve los candidatos ya validados y la API usa store=False; n8n guardó sólo las rutas y errores.

**Contrato a implementar en modo opt-in antes de desplegar cambios de segmentación:**

- Distinguir candidato para análisis de hecho independientemente ejecutable. Router puede aportar etiquetas tipadas de relación con la afirmación principal: independent_assertion, attribute_of, purpose_of, condition_of, shared_predicate, unresolved, con vínculo a candidato padre y cita exacta. No solicitar ni almacenar razonamientos privados; las etiquetas tampoco autorizan escritura.
- Core/compilador debe validar evidencias y límites por separado. Si una unidad no puede acreditarse como afirmación independiente, interpretarla con su contexto fuente completo o bloquearla de forma explícita; no usar una lista cerrada de nombres, adjetivos o conectores. Conservar hechos independientes, fechas, Tasks y herencias legítimas del corpus.
- Conservar en DEV una traza corta y versionada: hash de la fuente, modelo/revisión, candidatos con ID, clase, cita/offsets, roles/relación propuesta, grupo asignado y decisión del compilador (group/split/reject) con motivo de validación. Es evidencia de entradas/salidas observadas, NO razonamiento interno. Respetar límites de tamaño, retención, actor/conversación autenticados y ausencia de secretos. Exponerla sólo en detalles técnicos; validar toda ampliación simultáneamente en runtime, n8n y navegador para no repetir gráficos vacíos.
- Gates: propuestas adversariales sintéticas multilingües, modificadores, finalidades, contraste, acciones independientes, varios días, Tasks y pronombres; tests deterministas congelados y varias ejecuciones reales SIN escritura; readback físico, no degradación del gráfico, y garantías de idempotencia.
- Contrato separado para fallos y reintentos: el mismo delivery ID produjo en n8n una respuesta failed y una completed bajo ejecuciones distintas porque el fallo previo no quedó conservado como resultado autoritativo. Prohibir reejecución silenciosa que pueda duplicar una escritura.

No asumir que añadir ejemplos o subir reasoning asegura corrección. El guard experimental ec2d2ba todavía NO cubre de forma general cláusulas de finalidad y permanece sin deploy.

### E2 — Contrato de contexto entre etapas (después del primer ciclo de DEV, o antes si un fallo real lo exige)

- Inventariar información y propiedad de Router, Temporal, Core, Task, Calendar y próximos Events. Diseñar un único contrato tipado/versión mínima para fuente, evidencias de fecha, entidades, dependencias, pendientes y correlación; conectar sin transformar hipótesis en autoridades.
- Reutilizar o evolucionar `DomainInterpretation`, los carriers y los verificadores actuales; no crear un segundo sistema paralelo.
- **Aceptación**: pruebas de contrato con Task/Calendar/Core y una App ficticia; agregar datos tipados de una capacidad sin modificar el resto; tests de provenance, frescura, ambigüedad, lectura incompleta y negativas.

### E3 — Puerta de mutación compartida

- Inventariar rutas de chat/Core, TaskDirectMutation, Work Sessions, Calendar y cualquier API de edición de Notes. Separar reglas de dominio de garantías de persistencia comunes; hacer que la App invoque casos de uso Core apropiados.
- Corregir la responsabilidad de `TaskCorePlanner` para que las transformaciones genéricas de planes/referencias vuelvan a Core. No forzar escritura con LLM en operaciones directas.
- **Aceptación**: matriz de garantías por tipo de operación, pruebas de revisión concurrente, identidad ambigua, enlaces, lectura posterior, rollback/errores e historial; regresión de todos los recorridos afectados.

### E4 — Retirada controlada de excepciones históricas

- Localizar y clasificar validadores por evidencia, compatibilidad y uso real. Sustituir la continuación F14/F27 de frase fija por revisión de fuente general **antes** de exponerla ampliamente; no borrar centinelas de regresión.
- Desmontar rutas legadas solo cuando su reemplazo preserve contratos, pruebas y rollback. No cambiar ejemplos congelados para hacer pasar los tests.
- **Aceptación**: no hay ramas ejecutables que decidan por nombres/frases/IDs de prueba; suite de equivalencias morfológicas, varios tamaños de grupo y pronombres/correcciones adversariales, con readback canónico.

### E5 — Events como prueba de extensibilidad

- Events aporta intención y lifecycle de eventos. Reutiliza el contrato común, Temporal, Core para entidades/target/escritura y Calendar para representación; no introduce su propia persistencia de conocimiento.
- **Aceptación**: crear/editar/cancelar un Event con tiempo, participantes y referencias existentes desde chat y/o UI según contrato funcional Events; tests E2E y de no regresión. Añadir Events sin copiar infraestructura Task, ni añadir lógica Events específica en Router/Core salvo extensión genérica probada necesaria.

### E6 — Clean Architecture incremental y consolidación (continuo)

- En cada módulo tocado separar dominio/casos de uso/puertos/adaptadores cuando reduzca acoplamiento **demostrado**. Después de Tasks/Events, realizar el checkpoint de mantenibilidad acotado que prevé `development-pipeline.md`, antes de escalar a más aplicaciones.
- **Aceptación**: menos puntos de cambio al añadir una capacidad, límites de dependencia probados, documentación coherente, mismas garantías y métricas sin regresión. Nunca declarar una gran migración Clean Architecture como requisito para DEV.

## Fuera de alcance y decisiones pendientes

- Fuera de alcance inmediato: reescritura total, plataforma genérica de plugins, cambios de proveedor/modelo, alteraciones de n8n/DEV/PROD por este documento, acceso al vault real, nuevas infraestructuras.
- E2/E3: elegir la mínima forma definitiva del contrato y la puerta de mutaciones **después del inventario y challenge arquitectónico**, no fijar APIs finales solo por este diseño.
- Events: conservar el contrato funcional ya existente en `future-events-calendar.md`; resolver diferencias reales con el usuario antes de programar comportamientos nuevos.

## Protocolo de actualización y continuidad entre chats

Al **comenzar** cualquier chat/agente de Odyssey: (1) localizar el worktree correcto y leer `AGENTS.md`; (2) consultar el bloque «Seguimiento activo — DEV híbrido y extensibilidad» de `functional-roadmap.md`; (3) leer este plan y los contratos enlazados de la etapa activa; (4) verificar `git status`, `git log`, PR y estado DEV **antes de afirmar hechos**; (5) comunicar en español «hecho / falta / próximo paso / bloqueadores», sin pedir al usuario que reconstruya el contexto.

Al **terminar cada paso sustancial**, en la misma unidad de trabajo: actualizar **primero** el estado canónico y el próximo paso del roadmap; registrar fecha, rama/commit/PR si existen, archivos o límites modificados, tests/comandos con resultado, estado DEV/PROD, bloqueadores y decisión de continuación; enlazar en este plan solo si cambia un criterio de arquitectura. Un test pasado no implica deployment ni un commit implica revisión humana. Si queda trabajo sin verificar, registrarlo como pendiente, no como completado. Al cerrar una sesión sin cambios, no agregar notas vacías. No sobreescribir historia previa; mantener checkpoints compactos y referencias a evidencia.

El agente del próximo chat debe buscar estos documentos en **la rama/worktree indicada en el roadmap**, porque otras ramas pueden tener documentación más antigua. No depender de la memoria de ChatGPT ni de poder recuperar el chat anterior. Los commits locales no equivalen a GitHub remoto; reportar explícitamente si no se hizo push.
