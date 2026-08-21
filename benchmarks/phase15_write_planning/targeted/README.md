# Phase 15 targeted planner follow-up

This frozen five-case follow-up checked the two material findings from the
completed 18-case Sol/low run, plus three retrieval/read-write sentinels. It
reuses the canonical Phase 15 frozen prompt and capability snapshot; it does
not alter the original 18-case experiment.

The completed five-case pass used this command from the repository root:

```bash
python -m benchmarks.phase15_write_planning.targeted.run_benchmark \
  --run-id phase15-sol-low-targeted-20260821 --configuration sol
```

The experiment is exactly five cases, one repetition, `gpt-5.6-sol` at low
reasoning effort, with `store=False`. Any write result requires human semantic
review after the deterministic checks.

The run completed as follows: T01, T02, T03, and T05 were acceptable. T04
initially collapsed the 1990/2000 OR into one unsatisfiable AND filter. One
frozen-prompt T04 repeat then passed with two independent candidate sets. No
further paid calls are required; raw evidence is preserved under `results/`.
