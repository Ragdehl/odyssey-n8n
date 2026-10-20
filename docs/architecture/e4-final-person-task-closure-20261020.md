# E4 — Core crea Person y Tasks crea Task en el mismo mensaje (20-10-2026)

## Estado verificable
El código está implementado en la rama aislada `agent/e4-final-audit-20261020`, derivada de `869e362`, sin merge, push, despliegue DEV/PROD ni acceso a las notas privadas del usuario.

**Gate transversal fresco tras la reparación:** 1.268 tests Python PASS (7 subtests adicionales) y 178 tests JavaScript PASS. En la comprobación focal posterior, 72/72 PASS para handoffs y contratos anteriores. Ruff check PASS; el formateo se verifica antes del commit. El repositorio mantiene **9 fallos históricos** de benchmarks congelados en la suite Python global, distintos del gate transversal y de los cambios E4.

## Comportamiento implementado
- Core Writer crea Person realmente, conserva ID canónico y recibos físicos. Tasks reutiliza el Task CREATE ordinario y el E3 replay; no crea un segundo Writer ni da autoridad al Router para inventar personas.
- Los recibos directos CREATE y backlinks distintos pueden acreditar la misma identidad. Clones duplicados, índices de referencia manipulados, operaciones inventadas, guards físicos caducados, actor incorrecto y pronombres ambiguos quedan vetados.
- Los recibos Core vinculados a dependencias incluyen un digest privado del texto exacto que Core planificó. Ambos handoffs comparan el fragmento de origen revisado (con el mismo recorte de espacios de borde que usa el delegado). El agregador WholeSourceLight conserva el digest únicamente cuando todas las suboperaciones coinciden, evitando descartarlo en una agregación legítima.
- El nombre canónico puede estar capitalizado aunque aparezca en minúsculas en la fuente. La aparición en el texto original sigue siendo única y completa.
- TaskPersonReference revisa identidad, estado Markdown, actor y fragmento de Task antes de pasar al servicio estándar.
- Tests con fábrica de composición real y proveedores de respuestas **grabadas**, incluyendo parsers Planner/Tasks, readback de Markdown, enlace canónico, dos personas con referencia ambigua, nombres variables y replay sin duplicados.

## Evidencia complementaria y límites
- Pruebas separadas en Chromium arm64 real sobre localhost: PASS en móvil y escritorio, notas, SVG/flujo, conservación después de recarga y replay; **ese escenario visual previo es Core/Maya, no un E2E visual nuevo Persona→Task**. Usa sustituto HTTP de n8n y respuestas grabadas, no Cloudflare ni GPT vivo.
- Benchmark Pi de la batería sintética de 20 tests: 5 ejecuciones PASS, mediana 3,001 s por lote, máximo 3,151 s, pico RSS observado 96.096 KiB. **No representa la latencia de mensajes en uso real ni p95, concurrencia o carga de embeddings.**
- Auditoría independiente: en la ronda inicial Generality encontró el enlace cruzado entre mensajes; Quality aprobó esa revisión del código anterior; Testing y Performance quedaron bloqueados por evidencia externa de navegador/GPT y medición de rendimiento. El Builder posterior incorporó correcciones, pero la tercera sesión falló con el límite real de uso de Codex antes de cerrar las cuatro revisiones sobre el último código. No hay cuatro PASS finales; el supervisor quedó bloqueado por cuota del proveedor. El límite diario local no refleja la cuota real de ChatGPT.

## Pendiente para cierre de producto
Repetir las cuatro auditorías independientes sobre el commit definitivo cuando el proveedor permita nuevas sesiones, preservando controles de memoria y gasto diario. Después comprobar con datos y vault **sintéticos y aislados** el recorrido autenticado navegador → n8n auténtico → GPT vivo → Core/Tasks → Markdown → búsqueda → gráfico/donut → navegador y replay E3. El éxito offline no autoriza un despliegue a DEV/PROD ni significa que la funcionalidad esté lista para el usuario.
