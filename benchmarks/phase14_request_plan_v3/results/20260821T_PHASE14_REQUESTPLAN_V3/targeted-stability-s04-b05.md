# Phase 14 v3 targeted stability experiment: S04 / B05

Status: **complete**. The frozen v3 benchmark was evaluated across four logical repetitions for each targeted model/case pair. Host retries were appended to the existing run; no benchmark input, evaluator, production code, or historical summary was changed.

## Observed stability

| Model | Case | Rep 1 | Rep 2 | Rep 3 | Rep 4 | PASS |
|---|---|---|---|---|---|---:|
| Terra | S04 | PASS | PASS | PASS | PASS | 4/4 |
| Terra | B05 | CRITICAL | CRITICAL | CRITICAL | CRITICAL | 0/4 |
| Sol | S04 | CRITICAL | PASS | PASS | PASS | 3/4 |
| Sol | B05 | PASS | PASS | PASS | PASS | 4/4 |

Every logical repetition has an actual model-quality observation. Host retry records retain repetitions 2–4 and use attempt 3. Earlier attempt 1 and attempt 2 transport failures remain append-only evidence; they are not quality observations and are excluded from the matrix.

## Evidence integrity

- Raw evidence contains 84 request records: the original 60 plus 24 successful targeted retries.
- No request outside S04/B05 received a new attempt.
- No repetition greater than 4 exists, and repetition 1 was not rerun.
- Frozen cases, oracle, prompt, schema contract, planner capabilities, pricing, and metadata are unchanged.

## B05: disjunctive birth-year retrieval

Request: `¿Qué personas nacieron en 1990 o en 2000?`

Terra's four effective plans are structurally valid but each contains only the half-open 1990 interval (`1990-01-01` inclusive through `1991-01-01` exclusive). Every Terra repetition omits the 2000 interval. The evaluator findings are `narrow_range_filter` and `missing_retrieval_coverage`.

Therefore Terra B05 success is **0/4**. The failure is reproducible and systematic under this frozen benchmark: it is a silent, valid-but-wrong RequestPlan that can execute successfully while losing requested candidates.

Sol produces both required half-open intervals in all four effective plans: 1990–1991 and 2000–2001. Sol B05 success is **4/4**.

## S04: exact alias retrieval

Request: `¿Qué notas tienen exactamente el alias "Ody"?`

Terra produces a non-empty retrieval query and an `aliases contains "Ody"` filter in all four repetitions: **4/4 valid plans**.

Sol repetition 1 is **CRITICAL** because the query is empty; local RequestPlan validation rejects it. Sol repetitions 2–4 each contain a non-empty query and `aliases contains "Ody"`, so Sol succeeds **3/4**. The observed Sol failure did not reproduce in the three follow-up repetitions and is locally detectable before retrieval.

## Failure severity

These are not equivalent CRITICAL failures. Terra B05 is structurally valid but semantically incomplete: it creates a silent deterministic recall loss that downstream retrieval may execute without warning. Sol S04 is structurally invalid and is rejected by local RequestPlan validation before retrieval. The former can silently omit requested data; the latter is visible and blockable.

## New successful targeted observations

Counters below include only the six new successful observations per model (S04/B05, repetitions 2–4). Transport attempts returned no provider usage and are excluded.

| Metric | Terra | Sol |
|---|---:|---:|
| Successful observations | 6 | 6 |
| Input tokens | 21,258 | 21,258 |
| Cached-input tokens | 17,620 | 17,620 |
| Cache writes / tokens | 1 / 3,524 | 1 / 3,524 |
| Cache reads / requests | 5 / 17,620 | 5 / 17,620 |
| Output tokens | 444 | 647 |
| Reasoning tokens | 0 | 0 |
| Estimated cost | **$0.0223625** | **$0.050815** |
| Mean latency | 2.189 s | 2.524 s |
| Median latency | 2.052 s | 2.363 s |

Sol's targeted successful observations cost **2.2728×** Terra's (about **2.27×**). Both models observed one cache write of 3,524 tokens and five cached reads totaling 17,620 cached-input tokens in this six-observation stage. These are actual provider counters, not inferred cache behavior.

## Cumulative known v3 spend

Earlier v3 stages recorded $0.060691 for Terra and $0.138511 for Sol. Adding the new successful targeted stages gives:

- Terra: $0.060691 + $0.0223625 = **$0.0830535**
- Sol: $0.138511 + $0.050815 = **$0.189326**
- Combined known v3 spend: **$0.2723795** (about **$0.27238**)

The 24 failed transport attempts are excluded because the provider returned no usage or cost counters.

## Production recommendation

Use **Sol as the Phase 14 production planner baseline**. It costs about 2.3× Terra in these observations, but correctly covers the disjunctive B05 case in 4/4 repetitions, while Terra exhibits a reproducible silent candidate-loss failure in 0/4. Sol's one S04 invalid output was locally detectable and did not recur in repetitions 2–4.

On this evidence, Sol's price premium is **justified** for the safety-critical planner role. A Terra/Sol router is **not justified now** merely to save fractions of a cent per request. Routing can remain a later optimization after real production request distribution and monthly cost are known; it should not be introduced before that evidence exists.

## Deferred cleanup before production integration

- Correct the reusable planner capability builder's `relationship_to_user` operator derivation.
- Consider physical removal of old tag machinery from Core only as the separately planned cleanup if Phase 14 adopts the tagless v3 planner.
- Add simple deterministic invalid-output handling for cases such as an empty retrieval query.

These are deferred cleanup items, not changes made by this experiment. No second semantic validator or planner is proposed.

## Scope confirmation

- Only this derived report and the already appended raw retry evidence are in scope for the branch changes.
- Frozen benchmark artifacts and semantics are unchanged.
- Production code and `note-schema.json` are unchanged.
- No merge was performed.
