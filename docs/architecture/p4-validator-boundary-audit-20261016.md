# P4 — Auditoría y consolidación de validadores heredados (16-10-2026)

## Qué se ha demostrado y qué no

El cambio E2/E3 no implica que **todo el código histórico** de interpretación desaparezca. Se verificaron **cinco componentes estrechos concretos** con importaciones efectivas en módulos productivos. El inventario reproducible está en `scripts/audit_semantic_validator_boundaries.py` y un test impide que aumenten sus consumidores silenciosamente. **No es un censo exhaustivo de todos los validadores** ni pretende demostrar que todos los caminos antiguos son correctos.

| Protección | Consumidores productivos directos verificados | Naturaleza | Decisión |
|---|---|---|---|
| `candidate_sequential_contacts.py` | `candidate_attribution.py`, `candidate_coverage.py` | Sintaxis española concreta, dos contactos consecutivos | Legacy activo: **aislar**, no extrapolar ni borrar sin reemplazo y regresiones |
| `candidate_multi_participant.py` | `candidate_attribution.py`, `candidate_coverage.py` | Dos personas explícitas con conjunción delimitada | Legacy activo: reemplazo posterior por evidencia N:M genérica |
| `candidate_scoped_handoff.py` | `candidate_scoped_planning.py` | Pilot de segmentación sintética y de fecha/orden lexical | Vista experimental limitada, **no ruta P4** |
| `candidate_continuation_guard.py` | Ninguno directo en paquetes productivos | Una continuación literal sobre el cine | Utilizado directamente por tests de un piloto, no debe atribuirse a la ejecución productiva actual |
| `TaskCorePlanner` | `odyssey_apps/tasks/__init__.py`, `odyssey_runtime/composition.py` | Adaptador Tasks heredado, todavía requerido por otras rutas | Conservar su política diferencial hasta migración completa; **mecánicas de plan a Core** |

**Importante:** El runtime antiguo también invoca reglas generales que no son pilotos: comprobaciones de cobertura, autorización, identidad, temporalidad, cardinalidad, enlaces y Writer. No eliminar la comprobación de procedencia ni aceptar datos de modelo como autoridad para reducir falsos rechazos. E2 (`whole_message_coverage`, speaker proof, identidad autenticada) y E3 (claims, mutación canónica y resultados) son fronteras distintas y necesarias.

## Cambios efectuados en esta ronda

1. `odyssey_core/whole_source_compiler.py` ahora compila **todas** las acciones del mensaje antes del primer `execute_request`. Una Task sin fecha que la versión actual no puede expresar o un hecho sin propietario probado bloquea la petición **antes** de crear Day, SELF o Task. La evidencia estructural de símbolos `{{ref:N}}`, referencias, fechas y fuentes se revalida, sin atajos por nombres o frases del corpus. Si Core falla posteriormente por identidad concurrente o estado stale, E3 sigue devolviendo `partial` y prohíbe retry que duplique.
2. `odyssey_core/whole_source_readback.py` contrasta todos los recibos Task por `delivery-task-{posición}` también en el recuento final. Antes comprobaba el cuerpo Task con el ID correcto pero el recuento final con el sufijo incorrecto. Una prueba adversarial reproduce que una escritura extra antes podía pasar y ahora **se rechaza**.
3. `odyssey_core/write_plan_enrichment.py` extrae **mecánicas reutilizables** para crear el hecho visible y ampliar fact/references/helpers desde `TaskCorePlanner`. Tasks sigue decidiendo `ASSIGNEE`, `PARENT_TASK` y lifecycle, pero no construye `KnowledgeUnit` ni `KnowledgeReference` directamente en esas transformaciones. Tipos adicionales de NoteSchema pueden reutilizar la misma operación. Un rol desconocido se rechaza explícitamente; no se interpreta por defecto como PARENT_TASK.
4. El gate offline incluye nueva compilación Core con cardinalidad variable, Task readback adversarial, paridad del adaptador Tasks tras extraer mecánicas y la auditoría AST de los cinco componentes estrechos. El inventario falla si P4 vuelve a importar validador de frase fija.

## IA real tras la compilación previa

La batería autónoma ampliada `scripts/p4_product_live_isolated.py` ejerció diez ejemplos con respuestas NUEVAS del proveedor, servidor HTTP localhost y vault/estado nuevos. Resultado de aceptación **9/10**: 6 positivos y 3 abstenciones correctas, con replay de todos los requests y sin mutaciones en los bloqueados. El positivo «Hoy compré pan y mañana compraré leche» tuvo otro falso rechazo conservador sin escritura. En una ronda anterior ese mismo mensaje había sido completado correctamente. Por tanto sigue sin demostrarse estabilidad longitudinal; no convertir un único 5/5 positivo en autorización de despliegue. Todas las pruebas IA usan frases y Notes sintéticas; **no** pasaron por navegador/n8n ni datos personales.

## Qué falta antes de DEV

- Investigar los rechazos falsos de dos fechas/proveedor, instrumentar diagnósticos de fallo acotados sin exponer datos personales y ejecutar repetición real longitudinal (no cambiar la semántica del gate para maquillar resultados).
- Terminar el contrato funcional de **Tasks puras y mezcladas**, Work Sessions y subtareas desde chat, manteniendo la misma autoridad E2/E3 que usa UI. La nueva ruta aún no expresa Work Session + Core como un plan mixto verificable y se abstiene.
- Conectar la relación real de grupos «mis hijos» usando `verify_self_relationship` y `recheck_self_relationship` sin fijar alias, número de hijos ni inventar IDs.
- Probar compatibilidad y recuperación de claims después de crash, respuesta chat persistida, `partial`, selección de clarificación y reindexación real.
- Reducir el coste O(N) demostrado por 1000 Notes (~5,23s sin GPT con refresco incremental y embedder sintético); verificar FastEmbed, CPU/swap/ventilador de Raspberry.
- **E2E auténtico** navegador autenticado → webhook n8n → runtime nuevo → IA → Markdown → índices → n8n → UI, donuts y gráfica, en entorno verdaderamente desechable. Sin esto no hay autorización para solicitar pruebas manuales.

## Estado operativo

Solo rama `feat/light-router-poc-20261016`, sin merge ni deploy. DEV instalado `1474681`; PROD, Notes de usuario y conversaciones no modificados. Los errores históricos de benchmark de proveedor/precios se mantienen independientes del cambio. El resultado completo de CI y commit se anotan en el seguimiento activo del Functional Roadmap al cerrar esta ronda.

## Resultados verificables de esta ronda

Gate transversal: **574 tests Python + 168 Node PASS** en 47 archivos/9 grupos. Suite global: **3499 Python PASS/80 SKIP**, los mismos **diez fallos históricos**, 52 subtests PASS. La extracción `write_plan_enrichment` se validó también desde los tests existentes del planificador de Tasks (Lifecycle, Assignee, Parent/Subtask, live-replay congelado), además de casos falsos de App para tipos `person`, `document`, `task` y `project`.

Sonda adicional reproducible `scripts/p4_product_semantic_variability_probe.py`: 4 repeticiones auténticas de dos fechas en vaults frescos, **4/4 completadas**, dos hechos físicos por request y cero errores de validador reportados. En tres de cuatro muestras el Router etiquetó `tasks` como posible capacidad además de Core/Temporal, sin que Planner convirtiera ningún hecho en Task. La prueba de diez escenarios anterior tuvo **un falso bloqueo** de la misma frase; la sonda no lo ha reproducido y no autoriza declarar solucionada la intermitencia. El reporte estructural solo incluye roles, fechas, cardinalidad, estados y tipos de error sin fuente/entidades/canonical IDs de usuario.
