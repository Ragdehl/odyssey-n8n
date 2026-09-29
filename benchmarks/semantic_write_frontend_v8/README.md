# Semantic WRITE frontend v8

This is the offline successor to consumed v6 and retired-unexecuted v7. It intentionally restores the **known-best teaching semantics** from the checkpoint that passed SWR01-SWR07; the only mechanical teaching-data change is the renamed source enum required by the semantic schema. No new teaching example and no ownership-example retuning is introduced.

The remaining abstraction is moved into the semantic contract itself: provider-facing `EXISTING_DESCRIPTION` becomes `SOURCE_DESCRIPTION`. The planner is not authorized to assert that a source exists; it only describes the source supplied by the request. Core must still resolve that source as existing canonical evidence or clarify. This keeps source membership distinct from incidental event context without teaching phrase-specific patterns.

The gate reuses the exact same hash-pinned ten SWR cases plus three READ/delegation/mixed-order sentinels and the pinned evaluator. It permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Provider-free conservative input bound is 52,024 bytes per call and the no-cache ceiling is `$0.1672112`. `MAX_COST_USD` remains `$0.00`; no provider call is authorized.
