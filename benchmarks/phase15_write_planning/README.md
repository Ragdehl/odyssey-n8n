# Phase 15 write-planning benchmark — prepared, not executed

This is a frozen-before-calls incremental benchmark for the Phase 15 contract in
[`docs/architecture/phase-15-write-planning.md`](../../docs/architecture/phase-15-write-planning.md).
It reuses Phase 14's Sol/low Responses/Structured-Output approach and its recall-first retrieval
expectations, but does not rerun the full Phase 14 experiment or compare models.

One approved future pass is exactly **17 Sol/low calls**: seven Phase 14 regression cases (`R01`–`R07`)
and ten Phase 15 write cases (`W01`–`W10`). No repeat is planned. A failed or suspicious individual
case may be repeated only after evidence justifies it.

The local oracle is intentionally narrow. It treats malformed output, loss of an expected retrieval
branch, lost write unit/fact/reference, wrong intent, invented physical persistence decision or
identity, invalid canonical type, and unsafe `amend`/`remove`/`delete` creation implication as
critical. Query/fact wording is only token-group diagnostics, not a general semantic evaluator.

After human approval, the expected command is:

```bash
python -m benchmarks.phase15_write_planning.run_benchmark --run-id sol-low-initial --configuration sol
```

Do not run it during preparation: it calls the OpenAI API and writes append-only evidence under
`benchmarks/phase15_write_planning/results/`.
