# Planner prompt regression v3

One-shot production GPT-5.6 Luna / low regression gate for the Core planner after everyday Journal capture moved to Calendar Day.

The gate inherits the exact 16-case frozen matrix and oracle from v1/v2. It intentionally adds no Journal case: personal diary capture is now routed to Calendar before Core. Its purpose is to prove that removing legacy `journal_entry` from planner write capabilities does not regress ordinary Core READ/WRITE/relationship/clarification behavior.

- Model: `gpt-5.6-luna`, reasoning `low`.
- Maximum 16 provider calls, zero automatic retries, zero Sol calls, no vault mutation.
- Conservative one-byte-as-token ceiling: `$0.2076192`; hard authorization ceiling: `$0.210`.
- Provider authority remains zero until `ODYSSEY_RUN_PLANNER_PROMPT_REGRESSION_V3=1` is explicitly supplied after human authorization.
- Runner pins the inherited matrix, current prompt/provider schema, unchanged teaching examples, production model, clean worktree, budget, and one-shot result directory.

Retained execution on `208c47de13075bf4aa1484aca74d165207e97f67`: 16/16 completed responses, zero retries/Sol, standard cost `$0.0367568`, `acceptable=false`. Failed IDs were `SWR07-qualified-event-member`, `SWR08-relational-target-described-reference`, `SWR10-relational-target-two-bounded-references`, and `SWF-MIXED-ORDER-01`. The detailed row artifact was accidentally overwritten during post-run local staging because multiple gates shared the same commit-derived filename; `results/208c47de1307.reconstructed.json` records only the runner stdout facts and is explicitly marked as reconstructed. Do not accept the new Core contract or rerun this gate under the consumed authorization.
