# Contrato de interpretación híbrida Router → Temporal → Core → Writer

**DECISIÓN DEL USUARIO: arquitectura objetivo APROBADA el 12-10-2026.**
**ESTADO DE IMPLEMENTACIÓN: pendiente; NO está activada en DEV ni PROD.**
Este es el ÚNICO contrato normativo objetivo para este flujo. Sustituye la
obligación del 11-10-2026 de enviar a Core cada candidato atómico por separado.
Los documentos antiguos describen implementaciones o pruebas históricas,
pero no son instrucciones alternativas a este contrato.

## Regla principal

**Separar hechos no equivale a separar llamadas al modelo.** Router recibe
el mensaje original íntegro una vez e identifica candidatos semánticos atómicos
con roles, polaridad, modalidad, posiciones de texto y dependencias verificables.
El agrupador forma unidades de INTERPRETACIÓN compuestas por candidatos
semánticamente interdependientes; Core puede producir múltiples hechos/notas
independientes a partir de UN grupo. El grupo nunca se convierte en un hecho
fusionado o una escritura conjunta obligatoria.

Un grupo puede incluir toda la entrada original SI TODOS sus candidatos están
relacionados. Nunca incluir un hermano independiente solo porque comparta un
sujeto, fecha, verbo o tramo de texto. La proximidad no demuestra dependencia.

Original → Router (candidatos atómicos) → agrupador local (grupos coherentes)
  → Temporal solo si hay fechas/horas → Planner ordinario de Core por grupo
  → revisor independiente de cobertura candidato↔hecho → validación Core
  → Writer / Markdown / auditoría por hecho

## Contratos por componente

1. **Router** solo propone segmentación y dependencias lingüísticas con
   evidencia exacta en el mensaje original. No infiere identidad canónica,
   tipo de nota, resultado ISO, hechos finales, acciones o permisos de escritura.
   Conservar negaciones, condiciones, rectificaciones y ambigüedad.
2. **Agrupador** mantiene el texto original exacto de cada grupo, sus límites,
   todos los candidatos originales y sus posiciones verificadas, sin fabricar
   frases. Divide intenciones comprensibles independientemente (F06, F22) y
   reúne contextos imbricados (F04, F16, F23). Contabiliza TODO el mensaje
   y no duplica una acción independiente entre grupos. El mensaje completo
   queda disponible únicamente como procedencia/auditoría si contiene grupos
   independientes; NO se reenvía a Core como otra solicitud de planificación.
3. **Temporal** interpreta cada grupo con contenido temporal y devuelve
   evidencia tipada atribuible a CADA candidato/evento: fecha compartida,
   varias horas, varios días, orden y condiciones. Sin convertir por intuición
   rangos, aproximaciones, horas sin anclaje o tiempos cancelados en fechas
   exactas. Un grupo sin datos temporales omite Temporal.
4. **Core Planner** recibe el texto íntegro DE SU GRUPO, no una proposición
   atómica aislada por defecto ni hermanos independientes. Core mantiene
   autoridad exclusiva sobre semántica, referencia, sujeto, destino canónico,
   selección, hechos y acciones; puede planificar 0..N hechos y notas.
   Sigue GPT-5.6 hasta la migración aparte ya aplazada.
5. **Revisor Core + validadores** exigen contabilidad explícita de CADA
   candidato y CADA hecho planificado. La relación candidatos→hechos es N:M,
   sin convertir ordinales de Router en ordinales de escritura. Se puede
   justificar un sujeto, predicado o condición compartido DENTRO del grupo
   sin exigir una escritura previa, pero nunca copiar identidad no verificada.
   Validar por hecho destino, fecha/hora, polaridad, modalidad, corrección y
   alcance. Una propuesta del revisor no es autorización de escritura.
6. **Writer** conserva preflight canónico, identidad, permisos, estabilidad
   de Markdown, marcas request/fact, idempotencia y readback físico.
   Varios hechos del grupo pueden terminar en notas distintas.
   Los hechos seguros pueden completar y otros quedar pendientes SOLO cuando
   los contratos actuales garantizan esa separación. Si no, bloquear el
   grupo que no pueda separarse de forma segura. No prometer rollback
   transaccional global ni declarar completado lo que se omitió.
7. **Entre grupos** mantener carriers temporales, referencias canónicas y
   pruebas de eventos previos derivados de Core/Markdown; comprobar vigencia
   antes de escribir. Dentro de un grupo se interpreta conjuntamente el
   texto original, sin que cada hecho dependa de persistir el anterior.
   La referencia ambigua permanece sin resolver; otro grupo independiente
   puede completarse. No crear un Planner alternativo en Router o Temporal.

## Ejemplos y controles

- F03: parque + cine con mis hijos juntos; dos actividades, misma fecha;
  la identidad del grupo permanece pendiente si Core no puede acreditarla.
- F04: parque 12:00 + cine 18:00 juntos; dos hechos y horas separadas.
- F16: Ana compró entradas + Luis también juntos; dos compras, dos personas.
- F21: clase lunes y miércoles a las 18h juntos; dos días y una hora
  compartida; no inventar las horas que Temporal no pueda autorizar.
- F23: dos fallos en Odyssey juntos; dos propiedades de un proyecto;
  «Temporal» como componente no es una expresión de fecha.
- F06: vio a Ana / compró pan en grupos separados aunque compartan «hoy».
- F13: conversación con Eric y cine con «él» pueden agruparse solo con
  antecedente inequívoco; comprar pan aparte.
- F14/F27: «él» tras Eric y Luis sigue ambiguo, nunca escoger al azar.
- F19: corrección agrupada; no guardar el plan sustituido.
- F20: alternativas de lluvia agrupadas; no tratarlas como sucesos ocurridos.
- F22: tres tareas independientes, tres grupos.

## Cinco pruebas con modelos reales: 12-10-2026

Se reutilizaron las respuestas auténticas de Router GPT-6. Temporal GPT-6
cuando procedía; Core Planner y revisor independiente GPT-5.6 auténticos.
Todas las escrituras se intentaron SOLO sobre 13 notas Markdown ficticias.

| Caso | Estado real | Observación |
| --- | --- | --- |
| F04 | COMPLETED | dos horas correctas; dos readbacks verificados |
| F16 | COMPLETED | Ana y Luis, dos destinos canónicos; dos readbacks |
| F03 | NEEDS_ATTENTION | Core planteó dos actividades; revisor declaró ambigua identidad «mis hijos» |
| F23 | NEEDS_ATTENTION | Core planteó dos fallos, revisor los relacionó; validador actual bloqueó referencias múltiples |
| F21 | BLOQUEO TEMPORAL | lunes y miércoles reconocidos; «a las 18h» quedó UNSPECIFIED; Core no se ejecutó |

Resultado exacto: 2/5 completas, 2 pendientes en Core, 1 detenida en
Temporal. Es evidencia para escoger el diseño, NO validación de implementación
general. Coste adicional estimado: 0,0135635 USD; acumulado 0,2789394 de
0,50 USD autorizados (estimación, no extracto de facturación).
Pruebas aisladas históricas: ruta local externa
/home/ragdehl/projects/odyssey-experimental-receipts/hybrid-probe050/
Este resumen documental es independiente de que esa ruta siga existiendo.

## Implementación: compilador híbrido opt-in (primer bloque aislado)

**CÓDIGO IMPLEMENTADO en esta rama de experimento, NO desplegado en DEV/PROD:**

- `odyssey_runtime/hybrid_group_compiler.py`: reutiliza Router v1,
  las posiciones y roles existentes, la validación de fuente original y
  los contratos `CandidateRouteBundle`. Agrupa dependencias semánticas
  explícitas, preservando todos los candidatos independientes por ID.
- `execute_candidate_routed_message(..., bundle_compiler=...)`: habilita
  exclusivamente por selección explícita el agrupador híbrido, con el
  **mismo** Temporal/Core/revisor/Writer existente. Sin esta opción, el
  compilador atómico anterior sigue siendo el predeterminado. No se ha
  activado ninguna ruta nueva en DEV/PROD.
- Se reforzó el validador compartido de procedencia: los límites exactos
  de cada ruta/grupo deben reproducir la partición original; no basta con
  que el texto de una ruta aislada coincida. Los resultados históricos
  mantienen su propio compilador y se revalidan sin reinterpretarlos.
- Con los 26 resultados antiguos estructuralmente compilables de Router:
  **53 rutas atómicas → 37 grupos conservadores** (reducción del 30,2 %
  en unidades de interpretación potenciales; NO medición de ahorro real).
  F27 sigue rechazado por dependencia incoherente; no se repara a ciegas.
- Se han reproducido sin nuevas llamadas de pago las cinco respuestas
  **auténticas** anteriores de Temporal/Core, ahora entrando por el nuevo
  agrupador: **F04 y F16 completan** con notas ficticias verificadas;
  F03/F23 siguen pendientes por validadores canónicos y F21 mantiene el
  bloqueo Temporal. Las salidas originales se han congelado como fixtures
  bajo `benchmarks/application_router/hybrid_grouped_v1/`.
  F06 demuestra además que si el primer hecho independiente queda pendiente,
  la segunda compra puede persistir sin copiar al actor anterior.
- La suite de regresiones en el repositorio es obligatoria antes del
  merge. Ningún cambio de prompt ni modelo se ha producido en esta etapa.

**ACTUALIZACIÓN POSTERIOR (2026-10-12): F03/F21/F23 implementados y
validados en la rama experimental, NO desplegados.** La descripción de los
cinco resultados fallidos/parciales arriba es la PRIMERA prueba, y sigue
siendo evidencia histórica. Después, nuevas llamadas reales al modelo,
revisiones independientes de Core y readback físico en vault ficticio han
confirmado las tres correcciones en sus formulaciones positivas:

- **F03**: `odyssey_core/candidate_group_participants.py` conserva la
  descripción colectiva literal `mis hijos` en AMBOS hechos, sin inventar
  personas, identidades ni enlaces; exige que la participación y cada acción
  estén justificadas en los roles originales. Si la pertenencia del grupo
  completo se puede demostrar canónicamente en otro caso, la ruta normal de
  Core seguirá siendo la autoridad para el enlace; este piloto no lo afirma.
- **F21**: `odyssey_core/temporal_group_composition.py` compone un reloj
  postpuesto explícito con dos fechas EXACT_DATE ya verificadas por Temporal,
  tras comprobar roles compartidos, día de la semana, rango, zona y DST.
  `candidate_grouped_temporal.py` verifica por separado que cada Core Note
  de día coincida con su fecha/instante y que la frase no invente palabras.
  El Planner emplea los segmentos originales de Temporal; nunca fabrica
  `el lunes a las 18h` concatenando dos textos no adyacentes.
- **F23**: `odyssey_core/candidate_grouped_property.py` atribuye dos
  propiedades afirmativas distintas a UN sujeto explícito/verificado.
  Cuando `Router` y `Temporal` sean nombres de componentes sin identidad
  segura, Core guarda los textos LITERALES; no fuerza enlaces, ni crea notas.
- Se conserva el **control antiguo** para contextos no híbridos;
  `context.scoped_route_source` y la prueba tipada de Temporal restringen
  las nuevas validaciones y no convierten las rutas atómicas en grupos.
- Respuestas auténticas positivas, sin claves ni notas personales,
  congeladas en `benchmarks/application_router/hybrid_grouped_v2/`.
  Pruebas de ejecución/revisión/escritura reproducidas sin nuevas llamadas
  de pago en `tests/runtime/test_hybrid_repaired_real_provider_replay.py`.
  Coste total estimado de todos los experimentos hasta esta etapa:
  **USD 0.2951979 de USD 0.50 autorizados**. No equivale a factura de API.

**SIGUIENTES BLOQUES, TODAVÍA NO IMPLEMENTADOS:**

1. Ampliar y contrastar semántica multihecho general (N:M, negaciones,
   condiciones/correcciones, tareas, identidades singulares/plurales,
   estados parciales y pronombres ambiguos F14/F27), con todos los mensajes
   originales y pruebas adversariales ajenas a los casos del piloto.
2. Repetir los gates de regresión y calidad con variaciones reales acotadas,
   preservar la suite histórica y medir precisión, gasto y latencia.
3. Pedir aprobación separada antes de activar la ruta híbrida en DEV y luego
   en PROD. GPT-5.6 Core se conserva durante esta fase.

## Precedencia / documentación histórica

AGENTS.md y functional-roadmap.md apuntan a este contrato como objetivo.
router-unit-dispatch-contract.md (11-10-2026), router-fact-units-v1.md,
router-scope-27-live-regression-20261011.md y application-boundary-router-v0.md
son evidencia de diseños, prototipos y comportamiento legado, NO políticas
competidoras. No borrar fixtures, afirmaciones históricas de fallos/éxitos,
ni enunciados que documenten cómo funciona el v0 todavía activo.


## Auditoría documental y precedencia

Para el inventario de contradicciones corregidas, orden de lectura
entre chats, separación entre OBJETIVO/IMPLEMENTADO/DESPLEGADO y regla
de prevención, consultar la
[auditoría de coherencia 2026-10-12](router-hybrid-documentation-audit-20261012.md).
El registro es documentación de esta decisión, no otra autoridad normativa.


## 2026-10-12: Sensitive-scope source regression checkpoint (NOT a functional release)

The approved hybrid grouping is unchanged. Five fresh real-provider probes
were run on disposable canonical Notes with the previously saved authentic
Router GPT-6 source proposals. **Results are fail-closed evidence, not five
successful semantic writes:**

| Case | Fresh model result | Safe physical result |
| --- | --- | --- |
| F17, common negation of Ana and Luis | Core proposed one joint negative fact; independent reviewer could not authorize specialized negative coverage | NEEDS_ATTENTION, 0 writes |
| F19, cancelled park then cinema correction | Core attempted unsupported temporal wording/evidence; date-scoped planner validation rejected before reviewer | FAILED, 0 writes; do not save the cancelled park |
| F20, mutually exclusive Saturday alternatives | Core proposed a combined condition with an unsafe personal destination; reviewer declined | NEEDS_ATTENTION, 0 writes; not two confirmed occurrences |
| F18, no Ana / yes Luis | Two independent groups, each Core/reviewer declined unproven person binding; second group must not guess previous date/actor | NEEDS_ATTENTION, 0 writes |
| F22, three independent task intents | Core declined first two, historically stored the third "preparar la factura" as a Day fact | PARTIAL in **original provider receipt**, one Day write which is **not a Task** |

A corrective opt-in hybrid guard has now been added:
`CoreCandidateContext.hybrid_interpretation_mode` is marked **only** by the
hybrid source compiler. The Core candidate coverage gate blocks all ordinary
`WriteAction`s involving `task` candidates in this mode until a reviewed
specialized Task lifecycle contract exists. Hence replaying the unchanged F22
authentic model outputs with the new guard must produce **no false completed
Tasks or Day facts**. F25 (house repair need) is similarly prevented from
being silently promoted to a Task. Older atomic contexts are untouched.

Real provider outputs in
`benchmarks/application_router/hybrid_sensitive_v1/F17.json`,
`F18.json`, `F19.json`, `F20.json`, `F22.json` remain immutable,
with the historical captured statuses preserved (do not relabel F22's actual
original partial outcome). Regression tests in
`tests/runtime/test_hybrid_sensitive_boundaries.py` and
`tests/runtime/test_hybrid_multi_route_sensitive_replay.py` check
source-group coverage, sensitive-write refusal, F14 ambiguity, F27 invalid
dependencies, independent Task scopes, replay of real model outputs, and
forbidden generic Day writes. No user Notes, DEV/PROD, model versions,
Task schema or plugin/app internals were changed.

Current cumulative **estimated** provider spend after these probes was
**USD 0.3193113 out of the approved USD 0.50**. Do not count as official
billing. No additional model calls are required to replay these results.

**Next technical work:** establish a distinct reviewed Core semantics for
negative/hypothetical/corrected plans (the resulting Note content must
explicitly preserve modality and polarity), plus actual specialized
Tasks ownership with completion state and date/modality inheritance.
An unsafe broad exception in the ordinary fact coverage validator is
not an acceptable way to make these tests green. Continue F14/F27
source/identity gates and test an independent negative-plus-positive
case before considering DEV/PROD promotion.
