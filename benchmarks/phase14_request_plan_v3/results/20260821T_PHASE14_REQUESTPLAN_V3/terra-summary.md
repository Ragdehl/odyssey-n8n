# Phase 14 RequestPlan v3 — Terra/low stage

This derived report summarizes immutable append-only provider evidence in
[`raw_results.jsonl`](raw_results.jsonl). The frozen v3 inputs and evaluator were
not modified during this execution.

## Execution

- Benchmark/oracle: v3.0.0; `gpt-5.6-terra`; reasoning effort `low`
- Logical requests: **24/24**, all cases, repetition 1; 24 API attempts
- Transport/provider failures: **0**; transport retries: **0**
- Sol and Luna: not executed; repetitions 2–4: not executed
- The runner was resumed after its local execution window, completing only the
  five then-missing requests. It did not duplicate or retry a completed request.

`metadata.json` locks SHA-256 values for the prompt, cases, oracle, schema
contract, pricing, and frozen `planner_capabilities.json`. It also records the
canonical `note-schema.json` SHA-256 that generated the snapshot.

## Quality totals

| Status | Count |
|---|---:|
| PASS | 23 |
| HUMAN REVIEW | 0 |
| MINOR | 0 |
| MAJOR | 0 |
| CRITICAL | 1 |

PASS cases: S01, S02, S03, S04, B01, B02, B03, B04, N01, N02, N03, U01,
U02, U03, C01, C02, C03, M01, M02, MC01, A01, A02, A03.

## Non-PASS case

### B05 — CRITICAL

Request: “¿Qué personas nacieron en 1990 o en 2000?”

Generated RequestPlan:

```json
{"actions":[{"kind":"retrieve","plan":{"query":"personas nacidas en 1990 o en 2000","type":"person","filters":[{"field":"birth_date","op":"gte","value":"1990-01-01"},{"field":"birth_date","op":"lt","value":"1991-01-01"}]}}],"limitations":[]}
```

Findings: `narrow_range_filter` and `missing_retrieval_coverage`. Terra emitted
only the 1990 half-open range and omitted the requested 2000 candidate set. The
output was structurally valid, but its hard date filter deterministically loses
candidates.

There were no HUMAN REVIEW results.

## Targeted review

- S02 used `created_at`, not `entry_date`, with valid timezone-aware day bounds.
- S03 kept idea/review language semantic and emitted neither `type=concept` nor a tag filter.
- B01, B03, N03, A02, and A03 emitted valid timezone-aware lifecycle datetimes.
- B05 emitted valid half-open date syntax, but only for 1990; it failed to cover the requested OR.
- B04 kept semantic OR in one retrieval; N03/A02/A03 used explicit multi-type restrictions; C01–C03 and MC01 were create-only; M01/M02 were mixed create/retrieve; U01/A01/U02/U03 used the expected limitation codes.

## Deterministic safety verdict

| Question | Verdict |
|---|---|
| A. Any deterministic CRITICAL candidate loss? | **Yes — B05** omits people born in 2000. |
| B. Any false hard filter? | **Yes — B05** restricts `birth_date` to 1990 only. |
| C. Any invalid RequestPlan? | No; all 24 responses passed local contract validation. |
| D. Any missing requested retrieval branch? | **Yes — B05** lacks coverage for the 2000 date branch. |
| E. Any unrequested CreateNoteAction? | No. |
| F. Any genuinely problematic semantic HUMAN REVIEW issue? | No HUMAN REVIEW findings. |

## Provider counters, cache, latency, and cost

- Cache-write requests/tokens: **1 / 3,524**
- Cached-read requests/cached-input tokens: **23 / 81,052**
- Ordinary input tokens: **462**
- Output tokens: **1,884**; reasoning tokens: **109**
- Actual estimated cost: **$0.060691**
- Approximate no-cache counterfactual: **$0.240855**
- Mean latency: **2.073 s**; median latency: **2.017 s**

The counters show one prefix write followed by 23 cached reads; this is observed
provider usage, not an assumed cache outcome. The counterfactual prices every
recorded input token as ordinary input using the locked Terra pricing snapshot.

## Terra v2.2 comparison

Terra v2.2 had five unresolved transport failures and two deterministic CRITICAL
quality failures: S02 incorrectly used `entry_date`, and S03 narrowed semantic
idea/review language to `concept` plus a tag filter. v3 completed all 24 calls,
used the frozen current context, and passed S02/S03 as well as the timezone-aware
lifecycle regressions. This supports the date guidance, visible context, and
conservative type/tag simplification fixing those observed classes.

The B04 semantic-OR and former tag cases changed v3 semantics by design, so their
PASS results are not direct like-for-like improvement claims. v3 still has the
new B05 deterministic OR-range candidate loss; Terra is therefore **not
safety-clean** and this report does not authorize a Sol run.
