# Diario local de enriquecimiento y recuperación — V1 (26-10-2026)

**Estado:** circuito de aplicación implementado en fuente y probado con vault Git sintético. No desplegado todavía en DEV, sin worker móvil continuo ni autorizado para datos reales o PROD.

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

## Conexión Notes y autorización (corte posterior 26-10)

- Nuevo contrato schema_backfill (acciones status, stage, advance), disponible en la composición de Notes y en el validador de n8n. El navegador **no puede suministrar** valores, IDs de notas, solicitudes de confirmación ni instrucciones a la IA.
- UserSchemaRegistry.confirmed_backfill_property verifica contra el histórico de confirmaciones **publicado e inmutable** que el actor autenticado aprobó la propiedad exacta en el tipo exacto y que la revisión está activa. Conocer el ID o manipular una bandera HTML no aporta autoridad.
- ODYSSEY_SCHEMA_BACKFILL_ENABLED=1 es una puerta **independiente y apagada por defecto**, que solo puede abrirse en DEV cuando están activas las puertas de registro, confirmación y escaneo. Configurarla sobre /data/odyssey (PROD) se rechaza **antes** de crear directorios o índices. No habilita llamadas a proveedores externos: el endpoint inyecta interpreter=None deliberadamente.
- Tras aprobar una propiedad, el panel de Notas enlaza automáticamente lectura retrospectiva con un diario local. Inicia o recupera estado, hace hasta 50 avances por ejecución en primer plano, permite pausa/reanudación y muestra actualizadas, pendientes de IA, ambiguas, obsoletas y pendientes. Si la vía no está activada, informa que no hay autocompletado y **no inventa escrituras**. Crear un nuevo tipo sigue siendo **solo descubrimiento**, sin crear entidades arbitrarias.
- Cada escritura aceptada programa el refresco incremental de índices usando el mecanismo existente DerivedIndexRefreshCoordinator. Si ese registro falla después de escribir, la fila queda en estado writing y el siguiente avance reconcilia contra Core y Git, programando de nuevo sin repetir el commit. No se construye otra base de conocimiento ni cola remota.
- Pruebas de vertical real: confirmación publicada → Notes schema_backfill → Core/E3/Git Markdown sintético → recibos agregados; negativa de actor ajeno/revisión errónea/autoridad enviada por navegador; contrato n8n y panel web simulado. Chromium escritorio/móvil confirma compatibilidad visual con transporte simulado. No equivale aún a la ruta **desplegada** desde Chromium por n8n real.

## Prueba de navegador real aislado (26-10, corte siguiente)

Comando reproducible, sin credenciales ni despliegue: PYTHONPATH=. /home/ragdehl/projects/odyssey/.venv/bin/python scripts/odyssey_schema_backfill_chromium_local.py.

En dos vaults temporales, Chromium ARM64 **real** de escritorio 1280×920 y móvil 390×844 navega, pulsa el control de revisión de notas y atraviesa el **componente frontend auténtico de Odyssey**. El origen web es un proxy limitado a dos operaciones de Notes y a una identidad sintética fija. Después llama al servidor HTTP local auténtico y a los contratos reales del registro de aprobación, escaneo, diario, Core/E3 y Git. En ambas pantallas se observa **1 profesión actualizada, 1 descripción libre diferida**; tras recargar, vuelve a verse el mismo total con exactamente **un** commit de modificación (dos contando el inicial). El Markdown que no requiere actualización sigue byte idéntico. El diario no contiene el texto de los hechos. Todo el almacenamiento utilizado es efímero bajo /tmp.

**Límite esencial:** esta prueba no utiliza el n8n real, Cloudflare Access, autenticación del DEV ni proveedor GPT. El esquema fue aprobado de antemano en el fixture a través del registro canónico; la prueba de navegador empieza con la revisión de notas, no con un clic de confirmación de nuevo modelo. No constituye aceptación real del DEV desplegado y no activa ODYSSEY_SCHEMA_BACKFILL_ENABLED en el servicio. Los dos ficheros del banco de pruebas incluyen comprobaciones automatizadas de aislamiento y procedencia; el browser ARM es opt-in y no forma parte del CI universal.

## Motor n8n auténtico en entorno aislado (26-10, siguiente corte)

Dos pruebas opt-in sobre el contenedor instalado de **n8n real**, con red desconectada, sistema raíz de solo lectura, capacidades eliminadas, montajes sintéticos acotados y sin proveedor ni credenciales de usuario:

1. python scripts/odyssey_schema_n8n_engine_offline.py --run: importa un workflow temporal y ejecuta el código **exacto** del validador Notes de workflows/odyssey-online.ts mediante n8n. Resultado: **2 peticiones válidas admitidas y 4 maliciosas/mal formadas rechazadas**, sin tocar notas.
2. python scripts/odyssey_schema_n8n_core_isolated.py --run: crea un webhook real que atraviesa **Webhook → Validate Notes (código fuente real) → IF de seguridad → HTTP Request → broker local Unix → RuntimeComposition.notes → Core/E3 → Git Markdown**. En el vault sintético: **1 propiedad completada**, **1 fuente diferida**, **exactamente 1 commit nuevo**, replay sin duplicación y **5 peticiones inválidas rechazadas antes de Core**. Datos sintéticos eliminados al terminar. Reutiliza el mecanismo restringido de broker de las pruebas P4 de Odyssey.

No se trata de n8n del DEV desplegado, ni se ha ensayado una sesión Cloudflare Access, ni Chromium→n8n como **un único** recorrido, ni GPT real. Chromium→Core y n8n→Core son evidencias complementarias, **no aceptación de producto E2E**. Contratos Python offline de los dos bancos verifican las restricciones de origen.

## Prueba única Chromium → n8n real → Core/E3/Git en entorno aislado (26-10)

Comando: python scripts/odyssey_schema_chromium_n8n_isolated.py --run.

Por primera vez se ejecuta el recorrido **continuo**, sin unir resultados de pruebas separadas: Chromium ARM64 con clic real en escritorio (1280×920) y móvil (390×844) → proxy local limitado a las operaciones Notes autorizadas → socket Unix de entrada → n8n real en contenedor sin red externa → código exacto del validador Notes del workflow → IF y HTTP Request → otro socket Unix → RuntimeComposition.notes → Core/E3 → Git y Markdown temporal. El actor es un identificador fijo sintético vinculado por el n8n de prueba y la propiedad opcional ya se confirmó en el registro del fixture. El contenedor no tiene acceso al vault temporal del host y solo puede escribir su propio socket de entrada dentro del directorio de puente desechable.

**Resultados PASS en ambos tamaños:** una propiedad actualizada desde una declaración explícita, una fuente diferida para IA que permanece byte idéntica, exactamente un commit nuevo (dos contando el inicial), recuperación del panel al recargar, cero reescrituras al repetir, y nueve solicitudes autorizadas al Core sintético por tamaño incluyendo la comprobación inicial solo lectura. Al terminar se detienen y retiran los contenedores, sockets y vaults sintéticos. La prueba anterior de Chromium→Core directo sigue pasando después de este cambio.

**Límite:** n8n real en contenedor aislado no es el n8n actualmente desplegado en DEV; la sesión de autenticación y Cloudflare Access tampoco se han ensayado, ni existe una llamada GPT de proveedor real. **No declarar DEV E2E aceptado ni fusionar/desplegar por este test**. La aceptación completa requiere autorización separada para cualquier modificación de la ruta pública Cloudflare o despliegue DEV; esta prueba no requiere ni solicita esas operaciones.

## Revisión Codex focalizada y correcciones de persistencia (26-10)

Un agente Codex independiente en solo lectura del SHA 9f86b45 informó de tres problemas concretos. Es **una revisión focalizada, no los cuatro auditores finales**:

- **P1, cambio de contenido con revisión idéntica:** el guardia Core comparaba hash antes de entrar en persistencia, pero update_entity solo exigía la revisión. Ahora VaultRepository.replace_text incluye CAS opcional de bytes SHA-256 junto a la sustitución física, propagado por update_entity y AutomaticPropertyBackfill; escritores cooperantes de la misma carpeta se serializan mediante bloqueo POSIX del directorio, sin añadir archivos al vault. Las pruebas simulan una corrección externa con idéntica revisión y dos repositorios concurrentes: la escritura obsoleta se rechaza sin sobrescribir. Límite: un editor externo que ignore el bloqueo aún puede actuar en la ventana muy breve entre la comparación final y os.replace; el historial y readback siguen siendo necesarios, no es una transacción distribuida.
- **P2, historial Git largo:** la reconciliación ya no asume que el recibo está entre los últimos 100 commits. Usa una búsqueda Git con --fixed-strings --grep del ID de operación y ruta, y valida el trailer exacto, la revisión y el contenido físico. Prueba: más de cien commits posteriores en la misma nota con restauración idéntica y recuperación sin repetir escritura.
- **P2, diario alterado de forma aparentemente válida:** el checkpoint serializado tiene HMAC-SHA256 sobre el estado completo, con clave local aleatoria en el perfil privado 0600. Una fila actualizada cuya evidencia cambió, aunque sea JSON estructuralmente válido, se rechaza antes de dar el trabajo por terminado. Protege de corrupción y actores sin acceso al perfil; no puede impedir que una app maliciosa que controla íntegramente el perfil también lea la clave.

Los cambios usan Core y Git existentes, sin nuevas entidades, modelos, servicio o esquema. Validado en vaults Git sintéticos; la aceptación DEV y los cuatro especialistas Codex quedan por realizar sobre SHA corregido.

## No implementado / siguiente puerta

- El contrato y la pantalla están integrados **en fuente** bajo una puerta DEV separada, pero no desplegados; sigue faltando un scheduler/background real para Android/iOS. No se ejecuta automáticamente en DEV/PROD actuales.
- No hay campaña nueva de modelo real: los 18 casos ES/FR/EN del intérprete están congelados pero no evaluados en proveedor. No habilitar escritura semántica antes de comprobar falsos positivos, abstenciones y coste autorizado.
- El mecanismo actual guarda un commit por nota; para corpus enormes necesita optimización sin perder la recuperación. El plan de un máximo de 10.000 candidatas no sustituye los ensayos de rendimiento en hardware móvil.
- Pendientes identidad/deduplicación de entidades nuevas, UX de excepciones y deshacer, prueba real navegador→n8n/Core→Markdown en DEV sintético y auditoría Codex de los cuatro roles sobre commit aprobado.

Véanse la arquitectura de almacenamiento y el contrato de interpretación semántica V1.
