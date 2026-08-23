# Phase 15.2 selection-anchor benchmark

This append-only, focused benchmark validates the production Phase 15.2 request planner after all
local deterministic checks pass. It has fifteen Sol/low calls covering explicit nominal anchors,
direct-note versus graph intent, property-selected graph anchors, independent filters, explicit
two-hop scope, explicit-only controlled tag retrieval/mutation, and compact Phase 15.1 regressions.

Each result row preserves the exact user input, fixed current context, effective canonical schema and
capabilities, production prompt and strict Structured Outputs request, prompt/schema digests, raw
model output, local validation, narrow deterministic oracle result, latency, and provider usage.
The harness uses `gpt-5.6-sol`, low reasoning effort, `store=false`, `max_retries=0`, and no hidden
corrective pass. It only resumes an interrupted directory by appending previously missing case IDs
after verifying identical metadata; completed calls are never repeated or overwritten.

Run only once deterministic validation is green:

```bash
.venv/bin/python -m benchmarks.phase15_2_selection_anchors.run_benchmark phase15-2-sol-low-YYYYMMDD
```
