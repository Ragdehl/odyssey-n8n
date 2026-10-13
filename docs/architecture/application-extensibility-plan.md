# Plan de continuidad: arquitectura híbrida y aplicaciones reutilizables

**Dirección aprobada por el usuario el 13-10-2026.** Este documento define el objetivo, los contratos deseados, las etapas, sus criterios de aceptación y las reglas de continuidad entre agentes/chats. **El estado vivo, el siguiente paso y el historial de ejecución tienen un único dueño: [Functional Roadmap](functional-roadmap.md), apartado «Seguimiento activo — DEV híbrido y extensibilidad».** No duplicar aquí indicadores de ejecución.

## Objetivo y motivación

Permitir incorporar Events, Projects y otras capacidades sin replicar la interpretación común, la resolución de identidades, el transporte de evidencias, la autorización de cambios ni la escritura canónica. Mantener la arquitectura Router híbrido → grupos semánticos → Temporal/aplicaciones → Core Planner/validación → persistencia Markdown; una aplicación debe aportar **solo** su semántica/lifecycle diferencial. Evitar transformaciones o parches específicos de frases del corpus. Adoptar Clean Architecture **incrementalmente**, sin refactorización global ni bloqueo preventivo de DEV.

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
