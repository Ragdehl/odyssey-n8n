# E5 Events — matriz de aceptación antes de que lo use el propietario

**Estado 20-10-2026: E5 NO OPERATIVA / NO DEPLOY.** Nueve llamadas GPT reales de interpretación E5 pasaron el 20-10, sin conexión al runtime. Esta matriz es una obligación de aceptación futura, no una declaración de pruebas integradas que todavía no existen. La rama E5 es independiente de E4; ninguna prueba local reemplaza la auditoría y adopción E4 pendientes.

## Pruebas reproducibles actualmente disponibles

| Superficie | Verificado actualmente | Falta antes de declarar E5 lista |
|---|---|---|
| Modelo/reply → Events | Validación estricta grabada y **9 propuestas con GPT REAL**, operaciones ABSTAIN/CREATE/UPDATE/CANCEL/QUERY, citas fuente, nombres y fechas NO resueltos | Conexión con modelo real y segunda comprobación semántica de correcciones/cancelaciones |
| Events → Core | `DomainInterpretation` tipado sin Note IDs ni autoridad de escritura | Plan de Core normal con E2 identidad/temporal y E3 preflight/Writer |
| Events → Temporal | Citas exactas fuente, sin fechas ni horas inventadas | Valor de fecha/tz verificado por Temporal real, intervalos, DST y recurrencia acotada |
| Events → Tasks/Reminders | No hay creación por inferencia ni permisos nuevos | Acciones mixtas SOLO si lo pide el usuario y con políticas de recordatorio aceptadas |
| Events → Calendar | No se ha conectado Events a Calendar | Mostrar eventos en vistas mes/1/3/7 días, enlaces y notas; recarga idéntica |
| Persistencia E3 | Sin mutaciones en este segmento | Markdown real en vault sintético, huellas exactas, permisos actor, replay no duplicado, fallos postwrite seguros |
| n8n/browser/chat | No hay ruta Events de extremo a extremo | Chromium autenticado → n8n real aislado → GPT real → Core/Writer → Markdown → Calendar/Notes/gráfico/donut → recarga/replay |
| Rendimiento | Solo pruebas deterministas actuales, sin Events real | Latencia/memoria bajo carga en Pi y cold/warm cuando corresponda |

## Batería de situaciones obligatorias para probar yo antes de pedir una prueba del propietario

1. **Alta puntual**: «Foto del colegio el 22 de noviembre de 2026» → un evento de día, referencia al Day, sin inventar horas.
2. **Intervalo**: «Campamento del 4 al 8 de julio de 2027» → cinco días/intervalo coherente; no convertir en cinco Tasks independientes.
3. **Recurrencia acotada**: «Piscina todos los lunes del 5 de abril al 28 de junio de 2027» → solo los lunes dentro del rango, sin proliferación indefinida.
4. **Corrección**: «Cambia el teatro del martes al jueves» con dos eventos candidatos → resolución de identidad inequívoca o aclaración; cero cambios arbitrarios.
5. **Cancelación**: «Cancela la excursión» → estado correcto en evento seleccionado; no borrar la nota o días ajenos, E3 idempotente.
6. **Consulta**: «¿Qué eventos del colegio hay en noviembre?» → lectura real de Markdown/índice actual; excluye eventos cancelados si la consulta así lo requiere.
7. **Mensaje mixto**: «El viernes excursión y tengo que preparar la mochila» → evento + Task separados con sus enlaces correctos, sin convertir uno en otro.
8. **Recordatorio explícito**: «Recuérdame la víspera del teatro» → no crear notificaciones sin el contrato Reminders/permiso aprobado; devolver estado honesto si aún no existe.
9. **Fuente escolar pegada**: múltiples eventos, horarios, excepciones, material necesario; conservar todo el texto fuente, no elegir arbitrariamente eventos de entre varias menciones.
10. **Referencia pronominal**: «Hoy conozco a Ana y mañana va conmigo al concierto» → identidad enlazada solo si el contexto, E2 y un Core receipt demuestran el antecedente; cero asociaciones por descarte.
11. **Año ambiguo / DST**: «El 25 de octubre a las 2:30» sin año/zona → aclarar, no inventar instante local durante cambio de hora.
12. **Referencia repetida**: dos excursiones o dos «lunes» en la misma fuente → no vincular por posición ordinal implícita; aclarar o segmentar con prueba física independiente.
13. **Actor equivocado / replay**: sesión inválida, actor diferente, mismo request ID repetido → ninguna mutación ajena ni duplicación tras recarga.
14. **Errores reales**: interrupción n8n, caída en Writer, timeout de GPT, índice obsoleto, error JS en browser → fallo visible, sin resultado ficticio ni replay inseguro.
15. **Interfaz móvil**: enviar texto, ver estado/donut y gráfico, abrir Event/Day, editar/cancelar, regresar al chat y recuperar todo tras navegación/reinicio.

## Gate de adopción obligatorio

- Pruebas nuevas de dominio y de proveedor grabado + regresiones E2/E3/Tasks/Calendar/CrossSurface completas.
- Tests de integración sobre **vault sintético desechable** por cada operación y cada fallo (incluidas consultas después de escritura).
- Una campaña real de GPT con el contrato Events congelado y varias frases distintas, sin optimizar ejemplos concretos para que pasen.
- Un E2E autenticado en Chromium (escritorio y móvil) contra n8n real aislado → Core/Writer → Markdown → Calendar/grafo/donut, y comprobación de persistencia tras recarga, cancelación y replay.
- Auditoría independiente del **commit que efectivamente vaya a integrarse**. Aprobación de cuatro roles sobre contratos fundamentales y nueva evidencia al corregirlos; nunca heredar PASS de una fuente distinta.
- Ningún merge ni despliegue antes de cerrar estos pasos. La prueba en el teléfono del usuario es opcional de comodidad, no el detector principal de defectos.

**Regla:** si un requisito está sin desarrollar, queda `PENDIENTE`, no `PASS`; una campaña de pruebas amplia reduce sorpresas, no demuestra ausencia absoluta de errores.
