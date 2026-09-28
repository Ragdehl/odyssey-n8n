# Semantic WRITE resolution v1

This is the focused live gate for the WRITE planner contract introduced after the relational READ stabilization work. It validates only the changed model-facing distinction: Luna describes the mutation target and fact references as semantic identity queries; Core owns retrieval, canonical identity resolution, and link binding.

The five frozen Spanish cases cover a real self relationship, a possessive-but-not-self target, a contextually described target, a described target plus a described fact reference, and a genuinely unsupported pronoun that must fail closed. The runner is planner-only and never executes a returned action against a vault.

The runner calls `OpenAILunaExperimentalPlanner` directly. Maximum provider calls equal the number of cases, automatic retries are zero, and there is no Sol fallback path. Evidence is written incrementally to a fixed non-overwriting JSONL path and execution stops on the first failing case.

`MAX_COST_USD` is currently reset to `$0.00`. The current-main gate was explicitly authorized at its `$0.070515` conservative no-cache ceiling and `58,227`-byte input bound, executed once, and then re-locked. Any future rerun therefore requires fresh explicit authorization. The runner still requires `--confirm-live-provider-calls`, refuses overwrite, uses zero automatic retries, and has no Sol fallback path.

## Authorized live evidence

The user explicitly authorized the original prepared gate after review of its `$0.059576` conservative ceiling. That historical run executed once at commit `c952260` with the fixed five-case registry and completed all five Luna/low calls with zero retries and zero Sol calls. It remains valid evidence for that exact pre-integration planner contract, not authorization or evidence for the current integrated contract.

All five cases passed their frozen structural oracle: self/coworker references, possessive-but-not-self child targeting, contextual friend targeting, described target plus described reference, and fail-closed escalation for the unsupported pronoun case. Recorded provider status was `completed` for every row. The usage-backed estimated actual cost from the retained token counts and pricing snapshot was `$0.00380296`.

The current-main contract was then explicitly authorized at a `$0.070515` conservative ceiling and executed once at commit `1f0047d`. It again completed all five Luna/low calls with zero retries and zero Sol calls, and all five frozen cases passed. Provider status was `completed` for every row. The usage-backed estimated actual cost was `$0.0044110`. The runner was immediately reset to `$0.00` after the successful run so that the retained authorization cannot be reused silently.
