# Notas: cronología de hechos y orígenes integrados (2026-10-22)

## Objetivo de la interfaz

- Mostrar una sola etiqueta de fecha de captura, centrada y discreta, por día, sin la palabra «Añadido».
- Agrupar los hechos propios del mismo día y mantener la fecha de captura cuando se trate de backlinks. La fecha de la nota de origen NO sustituye la fecha de captura del hecho.
- Integrar las frases entrantes en la misma cronología. Se conservan sus referencias y permisos; no se copian los hechos a Markdown ni se cambian los enlaces.
- Distinguir referencias entrantes mediante línea lateral verde, fondo ligeramente diferenciado y botón «↖ Desde: Día 28 oct.» (o nombre de nota).
- Cuando no exista fecha de captura fiable, mostrar «Sin fecha de registro» sin atribuir un día inventado.
- Mover «Creada» y «Actualizada» a «Detalles de la nota», plegado por defecto. Mantener propiedades de tareas/eventos visibles.
- Las subtareas mantienen su panel especializado, sin duplicar su relación inversa como un hecho del timeline.

## Implementación

Cliente únicamente: `odyssey_web/notes.js`, `odyssey_web/styles.css`.
Se crea un `createFactTimeline` reutilizado por hechos locales y snippets
de backlinks. Usa `Added dd-mm-yyyy` ya presente en los `body_blocks`
y en la procedencia de cada snippet; no necesita una nueva API ni alterar
Core/E3. La fecha `Added` con enlace a `calendar_day` conserva navegación.
Grupos ordenados por fecha ISO descendente, elemento «Sin fecha» al final.
Backlinks asíncronos comprueban id de nota activa antes de renderizar.

## Evidencia

- `tests/odyssey_web_notes.test.mjs`: enlace de día, integración local+
  backlinks en la misma fecha, clasificación sin fecha, origen clicable,
  ausencia de tarjetas antiguas, regressiones Notes/Tasks/Work Sessions.
- Vista real en Chromium móvil 390×844 y escritorio 1280×960 sobre la API
  **read-only de DEV** y activos del frontend candidatos (sin deploy):
  nota `Odyssey DEV Synthetic User`, 8 grupos únicos de fechas,
  43 referencias entrantes, «Añadido» ausente, metadata plegada,
  0 errores JS y sin desbordamiento horizontal.
  Script permanente `scripts/odyssey_notes_timeline_browser.cjs`.
- Prueba completa `scripts/odyssey_cross_surface_gate.py` y aceptación
  final DEV se anotan tras terminar.

## Ramas, PR históricos y seguridad

E1 `291238b` y E2 `ad4049b` son ancestros del desarrollo E6 y todo el
código validado sigue íntegro en Git. Dos PR draft antiguos #153 y #154
no son desarrollo perdido, pero GitHub `dev` aún quedó en `4944881`.
La consolidación será fast-forward a dev cuando el nuevo frontend
pase pruebas y DEV, sin merge-squash ni tocar `main`/PROD. No borrar
worktrees de agentes sin comprobar sus estados individuales.


## Auditoría independiente de interfaz

La primera revisión read-only de `7fbbd90..078c66b` devolvió
**FAIL** por dos defectos concretos: (1) un backlink cuyo bloque
era por sí mismo el encabezado `Added dd-mm-yyyy` podía caer en
«Sin fecha» y mostrar el marcador bruto; (2) fecha y origen tenían
contraste insuficiente en fondo claro. Evidencia:
`/home/ragdehl/projects/.odyssey-agent-runs/ui-notes-unified-audit-20261022/findings.md`.

Se corrigió el encabezado enlazado usando la fecha validada del bloque
como prueba de captura y mostrando «Referencia desde el encabezado de esta
fecha» en lugar del marcador técnico; sin inventar fecha cuando no existe.
Nueva regresión específica `tests/odyssey_web_notes.test.mjs` PASS.
Colores ajustados a `#596476` (contraste 5,98:1 sobre blanco) y
`#325d60` (contraste 7,32:1 sobre blanco), superiores a 4,5:1.
Primera auditoría histórica conservada; revisión focal final y gate
completo se actualizarán según resultados.
