# Testing Strategy

## Principle

Every primitive and workflow must have a repeatable contract and be verified before it is considered complete:

```text
known input
    |
    v
workflow
    |
    v
expected output and state
    |
    v
 PASS / FAIL
```

Tests are not implemented in Phase 0. This document defines the strategy that later phases must apply.

## Deterministic primitives

Storage and ontology primitives should be tested with controlled fixtures and explicit preconditions. At minimum, cover:

- the normal case;
- entity or data not found;
- duplicate and idempotency behavior where applicable;
- malformed input;
- an invalid operation where applicable.

Tests must assert both the returned contract and the resulting Markdown state. Where a primitive can be retried, the test should demonstrate that a repeated identical request does not create unintended duplicates or changes.

## Subworkflow contract testing

Each reusable n8n subworkflow should have documented input and output schemas, structured error behavior, and test cases independent of its callers. Tests should use known input and isolated fixture data where possible.

Contract tests should verify validation, mapping, branch behavior, error propagation, and output shape. Native n8n workflow validation is useful but does not replace behavioral assertions against expected output and state.

## Python core testing

Python tests live under `tests/`. Pytest is the official runner and discovers the existing
`unittest` suite without requiring a mass migration. New tests should normally use native pytest
style, including fixtures and parametrization when they improve clarity. Existing unittest tests
may be migrated incrementally when functional work already modifies them.

From the repository root, create an isolated development environment and install the pinned tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The first command creates the repository-local virtual environment, the second activates it for the
current shell, and the final command installs the exact development-tool versions recorded in
`requirements-dev.txt`. This is development setup only; Odyssey remains an unpackaged application
with no added runtime dependencies.

Run the complete Python suite:

```bash
pytest
```

Pytest reads `testpaths` from `pyproject.toml`, so this runs every Python test beneath `tests/`.
The suite includes structural package checks, temporary-directory `VaultRepository` contract tests,
and isolated note codec, note validation, and schema tests.

Run Ruff's defect and consistency checks across all tracked Python locations:

```bash
ruff check odyssey_core scripts tests
```

Format those locations in place:

```bash
ruff format odyssey_core scripts tests
```

To verify formatting without changing files, add `--check`:

```bash
ruff format --check odyssey_core scripts tests
```

Install the Git pre-commit hook once per clone:

```bash
pre-commit install
```

This writes the local Git hook that runs Ruff linting, Ruff's format check, the complete pytest
suite, and the canonical schema validator before each ordinary commit. Run the same gates manually
against every tracked file with:

```bash
pre-commit run --all-files
```

`--all-files` checks the repository rather than only changes staged for the next commit. The pytest
and schema hooks deliberately ignore filenames supplied by pre-commit so each always runs its full
intended suite.

## Integration testing

Integration tests verify composition across boundaries, such as:

- domain workflow to ontology primitives;
- ontology primitives to the storage layer;
- Raspberry Pi host paths to the `/odyssey` n8n container mount;
- webhook request to a stable response contract;
- Markdown output remaining usable by Obsidian.

Use dedicated fixtures or a clearly isolated test area. Tests must not overwrite production notes or require exposing credentials. Destructive cleanup should be narrowly scoped and recoverable when practical.

## Future AI evaluations

AI-dependent extraction, classification, resolution, and reasoning require multi-case evaluation datasets rather than one successful example. Evaluation cases should include ordinary inputs, ambiguity, conflicting facts, aliases, near-duplicates, malformed input, and domain-specific edge cases.

Expected results may combine exact assertions for structured fields with bounded qualitative criteria for generated content. Model or prompt changes should be compared against the same versioned dataset. Deterministic validation remains responsible for enforcing contracts after AI output.

## Completion evidence

A workflow is complete only after its applicable validation and tests pass. Its behavior documentation should record repeatable verification commands and any durable limitation. Git branches, commits, Pull Requests, and test results track development state.
