# Sol fallback live gate v15

Focused one-shot evidence for the current ordinary Core fallback contract after everyday Journal capture moved to Calendar Day.

This gate deliberately does **not** use a Journal request. It reuses the frozen `SWR01-self-coworkers` ordinary WRITE sentinel (`Axel y Denis son mis compañeros de trabajo.`) and its established oracle.

- Model: `gpt-5.6-sol`, reasoning `low`.
- Maximum one provider call, zero automatic retries, no Luna calls, no vault mutation.
- Conservative standard cost upper bound: `$0.019407`; hard authorization ceiling: `$0.020`.
- Provider authority remains zero unless `ODYSSEY_RUN_PLANNER_SOL_FALLBACK_V15=1` is explicitly supplied after human authorization.
- Runner pins the current Sol prompt/provider schema, production model, frozen case, clean worktree, budget, and one-shot result directory.

Retained execution on `208c47de13075bf4aa1484aca74d165207e97f67`: one completed Sol/low response, zero retries, standard cost `$0.0028968`, `passed=true`. The complete retained artifact is `results/208c47de1307.json`.
