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
