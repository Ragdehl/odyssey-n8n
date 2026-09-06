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

## Browser/workflow checks

The minimal `odyssey_web/` client has deterministic JavaScript tests in addition to Python static/contract coverage. GitHub CI runs the checked-in web JavaScript gate together with the Python/schema checks.

Versioned n8n Workflow SDK source under `workflows/` is validated through its repository tests/checks. Live n8n execution is required only when behavior depends on the actual n8n/runtime environment rather than static workflow structure.

## CI and review

GitHub CI independently validates pull requests and `main`. The stable required deterministic check is `Python CI / Python deterministic checks`; SonarQube Cloud adds code-quality/security analysis.

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
