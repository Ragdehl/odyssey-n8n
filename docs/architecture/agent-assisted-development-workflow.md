# Cómo trabajar con IA en Odyssey sin perder el control

**Decisión incremental (16-10-2026):** no cambiar el stack, arquitectura híbrida, modelos ni la fase P4. Este protocolo no sustituye el [Functional Roadmap](functional-roadmap.md), que es la única fuente del estado operativo y del próximo paso, ni modifica permisos de despliegue.

## Fuentes de verdad y límites

- `AGENTS.md` → principios estables, contratos de seguridad y cómo empezar. Los checkpoints cronológicos antiguos están en [agent-execution-history-202610.md](agent-execution-history-202610.md), **no** en el prompt principal.
- [Application Extensibility Plan](application-extensibility-plan.md) → arquitectura deseada y criterios funcionales E1–E6.
- [Odyssey acceptance contracts](odyssey-acceptance-contracts.json) → índice compacto de compromisos concretos, con test identificado por archivo y función, estado máximo de evidencia **declarado**, y prohibición explícita de que un éxito offline se convierta en permiso de deploy.
- `.github/workflows/odyssey-dev-contract-gate.yml` → CI offline independiente para PR hacia la rama `dev`, que antes no tenía el mismo chequeo específico. Este archivo solo se ejecutará en GitHub cuando el cambio esté publicado en una PR; no sustituye las pruebas locales ni la validación real.
- `scripts/odyssey_acceptance_contracts.py` → analiza sintaxis de los tests enlazados, comprueba que siguen incluidos en la batería y que no se eliminan requisitos acordados sin modificar conscientemente las defensas. **No ejecuta esos tests ni certifica por sí solo ningún resultado.** La batería real sigue siendo `scripts/odyssey_cross_surface_gate.py` y pruebas externas.
- Informes de evidencia por fase y `git` → resultados reales, archivos, errores, recursos consumidos, recibos, versión instalada. El código canónico Markdown sigue siendo la única fuente de conocimiento, no un índice generado.

## Ciclo para cada cambio significativo

1. **Contrato:** indicar comportamiento visible esperado, invariantes Core/App/E2/E3 afectados, qué no debe cambiar y cómo se detectará un fallo. Si una decisión de producto no está tomada, conservarla como decisión abierta; no fabricar una respuesta.
2. **Implementación acotada:** tocar las mínimas capas; una App aporta sus operaciones especializadas, Core mantiene identidades y Writer, Temporal aporta fechas. No inventar código por nombre/frase de un test ni añadir servicios sin necesidad.
3. **Validar en escalones:** tests unitarios; pruebas verticales de Core + archivos reales desechables, Task/UI/Work Session y replay; gate transversal; modelo fresco en variaciones representativas; prueba auténtica de producto (navegador autenticado, n8n, IA, Writer, DOM, donut y grafo). Un escalón **no implica** el siguiente.
4. **Revisión independiente antes del deploy/merge:** buscar contradicciones arquitectónicas, rutas heredadas, escrituras parciales, duplicaciones, falsas certezas e impacto de código; repetir la revisión si cambian varias capas. Para cambios relevantes de UI incluir comprobación visual real, no solo tests de cliente.
5. **Informe breve y comprobable:** `hecho`, `pruebas y nivel`, `fallos reproducibles`, `pendiente/bloqueante`, `branch+commit`, `DEV/PROD`, `siguiente acción`. Reportar fallos históricos separadamente. No confundir Git HEAD con versión efectivamente instalada.
6. **Solo puntos de decisión humana:** semántica no acordada, datos reales, permisos/credenciales, migración destructiva, deploy sensible, merge/PROD. No interrumpir para aprobar edición reversible de pruebas o rama de trabajo.

## Definición de listo (P4)

La aceptación requiere evidencias positivas **físicas y observables** para el recorrido navegador→n8n→runtime→GPT→Markdown→índices→n8n→UI con identidad real autenticada y **vault sintético aislado**. Comprobar varios intentos de modelo, relaciones y actor implícito, fechas, Tasks, sesiones/subtareas, grafo y donut, respuesta que sobrevive navegación, reintentos, rechazos seguros y estado parcial. Claims E3 inciertos NO se reejecutan por defecto. El rendimiento debe medirse con embeddings reales y carga Raspberry (CPU/RAM/swap), no inferirse de un embedder ficticio.

Cuando un requisito queda sin prueba en un nivel superior, sigue **pendiente de ese nivel** aunque hayan pasado miles de tests inferiores. E5 Events y E6 Clean Architecture **no bloquean la aprobación de P4**: son etapas posteriores/incrementales. Los tests se retienen como centinelas después de cada cambio importante. No se retocan los resultados esperados solo para presentar una matriz verde.

## Acceso sin leer código

También existe `python scripts/odyssey_operator_status.py` (o `--json`):
compara la rama de trabajo con el HEAD de DEV realmente instalado, comprueba
el registro de invariantes y deja la aceptación P4 sin autorización mientras
falte la prueba real navegador→n8n→GPT→Markdown→UI. Es **solo lectura** y no
prueba por sí mismo funcionalidades; se ejecuta al comenzar cada nueva sesión
de agente y antes de cualquier informe de «listo para DEV».

Para obtener un estado fiable en una próxima sesión, solicitar: «Dame el estado de Odyssey a partir del HEAD, último seguimiento activo del roadmap, el registro de aceptación y el resultado de las pruebas». El asistente debe inspeccionar esos archivos y las versiones instaladas antes de responder, sin sustituirlos por recuerdos del chat. Se puede pedir una revisión externa o segunda pasada crítica sobre un PR antes de autorizar cambios operativos; ninguna IA sustituye la aprobación humana cuando hay una decisión de producto irreversible.
