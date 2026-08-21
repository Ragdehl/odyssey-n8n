# Phase 14 RequestPlan v3 — Sol/low stage

This derived report summarizes the immutable append-only provider evidence in
[`raw_results.jsonl`](raw_results.jsonl). Frozen v3 inputs, evaluator semantics,
Terra evidence, and production code were not modified.

## Execution

- Benchmark/oracle: v3.0.0; `gpt-5.6-sol`; reasoning effort `low`
- Logical requests: **24/24**, all cases, repetition 1; 24 API attempts
- Transport/provider failures: **0**; transport retries: **0**
- Terra was not rerun; Luna and repetitions 2–4 were not executed

## Quality totals

| Status | Count |
|---|---:|
| PASS | 23 |
| HUMAN REVIEW | 0 |
| MINOR | 0 |
| MAJOR | 0 |
| CRITICAL | 1 |

PASS cases: S01, S02, S03, B01, B02, B03, B04, B05, N01, N02, N03, U01,
U02, U03, C01, C02, C03, M01, M02, MC01, A01, A02, A03.

## Non-PASS case

### S04 — CRITICAL

Request: “¿Qué notas tienen exactamente el alias \"Ody\"?”

Generated RequestPlan:

```json
{"actions":[{"kind":"retrieve","plan":{"query":"","type":null,"filters":[{"field":"aliases","op":"contains","value":"Ody"}]}}],"limitations":[]}
```

Finding: `invalid_model_output`; local RequestPlan validation rejected the
retrieval plan because its required query was empty. This is model-quality
evidence, not a transport failure, and it was not retried.

## Targeted review

- S02 used `created_at`, not `entry_date`; S03 kept idea/review semantic and did
  not add `type=concept`.
- B01 retained two independent lifecycle branches.
- B03 covered “created yesterday” and “updated today”.
- B05 emitted both deterministic half-open `birth_date` ranges: 1990 and 2000.
- N03, A02, and A03 preserved shared multi-type lifecycle restrictions.
- Create-only, mixed retrieve/create, compound actions, limitation codes, and
  ordinary semantic OR cases passed.
- No unexpected hard filters, unrequested create actions, HUMAN REVIEW findings,
  or additional invalid outputs were observed.

## Deterministic safety verdict

| Question | Verdict |
|---|---|
| A. Any deterministic CRITICAL candidate loss? | No. |
| B. Any false hard filter? | No. |
| C. Any invalid RequestPlan? | **Yes — S04**, empty retrieval query. |
| D. Any missing requested retrieval branch? | No; B05 has both branches. |
| E. Any unrequested CreateNoteAction? | No. |
| F. Any genuinely problematic semantic HUMAN REVIEW issue? | No. |

## Provider counters, cache, latency, and cost

- Cache-write requests/tokens: **1 / 3,524**
- Cached-read requests/cached-input tokens: **23 / 81,052**
- Ordinary input tokens: **462**; total input tokens: **85,038**
- Output tokens: **2,455**; reasoning tokens: **613**
- Actual estimated cost: **$0.138511**
- Approximate no-cache counterfactual: **$0.498840**
- Mean latency: **2.873 s**; median latency: **2.683 s**

All values are calculated from recorded provider counters and the frozen pricing
snapshot; no cache sharing with Terra is assumed.
