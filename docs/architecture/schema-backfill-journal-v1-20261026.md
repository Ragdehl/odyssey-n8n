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

## Aceptación parcial en DEV desplegado (26-10-2026)

**Autorización:** exclusivamente Cloudflare DEV, despliegue fijo 5df4772, copia/rollback, datos sintéticos y autocompletado determinista temporal. No IA de pago ni PROD.

1. Backup privado verificado: /data/odyssey-dev/runtime/schema-backfill-deploy-backup-20261026-1814, con anterior 5e340da, vault/estado DEV (2,4 MB comprimidos) y n8n DEV parado para obtener backup consistente (115 MB). PROD no se detuvo.
2. Cloudflare actualizó solo /api/schema-scan.js; comprobación final 17/17 MATCH, configuración PROD y Cloudflare Access inalteradas.
3. El deploy oficial finalizó con commit, assets web y n8n en SHA 5df4772 y HTTP 200. Flags exclusivos de DEV para esquema, confirmación y escaneo habilitados. Asistente IA 0. Autocompletado determinista 1 solo durante la aceptación.
4. Core/E3 creó una ficha persona sintética con un único hecho canónico de profesión, con commit Git solo de esa ficha. No cambió ninguno de los 166 Markdown anteriores (verificación hash).
5. Chromium real en la interfaz Notes móvil confirmó manualmente la propiedad de prueba profesion_e2e_20261026, revisión 1. Se observó el reinicio y publicación del esquema, pero el ensayo **no registró ninguna petición de escaneo admitida en el proxy del navegador**; terminó por tiempo de espera. La causa puede ser el filtro del banco o un fallo del frontend: no atribuirla sin aislamiento. E2E UI automático NO APROBADO.
6. El diagnóstico sin respuestas simuladas y a través del n8n DEV real efectuó el escaneo y procesamiento de 56 candidatas. Resultado: 1 nota sintética actualizada, 55 diferidas para IA, 0 pendientes, 0 ambiguas, diario awaiting_ai; git y readback correcto. La nota alcanzó revisión 2 con el valor médica; las 166 notas anteriores y las 50 rutas preexistentes con cambios no se alteraron/confirmaron.
7. Chromium móvil y escritorio, mostrando frontend del DEV desplegado y peticiones de lectura al n8n DEV auténtico, comprobó propiedad nueva, nota visible, recarga sin errores ni desbordamiento. PASS. Se usó origen local seguro: NO equivale a una sesión exterior autenticada de Cloudflare Access.
8. Tras la prueba se puso ODYSSEY_SCHEMA_BACKFILL_ENABLED=0 en el drop-in exclusivo DEV y se reinició el servicio; los datos de esquema de prueba permanecen válidos. Sin GPT de pago, sin merge y sin cambios PROD.

**Siguiente puerta:** depurar recuperación/autoarranque del escaneo desde la UI y repetir en DEV, más aceptación Cloudflare autenticada y modelo real con autorización de coste independiente. Los cuatro auditores Codex finales siguen pendientes.

## Corrección de autoarranque desde la confirmación — fuente posterior al DEV 5df4772

El ensayo autorizado de DEV del 26-10 confirmó una propiedad mediante Chromium, pero no observó las solicitudes de escaneo en el proxy de aceptación. Al reproducir el estado queued identificamos **un falso criterio de aceptación del banco**: al abrir un tipo existente, el panel preliminar discover_type ya estaba visible para la revisión anterior. El banco interpretaba esa visibilidad como activación del nuevo modelo y dejaba de consultar el estado. El registro de la prueba anterior registra schema_confirm, pero ni una solicitud posterior schema_status de activación.

**Corrección de producto en fuente (odyssey_web/schema-model.js):**

- Tras la única confirmación humana, ocultar el panel de lectura de la revisión anterior mientras la activación está pendiente; nunca comunicar su visibilidad como prueba de activación.
- Consultar el estado del ID original cada 3 segundos, máximo 120 veces (seis minutos) en el código corregido; no reenviar confirmaciones ni habilitar llamadas a proveedores o escrituras fuera del flag. Los errores temporales permiten recuperar la misma solicitud; el cierre invalida los callbacks.
- Guardar en sessionStorage de Notes el objetivo de escaneo ligado al ID original para recuperar la propiedad tras reabrir. Validar de manera estricta forma, tipo y revisión y exigir la revisión activa publicada. El navegador no otorga permisos: cada operación sigue siendo verificada por actor y esquema en Runtime/Core.
- Una vez active, iniciar escaneo y diario en lotes. Sin modelo evaluado, la interpretación libre se deja deferred.

**Regresión:** tests Node cubren queued → queued → active, una sola confirmación, ocultación del panel antiguo, reabrir conservando el objetivo, almacenamiento adulterado y cancelación al cerrar. Chromium ARM64 real en escritorio y móvil con backend simulado recorrió clic → activación → escaneo → progreso awaiting_ai. **La recuperación ampliada a seis minutos está verificada en fuente, NO desplegada.** DEV está en 1ceee02 con ODYSSEY_SCHEMA_BACKFILL_ENABLED=0 después de la aceptación parcial.

## Reintento autorizado con DEV real 1ceee02: aceptación NO aprobada por arranque lento

- Antes del deploy: rama origen limpia y CI GitHub de 1ceee02 aprobado; respaldo específico y verificado de vault/estado DEV (2,4 MB) y volumen n8n (117 MB), marcadores Git y flags reversibles en schema-activation-acceptance-1ceee02-20261026. Cloudflare MATCH, Access/PROD fuera de alcance. Deploy oficial completó SHA 1ceee02 en checkout, runtime, assets web y n8n, salud HTTP 200. Asistente IA desactivado.
- Core/E3/Git creó una ficha persona nueva puramente sintética con el hecho profesion_e2e_20261026_v2: médica. El registro estaba en revisión 1. Chromium real en origen local seguro mostró el editor, introdujo una propiedad nueva y realizó **una sola confirmación humana**. Se publicó la revisión 2 y arrancó el reinicio gestionado.
- **Bloqueo confirmado:** el navegador envió schema_status del ID original 24 veces, sin repetir confirmación, pero agotó el límite de 24 x 3 segundos antes de recibir active. El arranque de Raspberry excedió esa ventana. Al recuperarse, el registro Core, consultado en lectura mediante n8n DEV real, devolvió active de la revisión 2 con ese mismo ID. El navegador agotó su espera **sin llamar a schema_scan ni schema_backfill**. No se utilizó una petición manual para completar el resultado.
- **Estado seguro:** se volvió a apagar ODYSSEY_SCHEMA_BACKFILL_ENABLED=0 solo en DEV y se reinició el runtime; GPT permaneció apagado. Verificación SHA-256: **167 notas anteriores intactas (0/167 modificadas)**; solo se creó la ficha sintética nueva, revisión 1, sin valor enriquecido. El registro DEV conserva revisión 2, commit 1ceee02; PROD Git HEAD idéntico al anterior.
- **Corrección en fuente (NO desplegada):** ampliar read-only a 120 consultas cada 3 segundos (máximo seis minutos con la pantalla abierta), el mismo ID y sin nuevas aprobaciones; los callbacks se invalidan al cerrar. Regresión Node simula 45 consultas entre queued y fallos de conexión, después active y escaneo/backfill automático. Si tampoco se activa dentro del plazo, conserva la recuperación manual y nunca repite confirmación.

**Pendiente:** gate y CI del nuevo SHA, nueva aceptación de un solo clic desplegado con datos sintéticos, sesión externa Cloudflare Access y evaluación semántica GPT autorizada. La publicación y deployment funcionan, pero **NO está aprobada la escritura automática iniciada desde la interfaz**. Cuatro auditorías especialistas todavía pendientes.

## Aceptación DEV de un solo clic en 4e721a0 — PASS (26-10-2026)

Con autorización expresa del usuario, DEV se actualizó al SHA 4e721a07e4463bbc111053a3c5ddd8fed4cf99f0, con CI GitHub aprobado. Ruta Cloudflare DEV en MATCH 17/17; sin modificaciones PROD. Respaldo nuevo verificado en schema-activation-acceptance-4e721a0-20261026: vault/estado DEV, volumen n8n, HEAD PROD, marker y flags; archivos anteriores indexados por SHA-256.

**Prueba funcional sin atajo de diagnóstico:** Chromium real cargó frontend desplegado sobre localhost seguro, interactuó por clic con editor de Notes, obtuvo una única confirmación de la propiedad Persona profesion_e2e_20261026_v3, esperó sin pulsar el botón manual, observó esquema activo revisión 3, inició automáticamente scan y backfill mediante n8n DEV real y recibió 1 propiedades completadas en la UI. Traza: **9 avances del scan**, **42 avances del backfill**, una sola operación schema_confirm, navegador PASS. Core/E3/Git escribió exactamente una nueva ficha sintética con profesion_e2e_20261026_v3=médica y revisión 2. SHA-256 confirmó **0 cambios en 168 notas anteriores**, una nueva nota. Git PROD HEAD siguió igual.

**Límites:** al cerrar la pantalla tras la primera escritura verificada, la UI contabilizaba **40 pendientes de IA y 17 aún pendientes de procesar**. Esto NO demuestra trabajo completado en segundo plano ni autoriza al modelo a escribir. La aceptación prueba activación automática y primera actualización real, no agotar todo el corpus. Chromium usó proxy localhost con operaciones tipadas hacia n8n DEV; **NO** autenticación externa Cloudflare Access. Sin GPT de pago ni auditoría final Codex.

**Estado seguro posterior:** ODYSSEY_SCHEMA_BACKFILL_ENABLED volvió a 0 y DEV se reinició; el asistente semántico permanece apagado. Código, web y workflows desplegados en 4e721a0, runtime/n8n healthy y Cloudflare MATCH, copias verificadas y PROD intacto. La ficha sintética de prueba sigue identificada en DEV. Próxima fase: validación semántica real bajo autorización de coste independiente, identidad/deduplicación/UX y cuatro auditores finales antes de merge.

## Auditoría Codex sobre la integración y reparación (26-10-2026)

Una primera planificación completa desde 07dd13b hasta 1273ea7 se bloqueó por límite seguro de evidencia: el diff de 796 KB supera el paquete autorizado de 256 KB; **ningún auditor consumió modelo en ese intento**. La siguiente revisión delimitó honestamente la integración (35 archivos, diff de unos 249 KB desde 6c5a197, conservando acceso read-only al código anterior) con los cuatro roles planificados. Su supervisor pasó el gate Python/JS, aceptación y Ruff. Los recibos independientes obtenidos fueron:

- **Generalidad: PASS con advertencia:** faltaba una regresión para un tipo nuevo arbitrario y el rechazo de tipos administrados por Apps.
- **Calidad: FAIL, dos defectos bloqueantes reparables:** la autorización original para añadir una propiedad sobrevivía a un cambio posterior de su descripción por otro actor; y un corte antes de escribir la clave de integridad podía dejar una clave vacía permanente. Se corrigió la autorización para seguir al actor que confirmó la última definición de esa propiedad y se publica la clave completa, fsynced, por hardlink atómico. Se añadieron tests de sucesión de actores, cortes antes de publicación, tipo Libro + atributo genre y rechazo de tipo Task ajeno al esquema ordinario.
- **Pruebas y Rendimiento: NO EJECUTADOS** en esa ronda. Las sesiones Generalidad+Calidad consumieron 282214 tokens reportados; el supervisor bloqueó preventivamente el resto por su reserva obligatoria de 105000 tokens, con solo 17786 disponibles. No hay cuatro PASS ni permiso para merge. Recibos conservados en el job privado schema-backfill-integ-4role-20261026.

Estos cambios posteriores son **solo código fuente y regresiones sintéticas**; DEV sigue desplegado en 4e721a0, con escritura automática e IA pagada desactivadas y PROD fuera de alcance. Tras el gate completo y CI habrá que revisar el nuevo SHA con los especialistas restantes y comprobar las correcciones con independencia; no reutilizar el PASS del SHA antiguo como aprobación de la reparación. El alcance anterior del asistente semántico sigue requiriendo un examen independiente separado.

## Seguimiento de P2 + ensayo de escala en Raspberry (código posterior, 26-10)

- **Resultado de escritura desconocido:** el servidor HTTP Notes devuelve 409 con código fijo SCHEMA_BACKFILL_OUTCOME_UNVERIFIED cuando el escritor o el refresco de índices fallan sin poder probar todavía si Git confirmó. Notes muestra «Verificar y continuar» y exige reconsultar el mismo diario; jamás repite la confirmación humana ni suministra texto/ID de nota. Regresión con servidor HTTP real: error de cola después de commit físico, recibo 409 sin mensajes privados, reanudación validada por Git y ningún commit duplicado.
- **Índices:** regresión en vault temporal, Core/E3/Git real, DerivedIndexRefreshCoordinator y ContextIndex SQLite real: el campo nuevo entra en el filtro de Notes tras wait_until_clean, y NoteDetail refleja el mismo valor. No se creó ningún índice de autoridad alternativo.
- **Escaneo optimizado de staging:** en lugar de volver a ejecutar dos inventarios físicos completos por CADA página de 25, el diario usa un inventario inicial compartido, verifica las notas seleccionadas antes/después de leerlas y exige una segunda comprobación de inventario completo **antes** de persistir el plan. El escáner interactivo autónomo conserva sus garantías originales por página. Se prueba que son exactamente dos inventarios para 54 notas y que una edición en página ya visitada o una nota nueva durante el escaneo impiden publicar el checkpoint. Las mutaciones siguen requiriendo CAS al aplicar cada nota.

**Mediciones locales, solo sintéticas, Raspberry Pi ARM64 4 GiB (sin GPT, sin DEV/PROD):**

| Candidatas | Staging antes | Staging después |
|---|---:|---:|
| 50 | 0,02 s | No se volvió a medir |
| 250 | 0,18 s | No se volvió a medir |
| 1.000 | 1,95 s | No se volvió a medir |
| 2.500 | 11,42 s | 1,25 s |
| 5.000 | 44,61 s | 3,62 s |
| 10.000 | No se midió | 11,40 s |

Memoria RSS máxima reportada a 10.000: 60,6 MB; 2.500/5.000 optimizado 46,5/51,4 MB. SwapFree estable durante estas ejecuciones. El ensayo anterior de 50 commits individuales de Git: 1,97 s total, p50 39,4 ms y p95 40,1 ms, **sin refresco asíncrono de índices**. Benchmarks independientes con vault temporal y Git sintético; no son garantía de p95 con notas grandes, consumo térmico, contexto de usuario real, batería móvil, servicio embebido ni todo el backfill de 10.000 escrituras. La optimización y las pruebas están solo en la rama de fuente mientras DEV conserva el SHA desplegado 4e721a0. Los dictámenes Codex para el SHA anterior son evidencia histórica: se requiere revisión de esta modificación antes de aprobación final.

## Medición de escritura + actualización ContextIndex (corte posterior, SHA 5116f9b)

**Banco en Raspberry ARM64 sobre tres vaults Git sintéticos efímeros, sin DEV/PROD ni proveedor:** schema real de Persona + propiedad opcional, LocalBackfillJob + AutomaticPropertyBackfill + GitHistoryRecorder, con ContextIndex SQLite real y embedder determinista sin red. Antes se inicializó el índice, luego cada commit de propiedad notificó y completó inmediatamente el refresco del índice contextual. Al terminar, una consulta Core Notes filtrada por profesion = médica devolvió exactamente todas las notas actualizadas. Son medidas seriales de carga; no incluyen el índice semántico completo de producción.

| Notas | Git + diario + ContextIndex (total) | Mediana por actualización | p95 por actualización | Coste agregado ContextIndex |
|---|---:|---:|---:|---:|
| 25 | 0,91 s | 36,1 ms | 36,6 ms | 0,15 s |
| 100 | 7,41 s | 73,4 ms | 77,4 ms | 1,47 s |
| 250 | 37,17 s | 148,3 ms | 152,7 ms | 8,03 s |

Máxima RSS de los ensayos: 53,0, 57,6 y 71,5 MB respectivamente, con SwapFree estable (1195 MB). El coste por actualización crece con el tamaño de vault: no extrapolar el staging rápido a un lote de escrituras de 10.000 notas. Un perfil aislado de **cinco** commits en vault de 250 notas, bajo cProfile (incluye la propia sobrecarga del profiler), contó **2520 parseos de notas** (aproximadamente dos recorridos completos del vault por escritura). Un recorrido proviene de CanonicalMutationGate.prepare para resolver ID único, el otro de GitHistoryRecorder.record para atribución y undo seguro. El coste del índice ContextIndex también aumenta al comprobar inventario. Optimizar requiere reutilizar evidencias de identidad/frescura con una prueba de unicidad y CAS equivalente, no retirar arbitrariamente esos recorridos o crear un Git commit agregado sin recuperación granular.

**Evidencia y siguiente puerta:** el código 5116f9b superó CI GitHub y la suite local, y el benchmark muestra materialmente el siguiente trabajo: diseñar un índice local verificable de rutas/IDs con inventario coherente, mantener protección de duplicados, cambios externos y reanudación tras caída, y medir el índice semántico completo. Solo después valorar 10.000 escrituras sin intervención humana y trabajador móvil. No se ha desplegado este SHA ni existe aceptación de Cloudflare Access autenticada o de IA de pago.

## Revisión focalizada de 5116f9b y cierre de contrato de escáner público

Una revisión read-only Codex independiente y **acotada exclusivamente al cambio 7d95125..5116f9b** detectó **un P2 reparable** en la API: aunque el diario privado sí garantizaba la verificación final del inventario, el método público scan_schema_sources aceptaba opcionalmente un _staged_inventory antiguo y podía devolver una página incompleta sin advertir de nuevas fuentes. Recibo en el informe local de Codex; no equivale a cuatro nuevas auditorías especialistas ni a evaluación semántica.

**Corrección posterior en fuente:** scan_schema_sources ha recuperado la firma pública sin posibilidad de aceptar instantáneas previas y exige comprobaciones completas por página. El constructor _scan_schema_sources_page, deliberadamente interno, solo produce evidencias preliminares para el diario, cuya última verificación del inventario es obligatoria antes de crear el checkpoint. Nueva regresión de API: intentar inyectar un inventario anterior provoca TypeError y un escaneo público normal detecta la nota recién añadida. Tras separar API pública y constructor provisional, el banco opt-in de **10.000 notas sintéticas** sobre Raspberry volvió a pasar: 10,98 s de preparación, CPU 10,97 s, memoria RSS máxima 60,3 MB; comparable a los 11,40 s anteriores, no un cambio de escritura o de seguridad. Las regresiones del diario siguen detectando mutación de la primera página o nota nueva y rechazan toda publicación del plan. No se habilitan escrituras nuevas ni se toca el modelo.

## Auditoría incremental y perfil de escala del 27-10 (solo fuente, SHA 718a6eb)

Revisión independiente Codex de cuatro roles, fijada al commit `718a6eb`, con diff de reparación `7d95125..718a6eb`: **Generalidad PASS, Calidad PASS con advertencias externas, Pruebas BLOCKED por falta de aceptación del mismo SHA en Chromium/Access y campaña GPT real, Rendimiento BLOCKED por falta de prueba completa de escrituras + todos los índices a escala 10.000**. No equivale a una auditoría de integración íntegra ni a cuatro aprobaciones. El intento original con base `6c5a197` quedó bloqueado **antes de consumir modelo** porque excedía el paquete de evidencia de 256 KiB. El intento acotado consumió 254.648 tokens reportados y no realizó modificaciones. Evidencia privada: jobs `schema-backfill-final-sha-20261027` y `schema-backfill-final-delta-20261027`. CI y suite transversal en el SHA de código `473871d`: 2.263 Python + 252 JavaScript, 7 subtests PASS; commit posterior `718a6eb` solo añadió el brief de auditoría y volvió a pasar su gate de commit/CI.

**Banco adicional Raspberry Pi ARM64 de 4 GiB:** reproducible con `PYTHONPATH=. python3 benchmarks/indexing/probe_schema_backfill_scale.py --scales 1000:12,5000:8,10000:5` desde la raíz de Odyssey, con memoria mínima disponible de 900 MiB y datos totalmente sintéticos. Se construyeron bóvedas Git efímeras con 1.000, 5.000 y 10.000 notas sintéticas; `LocalBackfillJob` real, un commit Git por propiedad, `ContextIndex` SQLite real y embedder determinista sin red. Cada muestra verifica `NotesQueryService` sobre exactamente las propiedades escritas; NO procesa 10.000 escrituras ni carga el modelo de embeddings neural de producción.

| Notas en la bóveda | Muestra de escrituras | Staging | Escrituras + ContextIndex total | Mediana por escritura | Percentil 95 observado en la muestra |
|---|---:|---:|---:|---:|---:|
| 1.000 | 12 | 0,41 s | 6,22 s | 502 ms | 508 ms |
| 5.000 | 8 | 3,89 s | 20,27 s | 2.422 ms | 2.441 ms |
| 10.000 | 5 | 12,15 s | 25,75 s | 4.797 ms | 4.806 ms |

RSS máxima acumulada del proceso 76,4/102,1/133,4 MiB respectivamente; `SwapFree` no cayó materialmente durante las muestras (aprox. 1,22 GiB). p95 con 5–12 observaciones **no es SLA ni estimación estadística robusta**. Los tiempos demuestran coste creciente por escritura casi proporcional a la cantidad de notas; no se extrapolan a 10.000 commits, a hardware móvil ni al índice semántico completo. El servidor avanza **una fuente por llamada**, la UI pausa tras 50 avances por sesión y el diario reanuda sin repetir escrituras inciertas, pero esto limita cada iteración, **no soluciona el cuello de botella O(N)**.

**Siguiente puerta de ingeniería:** perfilar el doble recorrido físico de identidad/Git y el inventario del índice con pruebas adversariales de cambios externos y colisiones; diseñar un catálogo verificado o una transacción acotada que reutilice evidencia de unicidad/frescura sin relajar CAS, E3, actor, journal duradero ni historial/undo por nota. Repetir comparación y probar un lote grande representativo *antes* de declarar que 10.000 actualizaciones funcionan o activar un worker móvil. No bajar silenciosamente la autonomía de escaneo a 250 fuentes.

## Optimización de escrituras E3/Git con catálogo canónico efímero — 27-10-2026 (fuente, NO DEV)

**Problema reproducido:** cada una de las escrituras de propiedad llamaba a `CanonicalMutationGate.prepare` (recorrido validando todas las notas por ID) y `GitHistoryRecorder.record` (segundo recorrido validando todas las notas para atribuir ID→ruta). ContextIndex añade su propio coste de inventario y refresco. Que el navegador pause tras 50 avances y el índice pueda refrescarse fuera de la petición no evita CPU, I/O ni batería en el dispositivo móvil.

**Cambio de código (solo backfill):** `AutomaticPropertyBackfill` tiene un `CanonicalMutationInventoryCache` limitado al proceso y su propia bóveda. En el primer avance se parsea y valida íntegramente el Markdown canónico; en los siguientes solo se reutiliza la identidad si coincide la lista completa de rutas y su huella física. Después de cada escritura con recibo E3+Git válido, el catálogo se renueva releyendo la nota exacta y comprobando que **todas las demás** mantienen la versión de antes. GitHistory reutiliza la prueba del mismo avance, vuelve a validar todas las versiones y la nota modificada, y conserva el commit/undo individual. Si falta prueba, hay cambio externo, nota nueva, duplicado, corrida, crash o un índice derivado no fiable, se vuelve al recorrido físico completo (o se rechaza la escritura y se conserva el estado de resultado incierto). **Nunca se emplean filas SQLite para autorizar identidad negativa**. No hay caché persistente ni permisos de escritura nuevos; si muere el proceso la siguiente sesión reconstruye desde Markdown. El presupuesto de lectura pasa de dos parseos de toda la bóveda *por escritura* a un parseo inicial y comprobaciones físicas posteriores, conservando parseo completo ante cualquier drift inesperado.

**Banco reproducible:** `PYTHONPATH=. python3 benchmarks/indexing/probe_schema_backfill_scale.py --scales 1000:12,5000:8,10000:5`; Raspberry Pi 4 de 4 GiB, Git y ContextIndex reales, embedder determinista, notas efímeras sintéticas, ejecución serial, sin DEV/PROD ni llamadas a GPT.

| Notas en la bóveda | Mediana anterior por escritura | Mediana con caché canónica | Mejora aprox. | Muestra de escrituras |
|---|---:|---:|---:|---:|
| 1.000 | 502 ms | 302 ms | 40 % | 12 |
| 5.000 | 2.422 ms | 1.415 ms | 42 % | 8 |
| 10.000 | 4.797 ms | 2.800 ms | 42 % | 5 |

La caché final incluyó comprobación de que añadir un ID duplicado tras el staging o tras la primera escritura la invalida, que cambiar otra nota obliga a recalcular el mapa canónico, que una duplicación después del write impide atribuirlo en Git y que un origen SQLite modificado no autoriza Core. El script no mide 10.000 **escrituras**, SLA/p95 robusto, GPT real, índice semántico neural, concurrencia, energía o el scheduler de Android/iOS. La mediana inicial de cada tanda incluye el primer coste de parsear toda la bóveda; la mejora no es O(1) porque aún se revisan todas las versiones y ContextIndex. La ruta actual UI→50 avances con pausas **no constituye aún un worker móvil real en background**; en móvil hará falta priorización, cuotas CPU/batería y persistencia de reanudación independiente de la pantalla.

**Optimización adicional ContextIndex (fuente, 27-10):** en `refresh_notes`, el inventario de rutas/versiones se obtiene una sola vez con `repository.note_version_snapshot()` (sin seguir symlinks, directorios estables), en vez de `list_markdown_paths()` seguida de `file_version()` para cada nota. Antes del commit SQLite sigue existiendo la segunda comprobación física global. Para cambios solo de frontmatter se conservan los enlaces existentes **únicamente cuando** todos los targets modificados retienen ruta/identidad, alias, body y filas de hechos verificadas contra la proyección previa; si hay altas, bajas, cambio en cuerpo/fact, discrepancia de SQL o drift ajeno, se recalcula todo el grafo. Las propiedades, atributos, embeddings y inventario de las fichas cambiadas sí se actualizan siempre. Nuevos tests prueban salto de grafo en metadatos, refresco global en body edit y reparación ante un estado de hechos incompatible.

**Medición repetida tras AMBAS mejoras de ContextIndex** en la misma sonda y máquina, muestras independientes (no p95 estable):

| Notas | Core/Git anterior | Con refresco de índices optimizado | Refresco ContextIndex anterior → nuevo | Muestra |
|---|---:|---:|---:|---:|
| 1.000 | 302 ms | 252 ms | 120 → 69 ms por nota aprox. | 12 |
| 5.000 | 1.415 ms | 1.174 ms | 578 → 339 ms por nota aprox. | 8 |
| 10.000 | 2.800 ms | 2.332 ms | 1.146 → 675 ms por nota aprox. | 5 |

Total desde el código inicial 10k 4.797 → 2.332 s (~51 %), aún O(N) por comprobaciones de integridad y todavía lejos de una campaña real de 10k escrituras. La sonda usa `on_updated` **síncrono** para medir explícitamente el refresco después de cada escritura, mientras que el runtime productivo usa el coordinador asíncrono y la barrera de lectura; no es medición del teléfono ni del end-to-end n8n/GPT.

## Agrupación acotada de refrescos derivados — 27-10-2026 (fuente, no desplegado)

**Problema:** el coordinador ya ejecutaba refrescos en un daemon thread con barrera de lectura, pero tras cada nota Core/Git lo activaba inmediatamente. La escritura siguiente habitualmente llegaba después y desencadenaba otro barrido global de versiones y de SQLite. Reutilizar una caché de identidad canónica y acelerar ContextIndex no eliminaba este coste repetido.

**Cambio mínimo en el coordinador existente:** solo `LocalBackfillJob.on_updated` de la composición llama a `DerivedIndexRefreshCoordinator.schedule_backfill` en vez de `schedule`. El primer ID fija una **ventana máxima de 6 s** que posteriores escrituras no prolongan; 8 IDs distintos solicitan un refresco inmediato (umbral de activación, **no** tamaño máximo de batch). El worker combina IDs solicitados y deja la fuente Markdown, journal HMAC, autorización por actor, CAS, readback y commits Git **individuales** sin cambios. Las demás escrituras conservan `schedule` inmediato y fuerzan también a procesar cualquier lote pendiente. `wait_until_clean` adelanta inmediatamente el refresco si una consulta lo necesita; solo devuelve control tras terminar el índice o produce error de lectura, nunca sirve voluntariamente una proyección atrasada. Si un refresco falla, sus IDs quedan registrados como pendientes en memoria y un intento posterior los vuelve a incluir, incluso si el nuevo commit afecta a otra nota. Las excepciones no desaparecen por un refresco parcial posterior.

**Recuperación:** si el proceso desaparece con IDs en espera, esos IDs en memoria desaparecen (no existe una cola durable nueva), pero los cambios siguen físicamente en Markdown y Git. En el arranque, `p4_indexes_reusable` compara los índices ContextIndex y SemanticEntityIndex con el inventario canónico; detecta el desfase y exige reconstruir. Prueba integrada nueva: después de 6 commits Git antes del refresco, el reutilizador **rechaza** los índices viejos; después de un único batch ContextIndex + SemanticEntityIndex, los reutiliza, y una búsqueda por propiedad recupera las seis notas y sus hashes. Suite de concurrencia: agrupación, vencimiento fijo, lectura anticipada, prioridad de escrituras ordinarias, fallo que bloquea al lector, arrastre de IDs de intentos fallidos y límites de configuración. No equivale a programar un worker duradero Android/iOS.

**Prueba reproducible** `python3 benchmarks/indexing/probe_schema_backfill_batches.py --scales 250:12,1000:12,5000:8,10000:5`, y `--with-semantic` para incluir el índice semántico genérico. Bóvedas Git sintéticas y descartables, embedder determinista sin red, índice inicial previamente construido. El tiempo total contiene los commits E3/Git uno por nota, journal, un refresco agrupado y **la espera explícita del lector**; no contiene el staging ni el índice inicial. Una medición concreta, sin garantía estadística:

| Total notas | Escrituras probadas | Refrescos ContextIndex | Total batch ContextIndex | Serie por nota (referencia f73242a) | Total batch + semantic |
|---|---:|---:|---:|---:|---:|
| 250 | 12 | 1 | 0,85 s | no medida comparable | no medido |
| 1.000 | 12 | 1 | 2,60 s | 3,33 s | 2,69 s |
| 5.000 | 8 | 1 | 8,68 s | 10,87 s | 9,05 s |
| 10.000 | 5 | 1 | 12,20 s | 14,43 s | 13,08 s |

A escala de 10.000 notas y 5 commits, el paso de 14,43 a 12,20 s reduce ≈15 % el tiempo total frente al anterior índice por nota, además de las anteriores optimizaciones Core/Git. En la variante `--with-semantic`, 10k y 5 commits: un lote context+semantic tardó 1,59 s; hashes semánticos y filtro Notes se contrastan con Markdown físico, 6 commits Git (incluido baseline). **Aún NO** son 10.000 escrituras, todos los índices App Tasks/Events, FastEmbed/ONNX real, medidas móviles de batería, ni una evaluación de IA real. El coordinador de runtime mantiene la lógica productiva de reconstrucción íntegra de índices derivados si falla su refresco incremental y el índice de arranque exige consistencia física.

## Batería ampliada: cuatro índices y ONNX local — 27-10-2026 (fuente)

`benchmarks/indexing/probe_schema_backfill_batches.py` amplía la prueba con `--with-app-indexes`: añade **una Task real y un Event real** al vault, compone los tipos de las Apps de producción mediante `compose_application_schema`, inicializa/reconcilia **ContextIndex + SemanticEntityIndex general + semantic-tasks + semantic-events**, verifica identidad, hashes canónicos de **todas** las notas en cada índice, propiedades filtrables, número exacto de refrescos y el commit Git individual. `--offline-model-cache RUTA` sustituye el embedder simulado por `FastEmbedTextEmbedder(...,local_files_only=True)` en una caché existente: sin descarga, GPT, red ni notas personales. La regresión de cuatro índices está incluida en el gate transversal a través de `tests/runtime/test_schema_backfill_notes_vertical.py`.

**Mediciones sobre Raspberry Pi 4, sin tomar la creación del índice ni staging en el tiempo de escritura y consulta:**

| Notas físicas en la bóveda | Escrituras | Cuatro índices, embedder determinista | Un refresco derivado | Nota |
|---|---:|---:|---:|---|
| 1.000 (998 Person + Task + Event) | 12 | 2,81 s | 0,27 s | hashes de los cuatro índices OK |
| 5.000 (4.998 Person + Task + Event) | 8 | 9,53 s | 1,29 s | hashes de los cuatro índices OK |
| 10.000 (9.998 Person + Task + Event) | 5 | 13,80 s | 2,44 s | 7 commits totales contando 2 baseline; hashes de los cuatro índices OK |

**Prueba ONNX offline de la misma ruta:** con 80 notas totales, 3 escrituras + 4 índices: **0,49 s** (0,36 s índice), pico RSS **857 MiB**; con 250 notas, 8 escrituras + 4 índices: **1,51 s** (0,94 s índice), pico RSS **1.204 MiB**, MemAvailable después del lote 1.252 MiB, swap libre sin caída material. Modelo **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2** cargado desde la caché derivada **solo DEV**, `local_files_only=True`, sin llamadas externas. FastEmbed 0.7.3 emite un aviso de cambio histórico de pooling CLS→mean; los contratos de versión/modelo existentes y la migración de índices deben verificarse antes de asumir equivalencia con versiones anteriores. No se ha medido un lote neural de 10.000 notas ni el rendimiento energético de un teléfono.

**Límite real detectado (NO resuelto):** el escáner `accumulate_schema_scan` conserva como prueba de unicidad un conjunto acotado de **10.000 IDs físicos**, definido junto a `_MAX_IDS` en el diario de escaneo y `_LIMIT` en el backfill. Un primer intento con **10.002 fuentes** (10k Person + Task + Event) se rechazó antes de escribir: `SchemaRetrospectionError: Duplicate or inconsistent scan progress`. El caso de exactamente 10k físicas sí funcionó. El objetivo acordado incluye eventualmente decenas de miles de notas: hace falta un diseño de páginas/checkpoints que permita continuar volúmenes mayores conservando prueba de unicidad, protección de colisiones entre páginas y manifiesto físico final, sin ampliar sin más límites de RAM o de recibos. No presentar la capacidad de >10k como implementada.

## Capacidad separada: inventario físico y diario de escrituras (27-10, fuente posterior a c1d2770)

Antes se mezclaban tres presupuestos distintos: **10.000 identidades** del recibo persistente de escaneo `LocalSchemaScanJobs`, **10.000 filas candidatas** del diario HMAC de backfill, y el conjunto de IDs inspeccionados al preparar ese diario. Si una bóveda tenía 10.002 notas aunque solamente una necesitase una propiedad, `accumulate_schema_scan` paraba el staging. No corresponde multiplicar automáticamente la capacidad del diario y el coste de reescribir 10.000 filas tras **cada** avance.

**Cambios de código exclusivamente en staging de backfill:** `_staged_scan_inventory` obtiene una única instantánea física de versiones/rutas y su SHA-256 antes de recorrer las páginas; el helper interno `_scan_schema_sources_page` reutiliza esos datos para la preparación provisional, manteniendo relectura y verificación física de **cada** nota y prueba global final de `note_version_snapshot` antes de publicar el plan. La API pública `scan_schema_sources` sigue verificando en vivo cada página y NO acepta instantáneas proporcionadas por el caller. Un acumulador privado de esa transacción comprueba IDs únicos en **todas** las páginas, con presupuestos transitorios **máximo 50.000 archivos** y **12 MB en bytes de IDs**; el acumulador público y `LocalSchemaScanJobs` mantienen el máximo previo de **10.000 IDs** en sus checkpoints privados. Ningún índice SQLite es autoridad de identidad.

**La capacidad del diario de escrituras sigue en 10.000 candidatos / 8 MB de registro HMAC**, con el mismo actor, vault, versión de esquema, CAS, intent registrado antes de editar, Git individual y recuperación. Si más de 10.000 notas **necesitan** escritura, el plan actual se rechaza antes de publicarlo: no trunca ni salta notas. Segmentar múltiples planes autónomos de máximo 10k con manifiesto y deduplicación inter-plan sigue **pendiente**. El escáner read-only de progreso en la UI también sigue limitado a 10k fuentes; por tanto todavía NO se declara aceptación E2E del producto sobre 50k.

**Prueba reproducible en Raspberry Pi 4**, solo Git/Markdown sintéticos bajo /tmp: `python3 benchmarks/indexing/probe_schema_large_stage.py --notes 12000 --eligible 1200`. Resultado observado: 12.000 fuentes físicas, 1.200 candidatas, **3,97 s** para escanear y publicar el diario, **5,51 s** para un primer write real Core/E3/Git con inventario de 12k notas, 71,9 MiB pico RSS, y reabrir el diario después del commit correcto sin reescritura. Las 10.800 notas ya ocupadas quedaron intactas. Regresiones: un límite de identidad pública mucho menor no impide el staging privado completo, duplicado de ID entre páginas => rechazo, nueva nota durante staging => rechazo al final sin plan, >capacidad de filas de escritura => rechazo sin modificar Markdown, bytes de ID patológicos => rechazo, solo **dos** inventarios físicos inicial/final en el staging de varias páginas. No se han ejecutado 12k commits ni cuantificado SLA.

## Escáner público reanudable 10k–50k con pruebas canónicas (fuente posterior a 26ed811; 27-10)

**Implementado en fuente, NO desplegado:** `LocalSchemaScanJobs` conserva el formato JSON V1 y su validación original para bóvedas de hasta 10.000 notas y trabajos ya existentes. Cuando comienza un trabajo nuevo sobre una bóveda de **10.001 a 50.000 Markdown**, utiliza un checkpoint V2 **operativo** en SQLite privado por actor y vault, con permisos 0600, `journal_mode` de SQLite y commits de avance por página. No es una base de conocimiento nueva, no admite escrituras Markdown, no reemplaza Git ni autoriza Core/E3; solo conserva `(orden, ruta, versión física)`, IDs de unicidad de avance y contadores, sin fuentes de texto ni hechos originales. El cliente/Notes API conserva exactamente `scanning/complete`, los contadores y el tamaño de página máximo 25 (20 en Notes UI); no recibe IDs ni rutas. Los recibos compactos tienen `identity_proof=external` y **no pueden** alimentarse al acumulador público de IDs en memoria.

**Evitar O(N²) de inventario:** V2 captura un manifiesto físico verificado al empezar; cada avance carga únicamente sus 20–25 entradas, comprueba las versiones de esos archivos y valida su Markdown y hechos canónicos. La tabla `seen` UNIQUE detiene inmediatamente una identidad repetida entre páginas; el avance y los contadores se confirman juntos mediante una transacción SQLite. Una modificación externa puede quedar pendiente de detección **durante el progreso provisional**, pero **jamás se emite un recibo completo** sin recuperar un inventario físico nuevo, volver a validar **todos** los Markdown/IDs/hechos originales y comprobar los mismos conteos e identidades; se compara la instantánea física al principio y al final. En un restart se recupera la página guardada. La reutilización de un recibo ya completo obliga a repetir comprobación de Markdown y del esquema, no a confiar en un estado SQLite anterior. Un fallo deja el checkpoint parcial sin avanzar, y no hay escrituras durante este proceso.

**Cotas:** máximo 50.000 rutas físicas; 12 MB sumados de rutas y 12 MB de IDs escaneados, IDs individuales de 4.096 caracteres, tamaño del SQLite operativo 48 MB, directorio local aislado, archivo regular propietario del proceso con modo 0600 y sin symlink. Los presupuestos JSON V1 no cambian. Se comprueba la integridad del inventario completo en la creación y antes de declarar `complete`; si se ha tocado cualquier otra nota o cambió el esquema, la lectura completa rechaza el escaneo. El manifest es un índice de trabajo, no una prueba suficiente para crear una Note.

**Benchmark Raspberry Pi 4, con datos efímeros Git/Markdown bajo /tmp:** `python3 benchmarks/indexing/probe_schema_large_stage.py --notes 12000 --eligible 1200` y `--notes 20000 --eligible 1200`. V2 registró **12k notas, 480 páginas en 8,08 s, memoria pico 80,9 MiB**; con **20k notas, 800 páginas en 13,40 s, pico 100,3 MiB** (el pico incluye posterior staging y una escritura). Cada 61 páginas se reconstruye el servicio para comprobar reanudación. En los mismos ensayos, el staging de 1.200 candidatas tardó 3,96/6,88 s, y el primer commit Git+Core 5,52/9,23 s. Ningún timing incluye el coste inicial de generar las notas ni equivale a 20.000 escrituras. Los tests de V2 verifican interrupción/reanudación, duplicados entre páginas, cambios externos antes de completar, cambios de esquema incluso después de `complete`, manipulación de IDs SQLite, separación por actor, rechazo de symlinks, y compatibilidad de la API real Notes.

**Cierre parcial importante:** con esta versión, el escáner read-only de Notes **ya no** queda bloqueado por el antiguo máximo 10k, hasta un límite probado de 20k y una cota diseñada de 50k. Sigue limitado a **10.000 candidatos de escritura / 8 MB por diario**, y falta una campaña autónoma con múltiples journals de tamaño acotado sin duplicados ni pérdida de evidencia. Faltan igualmente worker Android/iOS durable, pruebas con 50k efectivos, 10k commits, cuatro auditores del nuevo SHA, DEV desplegado matching SHA, Access y evaluación GPT real autorizada. SQLite no se considera autoritativo ni constituye consentimiento para escritura masiva.

**Siguientes puertas reales:** 1) escáner read-only reanudable por encima de 10k sin checkpoints gigantes ni recorrido O(N²); 2) segmentación de planes de escritura con continuidad exacta por actor y sin pérdida de evidencia, manteniendo el diario HMAC acotado y resolución de cambios concurrentes; 3) auditores del SHA actual, E2E DEV del SHA coincidente, Access, interpretación GPT autorizada y pruebas móviles.

**Próximo trabajo:** auditoría independiente acotada de la agrupación/indexación y revisión de recuperación bajo concurrencia; aceptación real DEV del SHA coincidente y proveedor semántico autorizado. Diseñar el ejecutor local móvil realmente durable, con políticas de batería y reanudación independientes de Chromium; la extensión segura por encima de 10k es otro requisito previo a la autonomía masiva. No reemplazar Markdown por SQLite ni cambiar el contrato de una aprobación.




## Campañas de escritura segmentadas, firmadas y reanudables — fuente (27-10-2026)

**Necesidad:** el escáner read-only ya inspecciona hasta 50k identidades, pero el diario E3/Git V1 se rechaza correctamente con más de 10.000 *candidatos a escribir*. No debemos ampliar sin límites el registro HMAC de 8 MB, perder el aislamiento del actor ni volver a examinar los diferidos desde el principio cuando se crea el diario siguiente.

**Implementación fuente:** `LocalBackfillCampaign` es un **coordinador local de los diarios existentes**, no un nuevo escritor ni permiso. Su registro padre HMAC reutiliza el secreto de integridad local, se vincula a actor/vault, SHA de esquema, ID de campaña, tipo/propiedad aprobados y cursor físico estable `after_path`. Genera ID de diario hijo determinista por índice y scope. Cada diario hijo conserva la secuencia original de Core/E3: fuente Markdown, CAS, intención fsynced, commit Git individual, readback, undo, estado de escritura ambiguo/reconciliación. El tamaño por segmento en código producto es **1.000 candidatos** (configuración interna acotada de 1 a 10.000; ninguna petición web puede elegir cursor/tamaño); la capacidad física global sigue en 50.000. La selección recorre **todos** los IDs de la bóveda para probar unicidad inter-páginas, no solo los 1.000 seleccionados. Calcula una huella ordenada de rutas e identidades (no datos SQLite) que se comprueba de nuevo antes de preparar cada tramo. Cambios de ruta/identidad o nueva Note provocan rechazo, no salto silencioso de notas.

**Continuidad:** primero se prepara un diario de máximo 1.000 notas, sin escribir. Cada llamada explícita `advance` aplica como máximo **una** escritura; si el hijo está terminado, el padre contabiliza sus resultados una única vez y avanza el cursor antes de crear el siguiente. Un reinicio tras un commit E3/Git sigue utilizando la reconciliación exacta del hijo, sin reescritura. Un reinicio entre publicar el diario hijo y persistir el nuevo cursor recupera el hijo por ID determinista. Si el hijo falta o su HMAC no coincide se rechaza. Las notas `deferred` se contabilizan, permanecen sin modificar y **no se vuelven a seleccionar** en diarios posteriores. Tras recorrer toda la bóveda, el resultado es `awaiting_ai` cuando quedan diferidas; NO se declara que todas las propiedades se hayan enriquecido. Una futura fase semántica podrá revisarlas con autorización del proveedor y su propia recuperación, pero **aún no está conectada** a este recorrido.

**Entrada de producto:** la API `schema_backfill` conserva exactamente `stage/status/advance`; en cada llamada vuelve a exigir aprobación confirmada del **mismo actor, revisión y propiedad**. Si existe un diario V1 anterior se respeta. Para un trabajo nuevo con más de 10.000 archivos físicos usa automáticamente el coordinador; con menos conserva V1. Se devuelven contadores y progreso de campaña; el total crece al preparar diarios posteriores y no debe confundirse con total final antes de completar el escaneo. No se introduce autonomía silenciosa en arranque, ni llamadas externas, ni despliegue.

**Batería de pruebas de la rama:** `tests/runtime/test_schema_backfill_campaign.py` y el contrato Notes API real, incluidos 6 fuentes repartidas en 3 diarios de tamaño 2 con 6 commits individuales, notas ambiguas diferidas sin bucle, caída después del commit y reconciliación sin duplicado, caída entre diario hijo y registro padre, faltante/tamper HMAC de diario padre o hijo, otro actor, otro esquema, cambio en el corpus y colisión de identidad entre segmentos, y compatibilidad con el diario V1 empezado. El gate transversal incluye explícitamente la nueva batería. Prueba de escala real con **11.000 candidatas** en Git sintético y **3 escrituras** atravesando **dos diarios de tamaño 2**: `python3 benchmarks/indexing/probe_schema_campaign_large.py --notes 11000 --writes 3 --segment-size 2`. Se midieron 3,73 s de primer staging, 11,17 s para los 3 `advance`, RSS máximo 68,5 MiB; 4 commits (baseline +3), reanudación correcta y diferencia Git↔Markdown limitada a las 3 notas esperadas. No se han escrito 11.000 notas: es una prueba de frontera y recuperación, **no** de resistencia, SLA ni autonomía continua en Android.

**Límites presentes:** cada E3/Git sigue ejecutándose individualmente y su autorización canónica verifica las identidades físicas completas; aún hay coste O(N) por nota a grandes escalas. La huella entre segmentos cubre rutas e IDs, pero no convierte una campaña multidiario en una transacción global frente a ediciones concurrentes de contenido; los source hashes/CAS se aplican por nota. Los valores diferidos no se reintentan automáticamente en esta fase determinista. No hay worker duradero nativo, ni prueba sobre PROD, GPT real, Cloudflare Access externo ni aceptación DEV del nuevo SHA. Para merge faltan revisión independiente de cuatro roles y cierre de puertas de integración autorizadas.

## No implementado / siguiente puerta

- El contrato y la pantalla están desplegados en DEV con autocompletado de escritura desactivado tras la prueba; sigue faltando un scheduler/background real para Android/iOS. PROD no lo ejecuta.
- No hay campaña nueva de modelo real: los 18 casos ES/FR/EN del intérprete están congelados pero no evaluados en proveedor. No habilitar escritura semántica antes de comprobar falsos positivos, abstenciones y coste autorizado.
- El mecanismo actual guarda un commit por nota; para corpus enormes necesita optimización sin perder la recuperación. El plan de un máximo de 10.000 candidatas no sustituye los ensayos de rendimiento en hardware móvil.
- Pendientes identidad/deduplicación de entidades nuevas, UX de excepciones y deshacer, sesión externa Cloudflare Access y auditoría Codex de cuatro roles sobre commit aprobado.

Véanse la arquitectura de almacenamiento y el contrato de interpretación semántica V1.


## Auditoría independiente del encadenamiento y correcciones — 27-10-2026 (solo fuente)

**Auditoría acotada en SHA d9ddc053 (delta desde 033c323, NO el PR completo):** ejecutado supervisor formal de 4 roles bajo un techo de 300.000 tokens reportados. Generalidad **FAIL** por nota originalmente no candidata que se vuelve elegible detrás de cursor; Calidad **FAIL** porque Notes client V1 rechazaba los campos segment/finished y el panel terminaba al completar un hijo; Pruebas **BLOCKED** por esos dos defectos y porque sigue pendiente E2E autenticado sobre SHA nuevo y GPT real; Rendimiento **NO EJECUTADO**: los primeros tres roles consumieron 262.512 tokens reportados y quedaban 37.488, por debajo de la reserva obligatoria de 50.000. El supervisor detuvo la ronda sin intentar el cuarto ni levantar arbitrariamente el límite. Recibos en el supervisor del job `schema-campaign-audit-20261027`.

**Corrección posterior al SHA auditado (requiere NUEVA revisión independiente):**
- El registro padre HMAC mantiene un mapa compacto de bits de **elegibilidad inicial**, indexado por la lista física completa de paths+IDs cuya huella SHA sigue fijada. Antes de cada diario siguiente se vuelve a leer/validar todo Markdown; si una nota no candidata tras el cursor pasa a ser candidata, o una nota aún no procesada cambia de elegibilidad en cualquier dirección, la campaña se bloquea en lugar de saltar o inventar candidatos. Los cambios de elegibilidad causados por los commits autorizados en el tramo ya cerrado son admisibles; no lo son nuevos candidatos detrás del cursor. El bitset no autoriza escrituras, que siguen en E3/CS, Git individual, CAS y readback.
- El contrato estricto `odyssey_web/notes-client.js` distingue recibos V1 exactos (<=10k candidatos) y campañas exactas con `segment` entero, `finished` booleano y total <=50k. Sigue rechazando campos de autoridad/IDs/undo y falsos estados terminales. El panel de `schema-scan.js` continúa mientras la campaña siga sin terminar, aunque un diario hijo haya acabado o tenga filas diferidas. El padre devuelve `in_progress` hasta que termina el último diario y entonces `complete` o `awaiting_ai` si quedan notas para interpretación.
- Nuevas pruebas adversariales: nota originalmente ocupada y luego vaciada detrás del cursor; candidato futuro convertido en ocupado; ruta no numérica y cambio `document→person` detrás del cursor; intermedio con diferidos; prueba Node del validador y flujo UI a través de dos diarios y transporte Notes HTTP con 11.000 candidatos. Solo datos Git/Markdown sintéticos.

**Alcance de la evidencia:** el gate local anterior no basta para aprobar la corrección; los cuatro dictámenes del SHA auditado no son cuatro PASS ni certifican los cambios posteriores. Una prueba real desplegada en DEV matching-SHA, Cloudflare Access y el proveedor semántico autorizado siguen pendientes. Ningún cambio de despliegue, PROD o vault personal.


## Segunda auditoría formal y reparación adicional — 27-10-2026, solo fuente

**Auditoría independiente anclada a `bf130ac` (delta desde `033c323`):** cuatro roles efectivamente ejecutados en la misma instantánea por `schema-campaign-repair4role-20261027`; Generalidad **FAIL**: una caída entre publicar el primer hijo y persistir la prueba del padre podía adoptar un inventario modificado; Calidad **FAIL**: un FIFO en el checkpoint padre podía bloquear `open(O_RDONLY)` antes de hacer `fstat`; Pruebas **BLOCKED** exclusivamente por falta del E2E real autenticado DEV sobre ese SHA; Rendimiento **PASS** para ese *delta* sin regresión de rendimiento bloqueante, con límite explícito de que 11.000 candidatas/3 escrituras no es una prueba de 11.000 commits. Total modelo reportado: 305.455 tokens en cuatro sesiones. No hay cuatro PASS y no es aprobación del PR completo. Los auditores fueron read-only, sin mutaciones/deploy.

**Correcciones posteriores que invalidan ese SHA para aceptación final:**
- Cuando se recupera un diario hijo ya publicado, la prueba completa del inventario físico actual **debe coincidir** con la prueba registrada y firmada en el hijo. No se puede reemplazar silenciosamente la prueba inicial de identidad/candidatos durante la ventana de caída previa a la persistencia del padre. Regresión con nueva nota `00.md` creada y confirmada en Git tras la publicación del primer hijo y antes de la recuperación: rechaza.
- El checkpoint HMAC padre se abre únicamente después de un `lstat` regular; `O_NOFOLLOW | O_NONBLOCK` más `fstat` previenen bloqueo por FIFO incluso ante carrera de sustitución. Regresión sintética con FIFO y alarma de dos segundos: rechaza sin colgar.
- **Hallazgo adicional reproducido manualmente:** una propiedad `profesion` escrita por E3 en un hijo anterior se elimina externamente antes del siguiente hijo; aunque fuese candidata al empezar, quedaba otra vez elegible detrás del cursor y se omitía. Solución: reutilizar los **diarios hijo HMAC anteriores** como evidencia de las rutas `updated/already_present` y, al inspeccionar los Markdown físicos del siguiente tramo, detenerse si alguna vuelve a ser elegible. No se introduce otra autoridad o un nuevo índice persistente; diferidas siguen sin reintentarse. Si falta o cambia la prueba de un hijo ya terminado, el trabajo rechaza.
- Medición de regresión aislada: `benchmarks/indexing/probe_schema_campaign_large.py --notes 11000 --writes 3 --segment-size 2`: 11k elegibles, primer diario **3,70 s**, tres escrituras a través de dos diarios **11,09 s**, 68,6 MiB RSS, Git baseline +3 commits, reinicio correcto. Datos puramente sintéticos, ninguna escritura personal. Estas métricas son de una sola ejecución y no prueban estrés prolongado.

**Pendiente de cierre:** gate completo y auditoría independiente de cualquier commit posterior a estas reparaciones, nuevo SHA desplegado en DEV y aceptación desde Chromium autenticado + Cloudflare Access + GPT real según autorizaciones, rendimiento sostenido de muchos commits/índices y worker móvil durable. Ninguna de estas reparaciones implica fusión, despliegue o autorización de un modelo de pago.


## Tercera auditoría del encadenamiento y prueba posicional completa — 27-10-2026, fuente

El supervisor `schema-campaign-closure4role-20261027` verificó los cuatro roles independientes contra el mismo `544f742`, delta `033c323..544f742` (no el PR completo). **Generalidad FAIL:** la huella agrupaba rutas y IDs activos por separado; como el scanner excluye notas deleted de `source_note_ids`, un intercambio entre dos notas de tipo no objetivo de cuál está activa podía conservar ambas listas sin conservar el vínculo ruta↔ID↔deleted. **Calidad FAIL:** el registro padre HMAC podía devolver `complete` aun después de perder un diario hijo finalizado o el diario vacío que acredita el final. **Pruebas BLOCKED:** falta aceptación autenticada del SHA desplegado con UI→n8n→Core/E3→Git→Markdown→query y GPT real. **Rendimiento PASS** en el alcance de código revisado; 11k candidatos/3 escrituras no prueban 11k commits, p95 sostenido ni móvil. Resultado: NO cuatro PASS; ninguna revisión autoriza merge o deploy.

**Reparación de Generalidad:** el cálculo de huella privada registra tuplas `(ruta física, ID canónico, deleted)` **en el orden de cada nota del vault**. El mismo scanner `_scan_schema_sources_page` produce un testigo efímero `_identity_witness` mientras analiza y valida Markdown físico; el testigo no se serializa en los recibos públicos, no depende del índice SQLite y no genera una segunda lectura completa. Se verifica que sus rutas sean exactamente las de la página antes de incorporar las tuplas a SHA. Regresión reproducible: dos documentos no objetivo con nombres de archivo estables intercambian sus IDs y estados live/deleted; `source_note_ids` y recuentos convencionales no cambian, pero el siguiente diario **rechaza** por identidad distinta.

**Reparación de Calidad:** `status` y `advance` de una campaña con `finished=true` deben verificar HMAC de cada diario ya completado y del diario terminal vacío; si cualquiera falta o se altera, no afirman `complete` ni `awaiting_ai`. Regresión elimina un hijo de escritura o el hijo de prueba terminal después de que el padre se cierre y comprueba rechazo inmediato. Esto verifica evidencia histórica del job; no afirma que todos los valores aún sigan presentes después de posteriores ediciones manuales.

**Coste y verificación:** primera implementación segura con una segunda lectura Markdown tardó 6,02 s para staging de 11k notas y 13,46 s para tres escrituras; con el testigo de escaneo privado los mismos ensayos sintéticos tardaron **3,79 s** y **11,19 s**, RSS máximo **69,4 MiB**. Tres Git commits + baseline y reanudación correcta. Son ejecuciones aisladas, no percentiles. La suite focalizada de cuatro superficies Python del scanner/backfill alcanzó 85 PASS, antes del gate transversal final. Falta gate global y revalidación de CI/Chromium del SHA resultante, además de la revisión independiente posterior a estas dos correcciones y las puertas de DEV/GPT/Access.


## Aceptación aislada del límite auténtico y de la UI multidiario — 27-10-2026 (NO DEV)

**Dos evidencias complementarias, no equivalentes a aceptación DEV:**

1. **API Notes con umbral auténtico:** `python3 benchmarks/indexing/probe_schema_campaign_notes_api_boundary.py --notes 10001` crea en `/tmp` exactamente 10.001 Markdown canónicos y un Git desechable, y usa `RuntimeComposition.notes("schema_backfill")`, con la propiedad `profesion` ya confirmada por ALICE. El umbral del producto **no se modifica**; solo se fuerza el tamaño *privado* de los diarios a 2 para comprobar la transición con tres peticiones `advance` sin miles de commits. Stage 3,53 s; tres advances 8,77 s; 2 actualizadas, 1 diferida, 1 pendiente del siguiente diario; 4 commits (2 baseline + 2 Core/E3), rechazo del actor BOB, reapertura de nuevo worker, HMAC padre y Git diff↔Markdown exactos, RSS pico 65,5 MiB. No es una prueba del navegador ni 10.001 escrituras.
2. **Chromium desktop/mobile real con n8n Docker offline + Core/E3/Git:** `scripts/odyssey_schema_chromium_n8n_isolated.py --run --campaign` ejecuta el cliente web auténtico en Chromium contra un servidor de recursos locales; peticiones Notes pasan por webhook n8n Docker `--network none` y Core del host, trabajando exclusivamente en Git/Markdown sintéticos temporales. La UI muestra **4 actualizadas, 1 diferida, campaña terminada**, cruza al menos dos diarios y tras `reload` conserva el resultado sin duplicación: 6 commits (2 baseline, 4 E3), 13 peticiones Core por viewport. Para mantener la prueba visual rápida se usan 5 notas físicas, el límite de selección del *backfill* se reduce exclusivamente en el proxy Python aislado a 3, y el tamaño del diario a 2. El escáner read-only sigue en su límite normal y valida Markdown real. No es una prueba del umbral 10k, que está cubierta por el primer ensayo. La prueba visual además distingue `4 actualizadas` de `finished=true`: espera la frase terminal del padre antes de verificar el cierre.

**Prueba adicional de escala real (solo fixture):** `python3 benchmarks/indexing/probe_schema_campaign_large.py --notes 30000 --writes 3 --segment-size 2` PASS con 30.000 Markdown elegibles, primer staging **11,31 s**, tres escrituras atravesando dos diarios **42,10 s**, RSS máximo **74,4 MiB**, 4 commits incluido el inicial y recuperación Git/readback sin duplicación. Es una única ejecución, no 30.000 escrituras ni SLA. Intento con `--notes 50000`: Git falla **antes de preparar la campaña** con `fatal: unable to write loose object file: No space left on device` porque el fixture Git de 50.000 archivos rebasa la capacidad de `/tmp` (tmpfs de 2 GiB) en esta Raspberry. No se ejecutó staging ni E3 a 50k; es una puerta de infraestructura de pruebas, no evidencia de que funcione o falle Odyssey a 50k. El benchmark ahora emite el stderr de Git capturado para distinguir este bloqueo de defectos de Core.

**Negativos y limitaciones:** se valida el actor a través del adaptador de prueba con `AuthenticatedActorContext`; no hay Cloudflare Access externo, ni navegador contra DEV desplegado matching SHA, ni GPT pagado, ni miles de escrituras prolongadas, ni trabajador nativo Android. DEV/PROD no se tocan. Ambos escenarios son opt-in reproducibles con datos desechables; el escenario original de un solo diario se mantiene por defecto en el runner y se revalida aparte.


## Revisión focalizada y defensa contra replay de diarios HMAC — 27-10-2026

**Decisión de alcance:** detener el aumento de bibliotecas sintéticas después de la prueba de 30.000 notas. El límite de 50.000 es un límite de seguridad/diseño del escáner, NO un objetivo de expansión de pruebas. Priorizar ahora el recorrido de producto autorizado en DEV y la experiencia móvil local; la prueba de resistencia con muchos commits/batería es una fase específica posterior y no justifica más escaladas de fixtures.

**Revisión independiente única, read-only, acotada a `544f742..c007f86`:** Codex gpt-6-sol/medium encontró un **P1 real**: la verificación de HMAC de todos los hijos al finalizar no era suficiente si alguien restituía un diario legítimamente firmado de una ejecución anterior con el mismo ID determinista, actor, esquema y propiedad. El padre podía devolver `complete` con totales de una encarnación nueva y resultados de un diario viejo. Sin otras observaciones accionables en la huella posicional privada. Esta revisión NO es otra ronda de cuatro roles ni aceptación DEV.

**Corrección en fuente, pendiente de aceptación final:** el padre HMAC ahora guarda una cadena SHA-256 de los HMAC exactos de **cada hijo terminado y en orden**, más el HMAC del diario terminal vacío. Al contabilizar un hijo se incorpora a la cadena antes de persistir el padre; al reabrir, se releen todos los hijos autenticados y se comparan el orden de rutas, la frontera final, cada contador `updated/deferred/...`, y la cadena contra el padre firmado. Ni una falsificación sin clave ni un **replay de un hijo auténtico antiguo** puede certificar `complete` por sí solo. No se mantiene un segundo índice de autoridad ni una lista creciente de hashes; el tamaño de la cadena en el padre es constante.

**Pruebas adversariales:** dos encarnaciones de la misma campaña con HMAC/key/actor/vault/ID reales y fuentes canónicas distintas; se reemplaza un hijo firmado antiguo y, por separado, el diario terminal antiguo. En ambos casos el HMAC del hijo individual sigue siendo VÁLIDO, pero `status` y `advance` rechazan por incompatibilidad con el padre. Escenario sin candidatos también emite y exige prueba terminal válida. Batería focalizada 82 Python PASS más regresión de campaña vacía; el fixture de 11k elegibles/3 escrituras continúa pasando: stage 3,71 s, tres avances 11,12 s, RSS 68,7 MiB. Medición aislada, NO 11k escrituras. Falta todavía gate transversal/código SHA fijado y aceptación desplegada DEV+Access+GPT.


## Corrección de replay de diario activo — 27-10-2026, rama fuente

La auditoría independiente incremental sobre `250ae42` detectó que un diario hijo
**activo**, aunque HMAC-válido, podía ser sustituido por una versión de otra
encarnación de campaña con el mismo ID determinista. Calidad devolvió FAIL;
Pruebas confirmó la omisión y quedó BLOCKED por la aceptación externa todavía
pendiente. Generalidad PASS; Rendimiento NO EJECUTADO por la reserva de 50k
frente al saldo de 40.584 tokens del ciclo. Estos dictámenes son históricos
y NO autorizan el nuevo código.

**Corrección en fuente (sin desplegar):** el checkpoint padre V2 HMAC registra
una generación criptográficamente aleatoria persistida **antes** de publicar
el primer hijo; todos los IDs de diarios hijos derivan de esa generación.
Además registra el SHA-256 de un manifiesto de selección inmutable
(alcance, esquema, ID hijo, inventario y tuplas ordenadas de ruta/ID/hash/
revisión de fuente). `status` y `advance` lo revalidan contra el diario HMAC
activo antes de sumar resultados o autorizar una nueva escritura; las
transiciones de segmento limpian el vínculo anterior. Esto no elimina el
CAS/E3/Git ni el journal por nota.

**Compatibilidad/recuperación:** los padres V1 terminados conservan lectura
y validación de sus diarios originales. Un padre V1 **activo**, sin vínculo
generacional seguro, no se acepta automáticamente: debe replanificarse
de forma supervisada después de verificar las escrituras físicas. Nunca se
reinterpreta en silencio ni se borra un diario de usuario. La protección
corrige el replay entre encarnaciones; no pretende que un HMAC local
impida a un atacante con control total de la clave y todos los checkpoints
restaurar simultáneamente el estado completo a un snapshot anterior.

**Pruebas sintéticas verificadas:** replay de hijo activo válido de generación previa,
manifiesto alterado y re-firmado, parent V1 completado legible, parent V1
activo rechazado, recuperación entre segmentos y Git, más cobertura
existente. Gate integral local: **2.329 Python + 7 subtests y 255 JavaScript PASS**, Ruff/formato/documentación PASS. Chromium auténtico escritorio y móvil → n8n offline real → Core/E3/Git sobre vault desechable **PASS**: 4 escrituras, 1 diferida, múltiples diarios, recarga y sin duplicados (proveedor OFF, NO DEV). El hito requiere auditoría fresca sobre nuevo SHA,
GPT real/acceso externo autorizados cuando proceda y aceptación E2E
matching-SHA para cierre de producto. PROD sin autorización de despliegue.
