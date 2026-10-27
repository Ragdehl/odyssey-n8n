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

**Próximo cuello de botella:** evaluación del coste global de comprobar inventario y actualizar índices por nota; estudiar agrupación *solo de los refrescos derivados*, sin agrupar a ciegas commits Git ni debilitar CAS o reanudación, y medir en teléfono real antes de aceptar autonomía masiva.

## No implementado / siguiente puerta

- El contrato y la pantalla están desplegados en DEV con autocompletado de escritura desactivado tras la prueba; sigue faltando un scheduler/background real para Android/iOS. PROD no lo ejecuta.
- No hay campaña nueva de modelo real: los 18 casos ES/FR/EN del intérprete están congelados pero no evaluados en proveedor. No habilitar escritura semántica antes de comprobar falsos positivos, abstenciones y coste autorizado.
- El mecanismo actual guarda un commit por nota; para corpus enormes necesita optimización sin perder la recuperación. El plan de un máximo de 10.000 candidatas no sustituye los ensayos de rendimiento en hardware móvil.
- Pendientes identidad/deduplicación de entidades nuevas, UX de excepciones y deshacer, sesión externa Cloudflare Access y auditoría Codex de cuatro roles sobre commit aprobado.

Véanse la arquitectura de almacenamiento y el contrato de interpretación semántica V1.
