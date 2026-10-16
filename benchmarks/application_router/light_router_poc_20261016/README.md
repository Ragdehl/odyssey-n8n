# PoC Router ligero: resultados observados, 16-10-2026

**P3 MÁS RECIENTE:** [informe](../../../docs/architecture/light-router-p3-results-20261016.md). Nuevo contrato Core y pruebas reales aisladas: 5/6 Core+Task completos, 1 bloqueo Ana sin escritura, y escenario «mis hijos» 3 facts sin fecha almacenados en SELF con backlinks Cloe/Bruno verificados. 256 backend y 140 UI existentes OK, pero falta nueva ruta HTTP/n8n/UI; **no instalar DEV**. Artefactos `p3_core_contract_fresh_receipts.json`, `p3_extended_receipts.json` y `p3_children_real_write.json`.

**ETAPA POSTERIOR P2 (16-10, reemplaza el antiguo gate de integración para la arquitectura NUEVA):** [informe P2 integrado](../../../docs/architecture/light-router-p2-results-20261016.md). PoC experimental con IA nueva Router+Planner+revisor de fuente, **5/6 escritores Core y Tasks correctos con readback y backlinks**, y abstención sin escritura para «Ana» vs «Ana López». Los **0/3** descritos más abajo corresponden a la integración antigua de Core sin el nuevo contrato de revisión íntegra; se preservan como comparativa histórica, no como estado del último prototipo. **Sin despliegue ni autorización de uso real**. Resultados: `p2_integration_receipts_fresh.json`, `p2_integrated_bridge.py` y 71 tests relevantes (nuevo módulo y regresiones).


**Resultado: VIABILIDAD SEMÁNTICA DEMOSTRADA; INTEGRACIÓN CANÓNICA NO DEMOSTRADA.**
Por tanto, P1 (factibilidad de interpretar todo junto) tiene evidencia favorable, pero P2 (Core→Writer→Tasks con garantías) NO PASA y el proyecto NO está listo para DEV ni para pedir al usuario otra campaña manual. No se ha modificado la aplicación en ejecución, sus notas, tareas, sus índices ni PROD.

## Metodología y garantía de autenticidad

- `run_poc.py`: llamadas **nuevas a OpenAI** con `store=false`, GPT-6 ligero Router de capacidades y GPT-5.6 planificador semántico del mensaje ÍNTEGRO. Dos pasadas diferentes (v1 y v2 de instrucciones generales, no replays). Cada mensaje conserva su fuente original en la entrada.
- `observations_v1.json`: 10 casos, 20 llamadas; coste **0,0061137 USD** estimados (tarifas declaradas en script). Un caso adicional auténticamente ambiguo con dos hombres está en `observations_ambiguous_two_males_v1.json`: 2 llamadas, **0,0007006 USD**.
- `observations.json`: v2 completa, 11 casos, **22 llamadas reales** y **0,0071436 USD** estimados, duración total ~76,7 s (mediana por caso ~7 s). Cambios de v2 genéricos: futuro ≠ obligación/task, y no atribuir `canonical_name` si el nombre no está en evidencia validada.
- Copia **temporal** de las 97 notas reales del vault DEV, validadas con el esquema compuesto Core+Tasks. Solo se pasaron al proveedor pistas mínimas de nombres coincidentes y, para «mis hijos», los enlaces verificados de Cloe/Bruno. No se compartieron íntegramente las 97 notas. El clon temporal se descartó.
- `check_observations.py`: oráculos independientes de las instrucciones del modelo. Verifican nº de hechos, sujetos, fechas, dependencias entre aplicaciones, fuente literal exacta y ambigüedad sin resolver; **NO certifican equivalencia semántica perfecta ni escritura física**.
- Los artefactos incluyen salidas semánticas estructuradas; no se incluyen claves API ni secretos. Las salidas son observaciones reales, pero siguen siendo resultados probabilísticos de proveedor.

## Qué demuestra v2 (11 escenarios)

| Escenario | Observación auténtica |
| --- | --- |
| «Ayer hablé con Maya» | 1 hecho; ayer 15/10; Maya como persona propuesta, NO nombre canónico afirmado sin prueba |
| «Hoy he conocido a Guillermo» | 1 hecho, fecha 16/10; existe un Guillermo en el clon |
| «Mis hijos fueron al parque, helado y película» | 3 hechos diferentes, **Cloe y Bruno** en los 3; «por la tarde» conservado sin inventar hora |
| Pan hoy / leche mañana | 2 hechos fechados 16 y 17/10; v2 ya no convierte futuro automáticamente en Task |
| Cena con Maya ayer / hablé «con ella» hoy | 2 hechos, ambas menciones apuntan a Maya, fechas correctas |
| Hablé con Ana/Luis; viaje y vuelta | 3 hechos, Ana mañana 17/10, Luis domingo 18/10 |
| «Hoy he conocido a Maite, mañana tengo que llamarla» | 1 registro Core + 1 Task con dependencia explícita en Maite, fecha 17/10, sin inventar ID canónico |
| Variante Nora y correo lunes | Igual dependencia Core→Tasks; lunes 19/10 |
| Banco mañana + gusto por jazz | Router permite dos aplicaciones independientes y plan produce dos hechos |
| Ana + Luis; «él» | Identifica Luis por género del pronombre; no necesita aclaración innecesaria |
| Eric + Luis; «él» | **Declara ambigüedad**, NO selecciona persona; el hecho 2 queda pendiente |

**Debilidades observadas incluso en v2:** el Router clasificó *también* Tasks para «mañana compraré leche» mientras el planificador completo lo consideró un hecho futuro, señal de desacuerdo entre modelos. Los hechos propuestos mezclan a veces español e inglés: no aceptable como texto final de Notes; el plan semántico tendrá que preservar el idioma y estilo del original. La resolución de nombres parcialmente coincidentes (Ana→Ana López, Eric→Eric de Prueba, Nora→Nora Test) continúa sin demostración de readback canónico. Cualquier estado de identidad sugerido por IA debe convertirse en propuesta, nunca en ID autorizado.

## Prueba de integración física sobre vault copiado: 0/3

`integration_control.py` usa la ruta **ya existente pero inactiva** `execute_complete_message_with_core` (Router v6, Temporal, GPT-5.6 Core Planner, attributor independiente y Writer existente) en copias nuevas de las 97 Notes, con índices derivados de **embeddings sintéticos constantes** por aislamiento, no el embedding productivo. **No es la implementación nueva.**

| Mensaje | Estado de Core | Fact guardado/readback | Hallazgo |
| --- | --- | --- | --- |
| Maya ayer | needs_attention / cobertura | No | Revisor no valida relación candidato↔fact; no se crea Maya |
| Guillermo hoy | needs_attention / cobertura | No | También falla el control que ya tenía persona existente |
| Mis hijos… | TemporalInterpreterError | No | El intérprete devuelve precisión de «tarde» incompatible con exigencia Core de hora/fecha exacta en esta ruta |

En `integration_detail_maya_simple.json` se reproduce una llamada **nueva** y se captura una causa concreta: `Graph attribution evidence is invalid` causada por `Every planned Core fact needs explicit source evidence`. El Planner había preparado el Day 15/10 con fact `Hablé con {{ref:0}}.` y helper de persona Maya con `reference_lookup_only=True`, de modo que ni siquiera está explícitamente asegurada la creación de una nueva persona. **No basta con cambiar el Router**: Core tiene que aceptar pruebas válidas de fuente/facts y resolver/crear identidad ausente de manera genérica, sin debilitar seguridad. El JSON completo original de los intentos de usuario NO existe en los receipts previos; esta es evidencia de una ejecución nueva y no debe fingirse reconstrucción literal del pasado.

**Costes adicionales**: integración 3 escenarios, 10 llamadas, **0,0078825 USD** estimados; investigación causal Maya 4 llamadas nuevas, **0,0037466 USD** estimados. Coste total de estas campañas PoC ~**0,0255870 USD** (v1 0,0061137 + aclaración 0,0007006 + v2 0,0071436 + integración 0,0078825 + detalle 0,0037466). Nota: son estimaciones de scripts con tarifa local y sin impuestos ni otros costes.

No se puede comparar la latencia ~7 s semántica con los ~19 s DEV por mensaje como mejora del producto, puesto que la PoC aún **no incluye indexación productiva, n8n, Writer, revisión completa ni UI**.

## Decisión y siguiente gate indispensable

1. **Conservar** hipótesis de Router ligero y contexto completo; v2 aporta prueba auténtica de que un solo entendimiento puede conservar sujetos, fechas y dependencias entre Apps.
2. **No desplegar / no pedir pruebas del usuario**: falta una prueba de concepto *integrada* que consuma las salidas semánticas reales, revalide fechas/identidades/sujetos, cree y relacione Maya/Maite mediante Core, escriba Tasks y realice readback físico + idempotencia + parciales de forma genérica y segura. Un PoC que saltara el validador de cobertura **no contaría como prueba**.
3. Hacer ese **puente de contratos P2**, aún en sandbox y con tests de IA nueva y datos desechables; resolver `candidate_coverage` y creación canónica de nuevas personas en el contrato común sin cambiar la validez de pruebas ambiguas. Reconciliar desacuerdos entre Router y Planner, y comprobar lenguaje natural español, no inglés.
4. Si P2 pasa, entonces proponer implementación incremental en rama de producto; pruebas genuinas con todo el pipeline, n8n/browser y rendimiento como gate previo al DEV. E3, DEV y PROD intactos hasta autorización de despliegue.

### Archivos reproducibles
- `run_poc.py`, `observations.json` y `observations_v1.json`
- `observations_ambiguous_two_males_v1.json` (segunda ejecución v1)
- `check_observations.py`
- `integration_control.py`, `integration_control.json` y `integration_detail_maya_simple.json`
- Decisión arquitectura: `docs/architecture/light-router-poc-20261016.md`
