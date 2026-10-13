# Auditoria de validadores de forma linguistica (2026-10-13)

ESTADO: rama experimental, NO DEV / NO PROD. Revision de los
validadores activos del Dispatcher hibrido, Core, Tasks y Writer.

| Modulo | Hallazgo | Decision |
| --- | --- | --- |
| candidate_sequential_contacts.py | Exigia expresion espanola de dos conversaciones | Legacy, desconectado de TODA ruta hibrida |
| candidate_multi_participant.py | Dos nombres, conjuncion y, tres unidades exactas | Legacy para eventos; hibrido usa candidate_group_participants con N referencias |
| candidate_group_participants.py | Verifica roles originales y una identidad por referencia | Activado en hechos hibridos con 1..N participantes, incluidos casos de un solo hecho |
| candidate_mutual_relation.py | Exigia los lexemas espanoles y y se | Eliminados; dos participantes siguen siendo un contrato de relacion BINARIA |
| temporal_group_composition.py + candidate_grouped_temporal.py | Tope arbitrario 6 hechos | Sustituido por presupuesto explicito de 16 evidencias temporales tipadas |
| candidate_fact_readback.py | Maximo arbitrario de 4 enlaces | Eliminado, sigue comprobando prueba canonica individual por cada enlace |
| TaskCorePlanner | Texto plano suplia identidad omitida, o duplicaba hechos enlazados | Contexto canonico read-only, verificacion de referencias y cero duplicado de la propia tarea |
| request_planning / experimental_luna_planning | Exigia fecha de Tasks como link aun estando validada en target_date | Consumir fecha como propiedad, sin link ficticio |
| candidate_scoped_handoff/planning y candidate_continuation_guard | Gramaticas historicas estrechas | No llamadas desde hibrido, conservadas solo para compatibilidad |
| candidate_attribution legacy | Atribucion 1:1, formas de dos personas | Hibrido usa el grafo revisor N:M, no activar legacy |
| candidate_reference_handoff | Handoff de dos candidatos historico | No es el carrier usado por dispatcher hibrido |
| candidate_sensitive_statement | Protege negaciones y condiciones sin transformarlas en eventos ocurridos | Cardinalidad de seguridad; no eliminar |
| TaskLifecycleGuard | Una Task primaria por operacion, roles assignee/parent singulares | Cardinalidad de dominio valida |

Presupuestos tecnicos pendientes: 26 candidatos en un mensaje, 128 hechos
de cobertura, 16 pistas de nombres y 5000 notas como limite de ESCANEO
experimental (no limite de notas almacenadas), 16 evidencias DomainInterpretation.
Antes de usar estas pistas en DEV sobre bovedas grandes, sustituir el
escaneo por lookup indexado y fail-closed si no hay contexto completo.
No volver a introducir un tope de notas de usuario ni reglas por IDs de prueba.

## Resultados reales por caso

F14: Router -> hablar con Eric y Luis + cine con referencia ambigua.
Temporal -> ayer 03/10. Core y Reviewer -> hecho aprobado con ambos enlaces.
Writer -> Day 03/10 con Eric y Luis. El cine con el sigue pending.
Resultado PARTIAL SEGURO.

F27: Router -> hablar con Eric, despues con Luis, cine con el ambiguo.
Temporal -> 03/10. Core+Reviewer -> dos hechos fechados y enlazados.
Writer -> dos lineas en Day 03/10. Cine permanece pending.
Resultado PARTIAL SEGURO; no elegir por proximidad.

F22: Router -> 3 tareas independientes; GPT-6 Tasks y Temporal -> dos
objetivos 04/10 y factura 05/10. Primer Core Planner -> llamar a Ana con
link. Planner original de segunda -> sin hecho, solo titulo plano.
Core ahora proporciona notas canonicas read-only; NUEVA respuesta real
GPT-5.6 -> Escribir a Luis con identidad person; Writer vincula Luis.
Tercera -> factura. Reproduccion de las tres rutas juntas con modelos
autenticos guardados: 3 Task Notes pending con fechas verificadas.
Test: tests/runtime/test_hybrid_tasks_named_source_live_replay_20261013.py.
NO existe el mismo Reviewer LLM independiente de Core en la ruta Tasks;
TaskCorePlanner/LifecycleGuard/Writer realizan los controles adicionales.
Resultado COMPLETED, NUEVO caso aceptado.

F09: Router -> propiedades separadas Marta y Luis, sin error.
Core Planner con contexto read-only de notas reales -> ahora propone
Vive en Lyon (singular) para ambos. Reviewer GPT-5.6 -> cubre ambos
hechos, pero no revisa redundancia con contenido previo. Writer actual
solo evita duplicados textuales exactos, no frases semanticamente
equivalentes; Marta ya tenia vive en Lyon dentro de su contenido.
El WRITE devuelve COMPLETED pero NO pasa aceptacion de producto.
Para corregirlo hace falta un contrato Core de hecho ya representado:
evidencia de contenido exacto y guard de vigencia por nota,
verificador semantico independiente con control de polaridad y alcance,
NO_CHANGE por candidato, y readback que acepte prueba ya existente.
No introducir casos codificados para Marta, Lyon o conjugaciones.

## Evidencia

- F14/F27: benchmarks/application_router/hybrid_remaining_diag_20261013/
- F22 respuesta autentica: benchmarks/application_router/hybrid_tasks_named_link_v1/
- F22 replay 3 Tasks: test_hybrid_tasks_named_source_live_replay_20261013.py
- F09 Planner y Reviewer reales: benchmarks/application_router/hybrid_existing_info_v1/
- Validacion 1,3,5,9 nombres y adulteraciones:
  test_hybrid_generic_validator_audit_20261013.py

Estado global: 24/27 aceptados en notas de prueba, F14 y F27
parciales por ambiguedad real, F09 duplicado aun sin resolver.
Ni DEV ni PROD han sido modificados.
