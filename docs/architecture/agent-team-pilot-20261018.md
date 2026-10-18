# Odyssey — piloto de equipo de agentes (18-10-2026)

## Decisión de trabajo

No esperar a P6. Separar *método de desarrollo* de *contratos de Odyssey*: no rediseñar Task, Event, Calendar, Time ni el mecanismo de apps de usuario como condición para probar el método. El proyecto ya define el límite correcto en `AGENTS.md` y `application-extensibility-plan.md`: Apps especializadas emiten interpretaciones tipadas y dependen de Core para propiedad, identidad, source provenance, fechas comunes, E2/E3 y Writer. Una app fabricada con IA debe poder superar automáticamente ensayos generativos de contratos y permisos sin incluir una lista cerrada de tipos de nota o un test escrito para cada app futura. La prueba semántica de dominio no se garantiza con validación de schema y requiere evaluaciones controladas antes de otorgar capacidad WRITE. Futuros bloques no confiables se ejecutarán en aislamiento y con permisos mínimos.

## Entorno comprobado

Raspberry Pi Debian 13 ARM64; RAM física 4 GiB, swap 2 GiB; MemAvailable ~2,1 GiB en pruebas. CLI `codex-cli 0.162.1`, ChatGPT login existente, multi-agent disponible. Git `origin` ya conectado y no modificado. Rama de función `feat/light-router-poc-20261016`, commit P4 base `4a93c6b`. Producción y DEV no se han desplegado ni conectado al supervisor.

## Piloto implementado

- `scripts/odyssey_agent_cycle.py`: supervisor determinista persistente con comandos `doctor`, `plan`, `run --live`, `status` y `stop`. El registro de prueba es `p4-agents-pilot-20261018` con estado `planned` en `/home/ragdehl/projects/.odyssey-agent-runs/p4-agents-pilot-20261018/status.json`. No existe ninguna ejecución del bucle completo.
- Cinco roles en `ops/agent-team/`: `builder` (único editor), `generality` (revisión de no casos específicos/Apps futuras), `quality` (seguridad/código), `testing` (real QA) y `performance` (latencia, CPU, RAM, swap). El supervisor es una máquina de estados, **no** otro LLM capaz de aprobarse por autorreferencia.
- Ejecutar secuencialmente (máximo un Codex simultáneo), sandbox read-only para auditores y workspace-write para Builder, `--ignore-user-config` sin MCP de n8n, filtrado de variables sensibles, directorio Git worktree separado `agent/<job>`, mutex global, vigilancia cada dos segundos, cancela ante STOP, timeout 20 min/role, RAM disponible bajo 650 MiB; hasta tres iteraciones de reparación. Emisión de dictámenes JSON strict verificables, logs de tests y evidencias por ronda. Ningún deploy/merge/push bajo el supervisor. Este conjunto ayuda pero **no sustituye una cuenta o contenedor Linux verdaderamente aislado** para autonomía con código no confiable.
- Gate determinista exige suite `odyssey_cross_surface_gate`, acceptance ledger y Ruff. Cuatro revisores independientes actúan en sesiones distintas. Fallo reparable → Builder recibe dictámenes y puede corregir; `blocked` por evidencia externa → STOP sin bucle absurdo; PASS del código → `reviewed_browser_gate_pending` y **no** `ready_for_user` hasta E2E browser/n8n/Writer/graph auténtico.
- `tests/runtime/test_agent_cycle_supervisor.py`: **10 comprobaciones PASS**, simulación del supervisor y sus revisiones, rechazo de IDs inseguros, planificación no viva, reporte persistente, bloqueo de browser y stop ante auditor bloqueado. Gate transversal **1056 Python + 174 JavaScript PASS** y 7 subtests Python; ledger de aceptación 18 invariantes y 41 anclas PASS, pero P4 DEV permanece sin autorización por E2E real pendiente.

## Primera auditoría real Codex (read-only)

Se invocó realmente el CLI contra la rama, con prompt del auditor generalidad y JSON schema estricto; **completó en 62,01 s, exit 0, no modificó archivos, verdict FAIL, tres bloqueadores**:

1. `odyssey_core/dependent_group_graph.py` limita capabilities a `core/tasks`; no cubre futuro registro de una App arbitraria.
2. `odyssey_runtime/whole_source_light.py` exige que toda arista Core→Tasks resuelva un objetivo Task, por lo que Person recién creada→Task CREATE no puede pasar por ese adaptador.
3. `odyssey_core/source_provenance.py`: `re.finditer` no descubre coincidencias solapadas (`aaa`/ `aa`), por lo que una evidencia literal ambigua puede validarse indebidamente. Confirmación directa en la Pi: `anchor_literal_evidence("aaa", "aa")` devolvió `SourceAnchor(start=0,end=2)` aunque hay una segunda aparición en offsets 1..3. Añadir prueba adversarial y reparar el algoritmo compartido, no un if por ejemplo.

La auditoría queda en `/home/ragdehl/projects/.odyssey-agent-runs/p4-agents-pilot-20261018/read-only-smoke/generality.json` y está referenciada desde el estado. **No se modificó P4** para arreglar las tres observaciones y no se autorizó ejecutar todo el pipeline en modo unattended. La detección del tercer punto es evidencia de valor incremental de la revisión independiente, no de cierre de P4.

## Flujo objetivo

Brief de feature → Build (Codex) → tests deterministas → Generalidad → Calidad/Seguridad → QA E2E → Rendimiento → hallazgos bloqueantes → reparación hasta límite → LIVE DEV (auténtico) → resumen de aceptación + usuario. Nunca afirmar éxito cuando falta n8n/browser, RAM/perf o identidad. Informes con fallos, cambios, coste/tokens si medibles, p50/p95 y nota de qué quedó sin comprobar.

**Móvil y avisos:** ChatGPT/Codex Remote permite dirigir sesiones sobre máquinas conectadas, y Codex Cloud permite tareas de código desde móvil con entorno GitHub publicado, según documentación oficial de octubre 2026. **No se ha verificado que la Raspberry aparezca en el móvil ni que este runner cree notificaciones de forma automática.** A corto plazo el archivo JSON ofrece visibilidad en el repositorio remoto y ChatGPT puede consultarlo en este chat cuando el usuario pide un estado, pero no lo seguirá automáticamente en segundo plano. Próximo piloto: probar la vinculación Remote de esta Raspberry o montar notificación n8n read-only o GitHub CI tras elegir canal y permisos. No exponer status a internet sin autenticar.

## Siguientes pasos y límite de autorización

1. Incorporar este piloto en test suite/roadmap y mantener las pruebas de CLI en el gate transversal.
2. Probar una microfeature autocontenida en worktree aislado, primero como revisión en lectura y luego un único `run --live` **tras aislar la cuenta/entorno y establecer permisos**; no usar los datos de producción. Verificar reparación, cancelación, swap, límites, logs y no duplicados.
3. Conectar E2E auténtico de navegador y avisos al móvil; solo entonces aceptar automatización de funcionalidades completas y ciclos nocturnos.
4. Resolver bloqueadores genéricos P4 mediante el mismo ciclo, sin condicionales por Task o por frases, antes de DEV.

## Piloto real ChatGPT→revisores (18-10)

ChatGPT implementó el arreglo de solapamientos en el commit `c64ad6e` y lo entregó al supervisor (`--implemented-by chatgpt --against db83e1e`). El job `p4-chatgpt-overlap-review-20261018` omitió Builder Codex, ejecutó `cross_surface`, `acceptance` y `ruff` PASS y los cuatro especialistas en sesiones read-only aisladas. Generalidad: **PASS**; Calidad: **PASS**; QA: **BLOCKED** por navegador E2E real ausente y un test de no-write con segundo fact irrelevante; Rendimiento: **BLOCKED** por falta de benchmark real p50/p95 y presupuesto. El supervisor cerró en `blocked_external_evidence` / `ready_for_user=false`, sin deploy ni correcciones autónomas. JSON por rol bajo `/home/ragdehl/projects/.odyssey-agent-runs/p4-chatgpt-overlap-review-20261018/round-1/`.

Tras la auditoría, ChatGPT corrigió el test de rechazo para que tenga UN único fact con cita `aa` ambigua en `aaa`; 63 tests focales PASS. Se añadió un benchmark repetible en `benchmarks/source_provenance_v2_microbenchmark.py`, 1500 muestras/caso sobre Pi ARM64, de la comprobación literal antigua por regex vs nueva. P95 (ms): 4K único 0,00446→0,00478; 4K repetido 0,29437→0,00217; contexto único 0,00504→0,00691. El pico RSS del proceso pasó 30016→30528 KiB; no equivale a memoria total de Odyssey. Es un benchmark de UNA primitiva, NO prueba p95 de captura End-to-End. Los auditores QA/rendimiento **no se han vuelto a ejecutar después de esta corrección**, por lo que sus bloqueos no se declaran resueltos.

## Política revisada de bloqueos para futuras rondas

Tras ejecutar los cuatro auditores sobre el código ChatGPT, se distinguieron dos fuentes de rechazo simultáneas: deficiencias reparables localmente frente a la falta de navegador autenticado/permiso/medición externa. `review.schema.json` exige que cada finding tipado clasifique `actionability=repairable|external`. El supervisor procesa errores reparables (o tests deterministas fallidos) y, si quedan intentos, reactiva Builder sin solicitar intervención al usuario, aunque otro auditor haya anotado un blocker externo. Si únicamente faltan evidencias externas, se detiene en `blocked_external_evidence` sin gastar más tokens; si se agotan las correcciones, `blocked_repair_budget`. CLI `run` devuelve exit 3 ante un bloqueo real; el estado JSON conserva la distinción entre fin de ejecución y aprobación. **21 tests de supervisor PASS; gate transversal 1077 Python + 174 JS PASS, siete subtests**, incluyendo doble bloqueo y segunda ronda, cuota de intentos y salida de shell. Esta política está testada de manera determinista, todavía NO validada con ejecución Builder Codex de escritura por falta de aislamiento Linux de la Raspberry.
