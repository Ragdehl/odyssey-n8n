# Semantic WRITE resolution v1

This is the focused live gate for the WRITE planner contract introduced after the relational READ stabilization work. It validates only the changed model-facing distinction: Luna describes the mutation target and fact references as semantic identity queries; Core owns retrieval, canonical identity resolution, and link binding.

The five frozen Spanish cases cover a real self relationship, a possessive-but-not-self target, a contextually described target, a described target plus a described fact reference, and a genuinely unsupported pronoun that must fail closed. The runner is planner-only and never executes a returned action against a vault.

The runner calls `OpenAILunaExperimentalPlanner` directly. Maximum provider calls equal the number of cases, automatic retries are zero, and there is no Sol fallback path. Evidence is written incrementally to a fixed non-overwriting JSONL path and execution stops on the first failing case.

`MAX_COST_USD` is `$0.06`, matching the explicit user authorization recorded after review of the `$0.059576` conservative no-cache ceiling. The runner still requires `--confirm-live-provider-calls`, refuses overwrite, uses zero automatic retries, and has no Sol fallback path.
