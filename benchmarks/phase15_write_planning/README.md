# Phase 15 write-planning benchmark — validated

This is the frozen incremental benchmark record for the Phase 15 contract in
[`docs/architecture/phase-15-write-planning.md`](../../docs/architecture/phase-15-write-planning.md).
It reuses Phase 14's Sol/low Responses/Structured-Output approach and its recall-first retrieval
expectations, but does not rerun the full Phase 14 experiment or compare models.
`planner_capabilities.json` is a new frozen projection of current production capabilities at the
fixed benchmark context; it deliberately does not reuse the historical Phase 14 snapshot.

The completed full pass was exactly **18 Sol/low calls**: seven Phase 14 regression cases (`R01`–`R07`)
and eleven Phase 15 write cases (`W01`–`W11`). The initial schema-compatibility attempt produced zero
model outputs and remains preserved as failed harness evidence; it is not model evidence.

The local oracle is intentionally narrow. It treats malformed output, loss of an expected retrieval
branch, lost write unit/fact/reference, unexpected fact count where the oracle fixes it, wrong intent,
invented physical persistence decision or identity, invalid canonical type, and unsafe
`amend`/`remove`/`delete` creation implication as critical. Query/fact wording is only token-group
diagnostics, not a general semantic evaluator. Every result containing a `WriteAction` is marked
`HUMAN REVIEW` after deterministic checks, because structure cannot reliably detect semantic
persistence instructions or invented identity hidden inside free-text `subject`, `facts`, or `role`.
Retrieval-only cases can still pass deterministically. No second evaluator LLM is used.

The completed pass used:

```bash
python -m benchmarks.phase15_write_planning.run_benchmark --run-id phase15-sol-low-20260821-v2 --configuration sol
```

Human review corrected two planner-boundary findings: semantic “before” no longer becomes lifecycle
metadata, and write-target existence no longer creates a `RetrieveAction`. A five-case targeted
follow-up then validated those fixes and regression sentinels. T04 failed once on the OR boundary,
then passed on one frozen-prompt repeat with independent 1990 and 2000 candidate sets; this is
accepted as isolated stochastic variance. No further calls are required. Evidence remains append-only
under `benchmarks/phase15_write_planning/results/`; the targeted experiment is documented in
[`targeted/README.md`](targeted/README.md).
