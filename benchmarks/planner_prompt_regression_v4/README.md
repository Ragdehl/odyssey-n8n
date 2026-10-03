# Core planner prompt regression v4

This one-shot gate succeeds v3 after Journal convergence. It retains the full 16-case regression
surface but replaces only SWR07/SWR08/SWR10, whose historical source was an event-like
`journal_entry`, with the separately versioned current-schema bounded-source successors using the
canonical `document` source `Directorio Faro`.

The ordinary Core prompt, provider schema, teaching examples, model, and reasoning effort are
unchanged from v3. No Event semantics, Journal prompt rules, or source-type-specific planner rules
are added. The successor evaluator checks the same generic invariant: a bounded existing source
constrains the candidate universe and qualifiers select only within it.

Provider authority remains zero unless the exact matrix/contract/budget preflight matches and the
explicit authorization environment flag is set. The gate is one-shot, zero-retry, and retains only
bounded result/evaluation/usage evidence.

- Maximum provider calls: `16`.
- Conservative ceiling: `$0.2076192`; hard authorization cap: `$0.210`.
