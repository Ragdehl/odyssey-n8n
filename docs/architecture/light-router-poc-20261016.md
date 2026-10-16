# Decisión y prueba de concepto: Router ligero y contexto íntegro (16-10-2026)

Estado: **hipótesis aprobada por el usuario para demostrarla mediante PoC; NO autorizada para despliegue**. Esta página sustituye la expectativa de ampliar el *split* actual. Mantener E2/E3 y PROD/DEV intactos durante PoC.

## 1. Motivo y aprendizaje obligatorio

Los tests de ingeniería previos (replays de respuestas de modelos grabadas, fixtures sintéticas y E2E de Writers/gates) **no equivalen a una sesión nueva de IA real en el chat de DEV, con su conversación, notas existentes, n8n y UI**. Las pruebas originales podían tener respuestas del proveedor congeladas, un vault sintético distinto, menos estados persistidos y no recorrer la interfaz. Que pasaran cientos o miles de tests demuestra integridad de partes, **no** que el usuario pudiera escribir libremente sin errores. Nunca volver a declarar «apto para que pruebes» únicamente por tests deterministas o algunos live fixtures.

**Nueva puerta de aceptación obligatoria, ANTES de pedir al usuario pruebas reales:**
1. Evaluación con IA genuina (no replay/mock) sobre mensajes NUEVOS y equivalentes generalizados, con presupuesto y modelo declarados. Incluir variante de prompts, contexto previo y variación de salida; guardar respuesta real del proveedor como fixture de regresión posterior.
2. Copia desechable del conjunto canónico realista de Notes DEV, con relaciones y notas ausentes, y validación de identidades ya presentes. Nunca sobre PROD ni sobre el vault DEV. Si se usa un indexador sintético, indicarlo como limitación.
3. Recorrido Router → interpretación contextual/Temporal → plan → validación semántica → persistencia → readback por Note ID/texto/backlinks; comprobar cobertura de TODOS los hechos, ausencia de duplicados y operaciones parciales.
4. Pruebas E2E con n8n + UI/graph + donut + mensajes de error de verdad, además de latencia/CPU/RAM, *antes* de transferir la campaña manual al usuario. Mantener tests deterministas para regresión; no confundirlos con los anteriores.
5. Guardar entrada, propuestas de modelos, decisiones, scopes, IDs canónicos, rechazo exacto **para diagnósticos autorizados en DEV**, sin filtrar datos sensibles a telemetría pública; preservar receipts tras escrituras parciales.
6. Cortar/reflexionar si la nueva arquitectura no mejora el resultado sobre la base actual. No sustituir invariantes de seguridad por tolerancia ciega.

## 2. Evidencia forense DEV real 16-10-2026 11:03–11:36 CEST

Base: 16 entregas reales en `/data/odyssey-dev/state/conversations/*/delivery-results/`, `main/requests/`, `execution-checkpoints/`; 97 Markdown en `/data/odyssey-dev/vault`. 5 COMPLETED, 1 PARTIAL, 10 NEEDS_ATTENTION; mediana ~19.1 s, máximo ~66 s. Los mensajes 11:19 «Abre una tarea...» eran indicación de interacción UI y 11:08 «Cloe y Bruno» no incluía orden de almacenamiento; no usarlos como fallos semánticos representativos.

| Mensaje real | Resultado | Prueba localizada |
| --- | --- | --- |
| A mí me gusta la subida | COMPLETED | SELF vinculado a `odyssey-dev-synthetic-person` |
| Me encanta pasear por la montaña | COMPLETED | SELF vinculado |
| Ayer hablé con Maya | NEEDS_ATTENTION | temporal y Planner completados; `candidate_coverage` ValueError ~0.14 ms; cero escrituras |
| Mañana termina el sprint de Odyssey | COMPLETED | proyecto y fecha 17-10 escritos |
| Mis hijos fueron al parque, helado, película | NEEDS_ATTENTION | `candidate.source_boundary_review` → `candidate.router_revision` → segundo rechazo; no Planner |
| Cloe y Bruno | NEEDS_ATTENTION | planner `UNRECOGNIZED_REQUEST` |
| Hoy compré pan y mañana compraré leche | NEEDS_ATTENTION | dos rutas temporales; ambas rechazadas por `candidate_coverage`; la segunda empieza « y mañana…» |
| Ayer vi a Eric. Después, en otro mensaje… | NEEDS_ATTENTION | revisión de fronteras y segunda propuesta fallidas; el texto era en realidad UN mensaje |
| Ayer vi a Eric | NEEDS_ATTENTION | `candidate_coverage` ValueError; la nota canónica disponible es «Eric de Prueba» |
| Hoy hablé con Ana y Luis; Ana París; Luis vuelve | PARTIAL | 1ª ruta de «hoy hablé con» rechazada; escritos los hechos de Ana (17) y Luis (18) |
| Esta mañana trabajé en Odyssey y esta tarde revisé documentación | NEEDS_ATTENTION | revisión de fronteras y reintento rechazados |
| Ayer cené con Maya y hoy hablé con ella | NEEDS_ATTENTION | revisión de fronteras y reintento rechazados |
| Revisar presupuesto Odyssey mañana | COMPLETED | `task` creada con `target_date=2026-10-17` |
| Abre tarea, inicia Work Session… | NEEDS_ATTENTION | `candidate.source_compilation` → `SOURCE_PROVENANCE_UNREPRESENTABLE` |
| Hoy he conocido a Guillermo | COMPLETED | se creó Person Guillermo y referencia desde Day 16; cuerpo Person vacío |
| Ayer llamé a Manuela | NEEDS_ATTENTION | `candidate_coverage` ValueError; cero escrituras |

**Vault**: 97 notas de 7 tipos (person 40, calendar_day 20, task 15, work_session 10, journal_entry 5, project 4, concept 3). Guillermo sí existe tras el test; Maya y Manuela no; Cloe y Bruno y relación familiar SELF sí; Ana López, Luis y Eric de Prueba existen; XBOM sigue como proyecto. Parte del vault DEV contiene notas sintéticas heredadas de tests; distinguir sus identidades del propietario real. Los logs públicos exponen `ValueError` genérico y NO persisten el JSON completo de Planner/reviewer; NO afirmar causa exacta de Maya sin esa evidencia.

**Causa demostrada:** no es solo usuario vs entorno; existen bloqueos prewrite reales con IA genuina. Dos familias independientes: (A) revisor de fronteras Router→revision→rechazo antes de Core; (B) Planner completado→validación de cobertura falla antes de Writer. E3 se concentra en integridad de mutación, no garantiza comprensión natural. Los E2E previos no atraviesan fielmente el flujo live+vault+UI.

**Contexto perdido:** en `odyssey_runtime/candidate_route_dispatch.py`, el Router recibe `source` completo y el compilador almacena `bundle.original_source` para procedencia, pero `unit_source` es el input de Temporal/Planner por ruta, y `ExecutionContext.source = unit_source`; existe un guard que RECHAZA dar al Planner el original completo o el fragmento hermano. Algunos sujetos/fechas se heredan con pruebas tipadas. Guardar el original para comprobar *provenance* no es entregarlo como contexto de comprensión: incumple parcialmente la intención funcional anterior.

**Comparación real sin Router (aislada, sin notas/estado)**: GPT-5.6 (4 llamadas, ~0,0092 USD estimados) escaló Maya y Manuela; planificó Guillermo; agrupó tres acciones de «mis hijos» en un solo fact. Esto NO demuestra capacidad E2E, ni sustituye un Planner con evidencia canónica y Temporal. Corrobora que eliminar Router sin revisar Core tampoco es solución.

**Rendimiento:** runtime Python ~1,2 GB RSS al inspeccionar, ~805 MB swap usados, CPU inactiva tras solicitudes. No hay prueba de reindexado completo por escritura; lo costoso observado son llamadas sucesivas e incluso reiteradas a IA y notas grandes en memoria. Instrumentar durante ejecución y comparar con control.

## 3. Arquitectura objetivo propuesta (PENDIENTE DEMOSTRAR)

- **Router ligero** determina capacidades/intenciones y dependencia entre operaciones; por defecto NO corta el texto ni genera rutas Core independientes por cada hecho o fecha. Fragmentación solo cuando independientemente interpretable *y* útil (p. ej. Core vs Tasks sin referencias), y siempre reversible.
- Un **contexto común** preserva (a) `original_source` inmutable legible por todos, (b) `scope`/operaciones permitidas para no duplicar escritura, (c) evidencias canónicas de participantes/pronombres/fechas/Notes/identidades y (d) acceso por capacidad sin conceder autoridad de escritura. La mera mención del nombre no acredita identidad; Core verifica o crea.
- **Separar interpretaciones no equivale a separar hechos ni escrituras.** Para un mensaje dependiente, un pase de comprensión completo produce 1..N hechos con sujeto/fecha/identidad y enlaces. Temporal interpreta fechas sin apropiarse del significado; Apps especializadas ejecutan los fragmentos tipados apropiados. El Writer persiste, NUNCA decide semántica.
- **Orden de operaciones con dependencias**: «Hoy conocí a Maite; mañana tengo que llamarla» → resolver/crear Maite de forma canónica; registrar conocimiento; Task enlazada a Maite con fecha; sin inventar IDs ni repetir hechos. Un fallo posterior informa `PARTIAL`, conserva receipts y evita reintentos inseguros.
- Persistencia única E3 + seguridad de E2. Eliminar/simplificar múltiples revisiones redundantes sin permitir hechos o referencias sin respaldo. No nota genérica ni nuevos tipos; la idea queda aparcada por decisión del usuario.
- UI: card legible, ancho acotado, saltos de línea; mostrar qué decidió cada etapa, qué se resolvió, se escribió y qué falló. Diferenciar **ambigüedad humana** de **incompatibilidad interna**.
- No imponer formas lingüísticas al usuario. Contrato genérico, sin «if Maya», «if pronombre femenino», plantillas de conectores o parche para un ejemplo.

## 4. PoC ANTES de programar el Router ligero

**Hipótesis falsable**: el mensaje completo + contrato de contextos y scopes permite comprender sin pérdida de participantes/pronombres/fechas mejor que el actual *split*; toda decisión sometida a readback y seguridad canónica.

**Aislamiento**: worktree `feat/light-router-poc-20261016`, sin cambiar código de ejecución ni DEV/PROD. Llamadas OpenAI reales, `store=false`, cap explícito de coste/llamadas, sin enviar notas personales íntegras al proveedor. Usar el vault solo mediante copia temporal para evaluación local; minimizar detalles de notas en prompts. Conservar snapshots/receipts saneados para regresiones. Evitar invocar side-effects de n8n o activar triggers.

**Batería mínima**:
1. «Ayer hablé con Maya.» → persona nueva, hecho, fecha, enlaces.
2. «Hoy he conocido a Guillermo.» → comparación positiva existente.
3. «Mis hijos fueron al parque, después comieron un helado y por la tarde vieron una película.» → 3 hechos, misma identidad familiar probada.
4. «Hoy he comprado pan y mañana compraré leche.» → 2 fechas, 2 hechos.
5. «Ayer cené con Maya y hoy he vuelto a hablar con ella.» → correferencia «ella» y 2 días.
6. «Hoy he hablado con Ana y Luis. Ana se va a París mañana y Luis vuelve el domingo.» → 3 hechos y sin pérdida del primer tramo.
7. «Hoy he conocido a Maite, mañana tengo que llamarla.» → 2 Apps, persona nueva + Task y enlace canónico; no inventar target.
8. Frases equivalentes con otros sujetos, variación sintáctica y caso con pronombre genuinamente ambiguo (pedir aclaración, NO adivinar).
9. Repetición con entidades ya existentes para detectar duplicados.

**Criterios de éxito**: resultados medidos por hechos completos y vínculos, no por etiquetas COMPLETED; cero invenciones y cero pérdida silenciosa; readback Markdown físico sobre copia, preservación de las notas preexistentes, outputs de IA genuinos guardados y contraste con fallos del 16-10. Identificar explícitamente donde el Planner o cobertura actuales siguen siendo incompatibles y no vender esos casos como éxitos. Al menos un caso multi-App Maite debe demostrar planificación/identity handoff con IA real; la persistencia física Task exige el gate de integración posterior si el PoC exploratorio no la cubre. Medir latencia, llamadas y coste; no prometer mejor latencia sin datos.

**Puertas**: (P0) documento de decisión y diagnóstico; (P1) PoC aislada con IA; (P2) evaluar evidencias/contratos y decidir si adaptar Core o arquitectura; (P3) implementación incremental solo tras decisión; (P4) gate de IA genuina + readback + n8n/UI + rendimiento antes de DEV; (P5) aceptación manual usuario. **No declarar que P2-P5 están hechos por aprobar P0/P1.**

## 5. PoC ejecutada: RESULTADO MIXTO; no apto para DEV (16-10-2026)

**P0 registrado:** commit inicial `10b9ddf`. **P1 SEMÁNTICO:** 2 tandas nuevas de IA real, GPT-6 para capacidades y GPT-5.6 para interpretación completa. V1 10 mensajes/20 llamadas (0,0061137 USD), más caso ambiguo real Eric/Luis 2 llamadas (0,0007006 USD). V2 11 mensajes/22 llamadas (0,0071436 USD). Proveedor con `store=false`, caps locales, sin datos DEV completos enviados a modelo. Se clonaron/validaron las 97 Notes del DEV incluyendo esquema Task; después se descartaron. Los oráculos del PoC verificaron 11/11 conteos de hechos, Cloe+Bruno 3 veces, fechas por separado, Maya/ella, Ana/Luis, 2 casos de dependencia inter-App y ambigüedad Eric/Luis sin alucinación. Esto **no** implica que cada resultado de modelo sea correcto bajo cualquier reformulación.

**Problemas v1 resueltos en v2 solamente a nivel semántico:** el planificador tomaba futuro simple como Task y proponía `canonical_name` de Maya sin respaldo. Regla genérica v2: futuro no es obligación; identidad solo propuesta hasta respaldo canónico. **Problema aún presente:** Router marca Tasks en «mañana compraré leche» pero Planner elige correctamente un hecho futuro; estas decisiones deben reconciliarse en un contrato tipado. Parte del texto generado en inglés cuando el usuario habló español; el texto persistido debe preservar el idioma.

**P1 INTEGRACIÓN con infraestructura actual:** 3 casos con IA real y Core/Writer ACTUALES sobre copias desechables de DEV, resultado **0/3 escrituras/readbacks**: Maya → `CANDIDATE_COVERAGE_REVIEW_REQUIRED`, Guillermo existente → mismo rechazo, «mis hijos» → Temporal exige fecha exacta para «tarde». Embeddings del clon eran sintéticos; no es un smoke n8n+UI. Un cuarto control detallado de Maya muestra `Graph attribution evidence is invalid` ← `Every planned Core fact needs explicit source evidence`; Planner propuso Day 15/10 + helper Maya `reference_lookup_only=True`, insuficiente para garantizar que se cree la persona. **Este bloqueo sigue abierto.** No se ha desactivado ni relajado la cobertura para inventar éxitos.

**Coste total de estas llamadas PoC:** ~0,0255870 USD (estimación sin otros cargos). La interpretación aislada tarda ~7 s por caso, pero **NO es comparable** con DEV end-to-end ~19 s porque faltan Writer real, indexación productiva, n8n y UI.

**Decisión:** PoC favorable para **capacidad de comprender sin trocear** y dependencias Core↔Task; **NO demuestra aún escritura segura de extremo a extremo**. Gate siguiente **P2 imprescindible**: puente experimental, solo en sandbox, entre plan íntegro tipado y cobertura/autorización de Core; resolver identidad nueva o existente y orquestación Core→Tasks con readback, sin saltarse invariantes. Si falla, no migrar arquitectura. P3–P5 (implementación/despliegue DEV/UI/usuario) siguen BLOQUEADOS. Ver diagnóstico y artefactos exactos en `benchmarks/application_router/light_router_poc_20261016/README.md`.

## 6. Referencias vivas

- `docs/architecture/functional-roadmap.md` (seguimiento oficial y orden).
- `docs/architecture/e3-shared-mutation-gate.md` (integridad Writer).
- `docs/architecture/application-extensibility-plan.md` (aplicaciones y contratos).
- `odyssey_runtime/complete_source_handoff.py` (entrada íntegra YA existente para probar, inactiva en DEV).
- `odyssey_runtime/candidate_route_dispatch.py` (fragmentación activa y rechazo explícito del source completo en la ruta).
- `odyssey_core/candidate_attribution.py`, `odyssey_core/candidate_coverage.py` (proofs y límites de cobertura).
