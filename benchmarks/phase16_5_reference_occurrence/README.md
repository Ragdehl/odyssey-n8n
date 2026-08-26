# Phase 16.5A reference-occurrence benchmark

This is a small focused live-contract check for the existing production `gpt-5.6-sol` / low
planner. It does not select a model or test persistence. Ten occurrence cases plus the fifteen
existing Phase 15.1 planner cases are each sent once through the production prompt and Structured
Outputs schema, then validated by the local `validate_request_plan(...)` boundary and the existing
Phase 15.1 oracle.

The benchmark checks structured validity, local marker indexes, preserved mentions, repeated markers,
false-positive reference avoidance, and intent-shaped CREATE/UPDATE planning. It is evidence for the
planner contract, not a replacement for deterministic pytest coverage.

Run manually only when provider access is explicitly available:

```bash
.venv/bin/python -m benchmarks.phase16_5_reference_occurrence.run_benchmark \
  --run-id 2026-08-26-sol-low
```

The runner refuses to overwrite an existing result directory and records usage/cost metadata and
validated plans when the provider returns them. A failed call clears the previous response capture,
so mixed-success runs cannot reuse stale usage or output. It never calls a fallback model.

Final evidence is recorded in:

- `results/2026-08-26-sol-low-focused-final5`: 10/10 occurrence cases passed.
- `results/2026-08-26-sol-low-phase15-regression-final6`: 15/15 existing Phase 15.1 sentinels passed.

Earlier all-failure runs were caused by an intermittent provider-side condition; isolated diagnostic
calls succeeded and the final runs completed with response usage. The production planner continues to
keep the underlying provider exception wrapped as a fail-closed `RequestPlanningError`.

The 2026-08-26-sol-low-v2 attempt reached the configured provider but received provider-call
failures for all ten synthetic cases, with no usage counters; it is retained as unavailable live
evidence rather than treated as planner failures.
