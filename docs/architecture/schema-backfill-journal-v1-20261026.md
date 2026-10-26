# Diario local de enriquecimiento y recuperación — V1 (26-10-2026)

**Estado:** implementado y probado en código con vault Git sintético. Todavía no está conectado al despliegue DEV, a un worker móvil, ni autorizado para modificar datos reales o PROD.

## Por qué

Odyssey elimina trabajo al usuario: una vez aprobado el tipo/propiedad, puede decidir autónomamente qué notas actualizar. El escáner histórico genera un cursor ligado al inventario; la primera escritura cambia ese inventario, así que las escrituras no deben continuar usando el cursor de lectura anterior.

## Contrato

- LocalBackfillJob.stage recorre completamente las notas canónicas por páginas, comprueba consistencia entre páginas y solo al terminar persiste el plan de candidatos. Registra ID, ruta, hash y revisión, NO copia el contenido del Markdown. Límite de 10.000 candidatas y 8 MB por checkpoint. Una colección mayor falla sin publicar un plan incompleto.
- LocalBackfillJob.advance procesa una nota por llamada, releyendo el archivo original con validación de esquema, ID, hash, revisión y tipo. Primero intenta valores explícitos sin IA; si se inyecta un intérprete ya autorizado, puede solicitar la revisión semántica en dos pases. Las escrituras requieren Core/E3, CAS, readback y Git local.
- El diario registra "interpreting" ANTES de llamadas al modelo y "writing" ANTES de modificar Markdown, con digest SHA-256 del valor y request ID actor/vault/job/posición. Después guarda resultado y commit para recuperación. Son checkpoints privados con bloqueo, archivo temporal, fsync, reemplazo atómico, límites de lectura y rechazo de rutas simbólicas.
- Al reiniciar, una fila en "interpreting" se puede repetir, porque aún no hubo escritura. Una fila "writing" se reconcilia automáticamente: o el Markdown y revisión originales siguen intactos y no hay commit de esa solicitud, o Git demuestra un commit atribuible con contenido físico idéntico al Markdown actual, revisión +1 y hash correcto del valor añadido. Cualquier discrepancia detiene la fila como caso "attention": NO se reintenta a ciegas, ni se supone que una operación no escribió.
- Si falta conexión o un modelo instalado, los campos inequívocos se completan localmente; las descripciones que requieren IA quedan como "deferred" / "awaiting_ai". Se pueden continuar más adelante sin repetir un escaneo completo. La transmisión de hechos a proveedores externos es opcional y depende de autorización expresa.
- Los estados resumidos son updated, ambiguous, no_evidence, deferred, stale, pending y attention. El usuario no confirma nota por nota.

## Evidencias y ejemplos sintéticos

1. Dos campos explícitos se completan automáticamente y uno libre queda diferido. La reanudación conserva el progreso y no duplica commits.
2. Simulación de caída después de modificar Markdown y antes de apuntar el resultado: el siguiente avance verifica commit y contenido, y marca updated sin una segunda escritura.
3. Caída anterior a escribir, sin commit: reanuda al comprobar que no se modificó la nota.
4. Modificación externa no atribuida: bloquea la repetición automática y conserva el estado para investigar.
5. Tras trabajar offline, se añade un intérprete simulado que verifica una frase natural; la nota diferida pasa por Core/E3 sin intervención por nota.
6. Aislamiento de perfiles y esquemas, symlinks inválidos, vault vacío, 28 fuentes en varias páginas y hash obsoleto.
7. Reparación de CI: el guardia de versiones de VaultRepository ya no recorre .git, que es historial técnico, no notas canónicas. Una prueba altera repetidamente esos metadatos y comprueba que el inventario de Markdown no cambia. Las modificaciones reales de Markdown mantienen su protección.

## No implementado / siguiente puerta

- No hay vínculo del diario de escritura con la pantalla de Notas ni scheduler/background móvil. Esta clase interna no publica un endpoint ni se ejecuta automáticamente en DEV/PROD.
- No hay campaña nueva de modelo real: los 18 casos ES/FR/EN del intérprete están congelados pero no evaluados en proveedor. No habilitar escritura semántica antes de comprobar falsos positivos, abstenciones y coste autorizado.
- El mecanismo actual guarda un commit por nota; para corpus enormes necesita optimización sin perder la recuperación. El plan de un máximo de 10.000 candidatas no sustituye los ensayos de rendimiento en hardware móvil.
- Pendientes identidad/deduplicación de entidades nuevas, UX de excepciones y deshacer, prueba real navegador→n8n/Core→Markdown en DEV sintético y auditoría Codex de los cuatro roles sobre commit aprobado.

Véanse la arquitectura de almacenamiento y el contrato de interpretación semántica V1.
