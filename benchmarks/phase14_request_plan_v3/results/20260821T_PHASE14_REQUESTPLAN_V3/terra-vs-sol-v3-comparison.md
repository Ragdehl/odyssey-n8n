# Phase 14 RequestPlan v3 — Terra vs Sol

This comparison is derived from the immutable Terra and Sol request records in
[`raw_results.jsonl`](raw_results.jsonl), using the frozen v3 evaluator and
pricing snapshot.

| Metric | Terra/low | Sol/low |
|---|---:|---:|
| Requests / API attempts | 24 / 24 | 24 / 24 |
| PASS | 23 | 23 |
| HUMAN REVIEW / MINOR / MAJOR | 0 / 0 / 0 | 0 / 0 / 0 |
| CRITICAL | 1 (B05) | 1 (S04) |
| Invalid RequestPlans | 0 | 1 (S04) |
| Transport failures / retries | 0 / 0 | 0 / 0 |
| Mean / median latency | 2.073 / 2.017 s | 2.873 / 2.683 s |
| Estimated cost | $0.060691 | $0.138511 |

Sol solves Terra’s B05 deterministic OR-range failure: it emits separate
retrieval branches for 1990 and 2000. Across S02, S03, B01, B03, N03, A02, and
A03, Sol preserves the required date, type, branch, and lifecycle behavior.
The quality improvement is therefore a failure-class substitution, not an
aggregate PASS-rate improvement: both models are 23/24, but Terra loses recall
on B05 while Sol produces an invalid plan on S04.

Sol is approximately 2.28× Terra’s estimated cost and 1.39× Terra’s mean
latency. Sol’s observed cache pattern is one write (3,524 tokens) and 23 reads
(81,052 cached tokens), the same pattern observed in Terra’s stage; this does
not imply a shared cache entry.

## Deterministic production verdict

1. Sol solves B05: **yes**, with both deterministic candidate regions.
2. Sol introduces a new failure Terra did not have: **yes**, S04’s empty-query
   invalid RequestPlan.
3. The observed difference does not justify selecting Sol solely on this
   benchmark. It removes one critical class but leaves one critical and costs
   substantially more.
4. A simpler safeguard is preferable as the first production response: retain
   Terra and add deterministic post-validation for empty required queries plus
   explicit OR-range coverage checks. A planner-contract clarification showing
   that deterministic OR date conditions require independent actions would also
   directly target B05. If those safeguards cannot guarantee acceptable recall,
   Sol becomes the safer fallback for the affected request class.

## B05 architectural review

Terra’s B05 output was structurally valid but represented only the 1990
half-open interval. This is primarily a planner-guidance/model-capability
boundary issue: the contract permits ordered multiple RetrieveActions, but does
not make the deterministic decomposition of disjoint OR ranges prominent
enough to guarantee the behavior. It is not evidence that the RequestPlan
architecture needs a new service or storage layer.

The production decision should combine contract guidance with deterministic
post-validation. The validator can detect that a request contains explicit
disjoint date alternatives and that generated hard filters cover only one
region; it can reject or repair/escalate rather than silently lose candidates.
The same post-validation should reject S04-style empty retrieval queries.
Benchmark artifacts remain frozen; no such change is made here.
