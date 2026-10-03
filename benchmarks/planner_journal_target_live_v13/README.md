# Planner Journal target live gate v13

v13 follows the retained v12 partial failure. The canonical `note-schema` now states that a journal record write must carry the user-referred date in two schema-driven places: an exact `entry_date` target filter for same-day identity resolution and an `entry_date` property so Core can create the correctly dated entry when no match exists.

No Journal-specific rule is added to Core. Existing generic Core behavior already applies target filters against authoritative Markdown before identity resolution and creates a typed target when no allowed existing identity resolves.

The gate makes exactly two GPT-5.6 Luna low calls (`hoy` and `ayer`), with zero automatic retries and no Sol fallback. It is mutation-free, requires a clean worktree and explicit `ODYSSEY_RUN_PLANNER_JOURNAL_TARGET_V13=1`, and refuses a second retained result. Conservative regional authority is below $0.030.
## Retained result

v13 ran once on `688a0cb633d4450b4aa3440686527e6d4de40461`. Both GPT-5.6 Luna low calls passed: `hoy` and `ayer` each emitted an exact `entry_date` target filter and the same `entry_date` property, preserving the fact text. There were 2 completed provider responses, zero automatic retries, and no provider failures. Estimated observed cost was $0.00468360 Standard / $0.00515196 regional.
