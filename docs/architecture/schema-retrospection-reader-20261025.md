# Fuente retrospectiva de hechos — primer corte, solo lectura

**Estado: implementado en fuente, NO desplegado ni conectado a jobs o a la UI.** Se añadió `odyssey_core/schema_retrospection.py` como un lector pequeño que reutiliza únicamente `VaultRepository`, `parse_note`, `validate_note` y `parse_atomic_facts` existentes. No crea otro sistema de IA, índice, cola ni `PendingReference` especulativo.

## Dos destinos, mismo lector

- `discover_type`: una vez activado un tipo en el esquema compuesto, recorrer **hechos marcados de otros tipos** para una futura interpretación específica. No busca entidades hipotéticas antes de que se cree el tipo, y no devuelve sus propias notas del nuevo tipo como candidatos. Nunca crea notas automáticamente: las entidades sugeridas requerirán confirmación por lotes y deduplicación de identidad.
- `backfill_property`: únicamente recorrer notas del tipo canónico especificado, y solo si les falta la propiedad añadida. Una propiedad ya presente jamás se sobrescribe; sus valores actuales no son candidatos. El tipo y la propiedad deben existir en el esquema entregado.

Cada página lee **como máximo 25 archivos Markdown**, en orden físico estable. Conserva `note_id`, `note_name`, `note_type`, ruta contenida, hash SHA-256 físico, revisión canónica y la pareja `(locator, text)` de cada hecho marcado por Core. El siguiente cursor liga el desplazamiento al hash de `note_version_snapshot()` (ruta, inode, tamaño, mtime, ctime). Un archivo modificado o un cambio en el inventario invalida la continuación; los archivos leídos se revisan por versión antes/después y se vuelve a cotejar todo el inventario al terminar el lote. Esto **no sustituye** el CAS de E3 antes de una futura escritura.

El lector **no clasifica semánticamente** hechos, no hace llamadas GPT ni deduce identidades. Si encuentra Markdown malformado o hechos marcados inválidos, aborta la página en vez de decir que el resultado está completo. Los hechos individuales tienen límites de tamaño y número; si exceden, aborta para requerir revisión. Las notas antiguas sin hechos marcados, o cuerpos mezclados con texto libre, se señalan mediante `legacy_coverage_unverified`, sin fabricar localizadores ni afirmar que ya se han analizado sus menciones.

## Comprobaciones y pasos restantes

Hay nueve pruebas sintéticas en `tests/core/test_schema_retrospection.py`: tipos distintos, paginación y reanudación, preservación de hashes/localizadores, propiedad existente, tipos nuevos ya presentes, texto legado sin cobertura, cursor obsoleto tras edición o alta, marcador inválido y **cero escrituras**. Estos tests no equivalen a backfill en producción ni a E2E desde la app.

**Todavía falta** un trabajo duradero para orquestar por lotes, estado y pausa/reanudación; interpretar evidencia con IA (sin inventar valores o relaciones); resolver la identidad de entidades repetidas; distinguir candidatos de cambios aprobados; escribir **solo** por Core/E3 CAS con autorización y lectura posterior; manejar fuentes legadas con revisión explícita; mostrar progreso, errores y cobertura incompleta en la UI; y probar el ciclo completo con usuario sintético desde Chromium. No se ha modificado DEV, PROD ni el vault de usuario. Primero hay que conectar el trabajo a la confirmación real del esquema, no iniciarlo por anticipación en cada nota.
