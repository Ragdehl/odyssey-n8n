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

The release acceptance sequence (including independent audits, bounded real-model browser E2E and separate acceptance on deployed DEV) is owned by [Development Pipeline](development-pipeline.md). A green offline CI does not waive those gates; missing evidence must be shown as BLOCKED, never as product acceptance.

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

### Core P4 — catálogo físico por tipo/nombre/ID (octubre 2026)

`tests/core/test_verified_metadata_catalog.py` forma parte del grupo offline `performance_and_indexes`. Confirma equivalencia con búsqueda exacta anterior, sin segunda autoridad SQL, unicidad Day/Self/ID, cache solo request-scoped, revalidación de todas las fuentes y schema después de cambios externos, homónimos/duplicados y fail-closed ante Markdown inválido. Bench proveedor-free `scripts/p4_verified_catalog_scope_bench.py` mide 10 búsquedas exactas sobre 250 fuentes: ahorro por compartir una única validación física (no implica que una petición sencilla sea más rápida); ver [informe de metadatos verificados](p4-verified-metadata-scoping-20261017.md). No etiquetar una proyección derivada como fuente de identidad ni inferir que un índice SQLite sin resultado demuestra ausencia en vault.

### SQLite determinista (P4, formato 5)

`tests/core/test_context_deterministic_projection.py` mantiene el contrato de las tablas del `ContextIndex`: propiedades **completas**, `note_aliases`, `note_facts` por locator estable y capture/Temporal, integridad de marcadores heredados, wikilinks crudos y resueltos, backlink derivable por `target_id`, link por fact, ambigüedad de rutas casefold, futuras propiedades de personas bajo schema sintético, exactitud rebuild=incremental y versión de índice incompatible que exige rebuild. Se ejecuta con el gate transversal; ver [inventario y secuencia](p4-deterministic-sqlite-projection-20261017.md). No interpretar estas tablas como un segundo Canonical Writer ni usar SQLite stale para decidir unicidad o autorización SELF.

### P4 SQLite inventory, Core indexed queries and startup reuse — 2026-10-17

`tests/core/test_indexed_queries_and_freshness.py` validates complete physical-version inventory (including soft-deleted), typed read-only SQLite queries (ID, name/alias/type, all canonical attributes, atomic facts, outgoing and incoming wikilinks), grounding positives with Markdown SHA and canonical parser, fail-closed stale/negative or malformed index, new files, external rename, source change with mtime restored, bounded reconciliation, duplicate IDs, symlinks, and incremental refresh reading only the changed Markdown. `tests/core/test_vault_repository.py` now also compares fast `note_version_snapshot` with individual secure file versions and checks external symlinks and nested file changes. `tests/runtime/test_p4_index_startup_reuse.py` checks P4-only safe reuse of Context+Semantic+App indexes on restart; incompatible model/schema/modified Markdown triggers full rebuild. Gate `scripts/odyssey_cross_surface_gate.py` includes these files. Isolated performance `scripts/p4_product_scale_isolated.py` accepts `ODYSSEY_P4_SCALE_COUNTS=20,250,1000`; boot microbenchmark `scripts/p4_index_boot_isolated.py`. See [results](p4-sqlite-index-queries-reconciliation-performance-20261017.md). **These do not authorize DEV**, are not live n8n E2E, and do not cryptographically close multi-process write races.

### P4 — real external-process race test contract (2026-10-17)

`tests/core/test_index_publication_races.py` is part of `performance_and_indexes`. It uses actual independent Python processes that alter **synthetic** Markdown during embedding AND after constructing SQL rows (just before commit/replace), and verifies that `ContextIndex` full rebuild, incremental refresh and metadata-only refresh reject publication/commit without changing prior index bytes. `tests/runtime/test_p4_index_startup_reuse.py` similarly checks that a source edit during semantic index validation vetoes bootstrap index reuse. `tests/core/test_indexed_queries_and_freshness.py` verifies false-negative/positive checks when the source changes **between** inventory proof and SQL selection; no privileged services or API calls. Same-source CAS remains separate; these are freshness checks, not a multi-process filesystem transaction. See [P4 external races and indexed identity](p4-source-races-and-identity-lookup-20261017.md). Provider-free speed benchmark `scripts/p4_verified_catalog_scope_bench.py` tests 10 exact queries over 250 synthetic Notes and prints counts and elapsed time, but timing is not a CI threshold.
