# P4 — diagnóstico privado de vetos anteriores a Core (18-10-2026)

## Propósito
Después de 10 E2E (6 completadas, 4 needs_attention), varias frases N:M/identidades conocidas rechazan antes del Core preflight. No es posible deducir la causa exacta de un needs_attention genérico ni justificar desactivar los revisores. Añadir un diagnóstico técnico **solo DEV**, fail-closed, de qué gate concede/veta, sin persistir fuente, nombres, notas, citas, prompts, salida GPT ni actor.

## Implementación preparada
- Campo opcional WholeSourceLightExecutor.prewrite_diagnostic, inyectado únicamente en composición con ODYSSEY_DEPLOYMENT_ENV=DEV. Cada evento conoce solo request_digest sha256 truncado, categoría fija y contadores/flags explícitos (cantidad de hechos/entidades, unresolved, approved, complete, reviewed_facts, overlap, intento 0/1). Se emite proposal, coverage_verdict, coverage_rejected o retry_exhausted, coverage_contract/identity_collision/speaker_contract, prewrite_accepted, compile_rejected. Ningún mensaje/error textual se registra.
- Fichero de runtime DEV p4-prewrite-gates.jsonl, permisos 0600, máximo ~256KiB con truncación, O_NOFOLLOW y errores de logging ignorados. Nunca en PROD, nunca en ruta /data/odyssey; aislamiento identidades por raíz actual.
- Garantías: mismo review, validate_whole_message_coverage, reject_unproven_person_collisions, validate_dual_speaker_review, compile_reviewed_operations, Core y Writer sin bypass; el observador jamás altera un veto. Al comenzar la segunda propuesta tras un rechazo de coverage, reiniciar concurrent_speakers: nunca reutilizar dictámenes hechos sobre la primera propuesta.
- Focal: privacidad/flags, fail-closed para rechazo de coverage, fallo speaker sin escritura, acceso PROD apagado, rotación. 34 Python test focal PASS. Gate transversal pendiente cuando se redacta el primer estado.

## Próxima acción y criterio
Deploy solo DEV después del gate; reproducir frases que fueron needs_attention con IDs sintéticos únicos; agrupar stage/flags, y atribuir fuente de rechazo *sin* bajar umbrales ni inventar identidades. Cambios posteriores solo si reproducidos con casos adversariales (pronombres, fechas, sujetos implicitos, negación, N:M) y pruebas reales E2E. PROD intacto.
## Seis E2E reales con diagnóstico privado (18-10-2026)

DEV desplegado 821c8fa; PROD intacto. El registro /data/odyssey-dev/runtime/p4-prewrite-gates.jsonl tiene permisos 0600, solo categorías fijas, números y digest de petición, sin fuente, actor ni notas.

Resultados por Chat -> n8n -> GPT -> Core (tiempos runtime): N:M de cuatro personas COMPLETED 16,60s (4 entidades, 1 fact, coverage aprobada y prewrite aceptado); persona conocida needs_attention 24,17s (coverage aprobada, speaker_contract rechazado antes de escribir); nueva persona con pronombre COMPLETED 25,13s (coverage y prewrite aceptados); negación seguida de afirmación needs_attention 15,60s (coverage aprobada, coverage_contract posterior rechazó); dos obligaciones de Task needs_attention 17,08s (ruta Tasks-only, ningún gate Core); otro N:M con nombre parcial needs_attention 16,50s (coverage aprobada, identity_collision). Estos 4 rechazos no son éxitos ni pueden agruparse como un único bug.

El parcial Reme frente al nombre previamente registrado Reme Busquets es una colisión protectora: enlazar por prefijo sería inventar una identidad. Tasks-only valida por diseño exactly_one_operation y por eso debemos soportar conjuntos verificados de Tasks sin descartar subtareas, relaciones o lifecycle. La frase negada no debe registrarse como evento realizado, aunque hay una segunda afirmación que convendría conservar mediante representación epistemológica explícita y validación de fuente completa.

Segunda instrumentación preparada en rama: códigos numéricos solo para motivos de excepción estáticos de cobertura (10-15), speaker (21-25) y colisión de identidad (31-32), jamás copiar mensajes de excepciones con nombres. Incluye task_scope_verdict/task_scope_rejected con flags task_only, one_operation, source_aligned. No elimina ningún veto. Tests focales 36 PASS; gate global pendiente al redactar esta línea. Tras desplegarla, repetir rechazos concretos para distinguir desacuerdo de hablante vs ordinal o quote, y confirmar la ruta de dos Tasks. Corregir solo a partir de evidencia y regresiones adversariales.
