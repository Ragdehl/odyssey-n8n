# Phase 16.5A reference-occurrence benchmark

This is a small focused live-contract check for the existing production `gpt-5.6-sol` / low
planner. It does not select a model or test persistence. Each synthetic request is sent once through
the production prompt and Structured Outputs schema, then validated by the local
`validate_request_plan(...)` boundary.

The benchmark checks structured validity, local marker indexes, preserved mentions, repeated markers,
false-positive reference avoidance, and intent-shaped CREATE/UPDATE planning. It is evidence for the
planner contract, not a replacement for deterministic pytest coverage.

Run manually only when provider access is explicitly available:

```bash
.venv/bin/python -m benchmarks.phase16_5_reference_occurrence.run_benchmark \
  --run-id 2026-08-26-sol-low
```

The runner refuses to overwrite an existing result directory and records compact usage/cost metadata
when the provider returns it. It never calls a fallback model.

The 2026-08-26-sol-low-v2 attempt reached the configured provider but received provider-call
failures for all ten synthetic cases, with no usage counters; it is retained as unavailable live
evidence rather than treated as planner failures.
