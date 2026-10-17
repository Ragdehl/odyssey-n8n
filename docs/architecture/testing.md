# Testing Strategy

Odyssey separates deterministic correctness from live model evidence. A change is ready only when the checks appropriate to its behavior have passed.

## Deterministic testing

Use the narrowest useful test during iteration, then the complete deterministic gate before readiness.

Python tests live under `tests/`; pytest is the official runner. Existing unittest tests may remain and are discovered by pytest.

Typical focused iteration:

```bash
pytest tests/core/test_notes.py -q --tb=short
```

Complete Python suite:

```bash
pytest
```

Python lint/format authority:

```bash
ruff check odyssey_core scripts tests
ruff format --check odyssey_core scripts tests
```

Canonical schema validation:

```bash
python3 scripts/validate_note_schema.py
```

The repository pre-commit configuration groups the complete local deterministic checks; `pre-commit run --all-files` is the normal final local gate when working through Codex.

## Shared cross-surface mutation regressions (P4 onward)

For a substantial Router/E2/Core/E3/Tasks/Work Sessions/UI refactor, run the same offline command used in GitHub CI:

```bash
python scripts/odyssey_cross_surface_gate.py --output /tmp/odyssey-cross-surface.json
```

This gate is [defined and versioned here](cross-surface-regression-gate.md). It runs 9 groups of deterministic/isolated service/HTTP tests plus all Node web/workflow contracts, explicitly withholding OpenAI credentials. Missing tests or any failed case **block** the branch. Add a test group for each new App capability and fresh regression examples for any newly observed real-chat failure; do not duplicate domain mechanics in an App test. A green gate proves shared mechanics, **not** fresh model correctness or real browser/n8n integration. These remain separate manual approval gates and must not be inferred from the CI job.

## Browser/workflow checks

The minimal `odyssey_web/` client has deterministic JavaScript tests in addition to Python static/contract coverage. GitHub CI runs the checked-in web JavaScript gate together with the Python/schema checks.

Versioned n8n Workflow SDK source under `workflows/` is validated through its repository tests/checks. Live n8n execution is required only when behavior depends on the actual n8n/runtime environment rather than static workflow structure.

## CI and review

GitHub CI independently validates pull requests and `main`. The stable deterministic check name is `Python CI / Python deterministic checks`; SonarQube Cloud adds code-quality/security analysis. Whether branch protection currently requires that check is a GitHub repository setting and should be verified before relying on it.

```text
implementation
     |
focused tests / local iteration
     |
complete deterministic gate
     |
odyssey-verify-change
     |
push / Draft PR
     |
GitHub CI + Sonar
     |
semantic review
     |
human merge
```

Do not duplicate identical expensive local checks immediately when an unchanged tree already has fresh successful evidence; rerun the affected gate after any relevant change.

## Contract testing principles

For deterministic primitives and reusable boundaries, cover the applicable cases:

- normal success;
- not found / empty result;
- malformed or invalid input;
- ambiguity/conflict/fail-closed behavior;
- retry/idempotency behavior when applicable;
- revision/stale-state behavior for writes;
- returned contract **and** resulting canonical/durable state;
- no unintended mutation on failure.

For planner retrieval changes, keep the provider schema and local validator in parity across
`single`, `collection`, and note-set presentation. In particular, test cross-field states that Core
rejects, and test that several grounded collection members or matching Notes remain results rather
than clarification. A deterministic pass proves the contract shape, not that a live model follows
the changed instructions; focused production-model evidence remains a separate gate.

Clarification continuation tests must keep result cardinality separate from identity ambiguity:
an explicit Note set or grounded collection may contain many results, while one unresolved source
or write target needs a bounded choice. Test numeric/exact-label precedence, cancel, new-request
supersession, unresolved retention, actor/conversation isolation, durable replay, and a current
canonical Markdown/re-resolution guard before any resumed write. Do not add a wall-clock expiry to
v1; a stored choice is not mutation authority. Tests must use injected classifiers, never provider
credentials or live model calls.

Use isolated temporary/disposable fixtures. Tests must not modify real personal notes or require production credentials.

## Model-facing evaluations

Changes to production model prompts, model-facing instructions, or structured-output contracts require more than deterministic schema tests.

Use a versioned/frozen multi-case evaluation set and compare the exact production model/reasoning configuration. Include ordinary cases, difficult historical failures, ambiguity, malformed/invalid outputs, and regression sentinels for behavior that could be disturbed.

A production-model change is not validated merely because:

- one example worked;
- a different model followed the prompt;
- deterministic JSON validation passed;
- a synthetic oracle demands wording that the real contract does not require.

When provider access is unavailable, record the live-evidence gate as pending. Do not silently lower the standard or substitute unequivalent evidence.

Live calls should remain focused and cost-aware. Reuse existing benchmark evidence and frozen cases rather than rerunning broad model selection without a concrete reason.

**Raspberry live API procedure, already established (do not forget):** a normal Remote Desktop shell deliberately has no `OPENAI_API_KEY`. This is **not** proof of missing credentials/provider failure. Before classifying the API inaccessible, read `AGENTS.md` (model execution/security section) and verify the fixed user `systemd` manager/bus and protected existing `EnvironmentFile` metadata **without reading its contents**. The authorized one-shot provider gate runs via `systemd --user` transient unit using `EnvironmentFile=`, `--wait --collect --pipe`, explicit bounded opt-in, and a disposable test vault. Never source the key in the remote shell, invent an alternate credential path, or display its contents. If the unit/tool itself is blocked, report a **blocked provider run**, preserve exact evidence already obtained and continue provider-free checks without attempting alternate evasions.

## Integration and E2E evidence

Integration tests cover composition across real boundaries when needed, including:

- n8n -> internal runtime -> Core;
- request/result contract and stable `request_id` retry behavior;
- canonical Markdown mutation plus pending/Git/index outcomes;
- browser -> n8n Odyssey Online response;
- Raspberry/Cloudflare access boundaries when deployment work reaches them.

Initial live integration uses disposable data. Real vault activation, security changes, credentials, and destructive cleanup remain explicit human-controlled actions.

## Completion evidence

A PR is not ready while an applicable deterministic, live-model, environment, or semantic-review gate is unresolved. Branches/PRs/tests preserve development evidence; current functional status belongs in the [Functional Roadmap](functional-roadmap.md).

### P4 — dos capas de regresión obligatorias (octubre 2026)

1. **Determinista, offline, para cada cambio estructural:** `python scripts/odyssey_acceptance_contracts.py` + `python scripts/odyssey_cross_surface_gate.py --output /tmp/odyssey-cross-surface.json`, luego Ruff y suite global. El gate no necesita credenciales, incluye casos Core/Tasks/UI, reintentos E3, HTTP localhost, propiedad de rutas en n8n JS y casos adversariales; **no** autoriza DEV ni PROD.
2. **Gates GPT nuevos y aislados tras cambios de Router/planning:** `scripts/p4_live_router_diversity_matrix.py` (22 entradas ES/FR/EN, cardinalidad de apps por operación), `scripts/p4_task_scope_auditor_live.py` (6 entradas de operación única vs múltiples), `scripts/p4_dependent_real_provider_gate.py` (modelos reales para Router/split/TaskInterpreter/revisores, Core plan congelado, Markdown/E3 real), `scripts/p4_product_live_isolated.py` (Planner/Writer reales, HTTP local, fake SELF y Notes temporales, incluido backlink canónico SELF). Los scripts **son opt-in**, deben ejecutarse bajo el procedimiento de `AGENTS.md` con servicio temporal `systemd --user`, `EnvironmentFile` protegido y autorización explícita. No leer ni imprimir la clave. Evidencia y límites por caso en `docs/architecture/p4-router-tasks-generality-live-20261017.md`.

Los scripts de modelos no forman parte de CI; jamás reemplazan la validación auténtica de navegador→n8n→Core/Tasks→Markdown→navegador. Un resultado «capacidades correctas» no es suficiente: exigir cardinalidad de operaciones, continuidad exacta de fuente, evidencia física y replay/noop/estado correcto cuando aplique. Conservar cada fallo genuino como test offline adversarial además de su recibo en vivo. Perf provider-free: `scripts/p4_product_scale_isolated.py` (20/250/1000 notas); discriminar su coste O(N) de índices y del coste GPT.

### Rendimiento y búsqueda de fuente (P4)

`tests/core/test_vault_repository.py` participa en el gate transversal de rendimiento. Controla la caché opcional de lectura de P4 **limitada a cada petición**: el contenido y los listados solo pueden reutilizarse con las versiones físicas actuales; escritura Core, edición externa, borrado o symlink fuerzan lectura/scan fresco; límites de memoria; no cachear identidades entre entregas. Ejecutar `scripts/p4_source_hotpath_profile.py` sobre vault sintético para detectar el número REAL de recorridos y lecturas (250 notas: 31 enumeraciones y 8086 read calls antes de cache), y `scripts/p4_product_scale_isolated.py` para evaluar 20/250/1000 Notes sin LLM, con opción `ODYSSEY_P4_SCALE_COUNTS=250` para evitar el coste de reconstruir 1000 Notes en cada iteración. Ver [informe performance/SQLite](p4-sqlite-source-performance-20261017.md). Los índices SQLite existentes son pistas/materializaciones derivadas: no autorizan resultados de identidad/ausencia sin comprobar frescura de la fuente. No confundir tiempo de construcción de índices con tiempo de mensaje.
