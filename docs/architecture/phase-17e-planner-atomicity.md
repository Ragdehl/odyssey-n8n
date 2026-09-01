# Phase 17E planner semantic atomicity

Status: **completed focused subphase**

## Objective

Validate and, if necessary, minimally clarify the production Sol/low planner instruction so
“atomic fact” means independently meaningful durable knowledge rather than one sentence or clause.
The observed failures and retrieval context are recorded in the
[Phase 17E retrieval benchmark](phase-17e-retrieval-benchmark.md).

## Acceptance criteria

- Preserve the existing 11 planner cases and corrected semantic evaluator.
- Freeze approximately five additional adversarial semantic-atomicity cases before prompt editing.
- Make at most one concise production prompt clarification; do not change the schema or planner
  structured-output contract.
- Run focused live Sol/low evidence for the existing and new cases, preserving raw outputs.
- The two existing coherent-material failures no longer materially over-split, prior PASS cases do
  not regress, and genuinely independent facts remain separate.
- If the hypothesis fails, stop without iterative prompt tuning and record the evidence.

## Evidence

The one prompt clarification was applied and validated with the existing 11 cases and five frozen
adversarial cases using `gpt-5.6-sol` with low reasoning. Offline-corrected results were 11/11 PASS
for the existing cases and 5/5 PASS for the new cases. The two original critical cases remained PASS
in the permitted stability rerun. The raw outputs are preserved in
[`planner_live_results.jsonl`](../../benchmarks/phase17e_retrieval/planner_live_results.jsonl) and
[`planner_atomicity_live_results.jsonl`](../../benchmarks/phase17e_retrieval/planner_atomicity_live_results.jsonl).
The permitted second stability run for the two critical cases is preserved in
[`planner_critical_stability_run2.jsonl`](../../benchmarks/phase17e_retrieval/planner_critical_stability_run2.jsonl).

The evaluator's symmetric containment is a benchmark correction: `entities` are semantic target
descriptions, while Sol may return a shorter canonical identity or a more specific query. The
smallest rule is normalized containment in either direction; clearly unrelated descriptions do not
match. This affects the existing `one-coherent-concept` case (its expected description is longer
than Sol's returned identity) and no other current case. It changes benchmark evaluation only, not
production planner behavior or expectations.

The evidence showed that independent facts still split, references and multiple entities remain
attributable, and coherent explanations, reflections, and dependent-reason decisions remain unified.
No production retrieval behavior was changed. The planner precondition is sufficiently trustworthy
to proceed to a separate retrieval adoption decision, but this subphase does not adopt Combined.

## Out of scope

- Combined or other production retrieval changes, ContextIndex, Top-K, or MiniLM changes.
- New models, planner passes, deterministic regrouping, type-specific writing profiles, schema or
  persistence changes, n8n, Phase 18, and autonomous write authority changes.

## Open decisions

None. The single semantic-atomicity clarification is sufficient for this focused planner
precondition, and the evidence is sufficient to proceed to the separate Phase 17E retrieval
adoption decision. This subphase does not adopt Combined.
