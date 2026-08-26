# Phase 16.5A reference-occurrence benchmark

This is a small focused live-contract check for the existing production `gpt-5.6-sol` / low
planner. It does not select a model or test persistence. The suite selector runs the ten occurrence
cases, fifteen existing Phase 15.1 cases, or six late-Phase-15 sentinels through the production
prompt and Structured Outputs schema, then validates each with the corresponding existing oracle.

The benchmark checks structured validity, local marker indexes, preserved mentions, repeated markers,
false-positive reference avoidance, and intent-shaped CREATE/UPDATE planning. It is evidence for the
planner contract, not a replacement for deterministic pytest coverage.

Run manually only when provider access is explicitly available:

```bash
.venv/bin/python -m benchmarks.phase16_5_reference_occurrence.run_benchmark \
  --run-id 2026-08-26-sol-low-focused-final5 --suite occurrence

.venv/bin/python -m benchmarks.phase16_5_reference_occurrence.run_benchmark \
  --run-id 2026-08-26-sol-low-phase15-regression-final6 --suite phase15_1

.venv/bin/python -m benchmarks.phase16_5_reference_occurrence.run_benchmark \
  --run-id 2026-08-26-sol-low-late-phase15-final --suite late_phase15
```

The runner refuses to overwrite an existing result directory and records usage/cost metadata and
validated plans when the provider returns them. A failed call clears the previous response capture,
so mixed-success runs cannot reuse stale usage or output. It never calls a fallback model.

Final evidence is recorded in:

- `results/2026-08-26-sol-low-focused-final5`: 10/10 occurrence cases passed.
- `results/2026-08-26-sol-low-phase15-regression-final6`: 15/15 existing Phase 15.1 sentinels passed.
- `results/2026-08-26-sol-low-late-phase15-final2`: 6/6 late-Phase-15 sentinels pass under the
  Phase 15 semantic contract. The already-recorded T03 output targets Marta, sets
  `relationship_to_user` to `hermana`, explicitly adds `review`, and explicitly removes it in the
  following unit without unrelated mutations. Its first unit uses `record`, which is valid alongside
  `amend` for property `set` and explicit tag changes; the Phase 16.5 adapter no longer freezes the
  historical `amend` label. No new live model call was required; the raw model output is unchanged.

Earlier all-failure runs were caused by an intermittent provider-side condition; isolated diagnostic
calls succeeded and the final runs completed with response usage. The production planner continues to
keep the underlying provider exception wrapped as a fail-closed `RequestPlanningError`.
