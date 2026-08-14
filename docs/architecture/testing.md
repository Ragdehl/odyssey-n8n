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

Python application-core tests live under `tests/core/` and use the standard-library `unittest` framework. Run them from the repository root so `odyssey_core/` imports directly without a packaging or installation step:

```bash
python3 -m unittest discover -s tests -v
```

The initial test is structural only because the bootstrapped package has no domain or vault-repository behavior yet. Future tests should assert real contracts as those capabilities are deliberately introduced.

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
