# Journal target live gate v12

This focused gate validates the model-facing `note-schema` correction for `journal_entry` targeting.

The production Core planner must treat the semantic journal date as target identity evidence: `today` and `yesterday` must produce `journal_entry` writes whose target is filtered by the resolved `entry_date`, while also recording that required property for creation when no same-date entry exists.

The gate makes exactly two GPT-5.6 Luna low calls, with zero automatic retries and no Sol fallback. It is mutation-free and does not touch the real vault. Provider access requires explicit `ODYSSEY_RUN_PLANNER_JOURNAL_TARGET_V12=1`, a clean worktree, the exact pinned candidate prompt/schema hashes, and a fresh human authorization.

The conservative regional byte-as-token ceiling is below $0.030. Real persistence behavior is covered separately by a provider-free vertical regression proving that a wrong-date journal candidate is excluded and left byte-for-byte unchanged.
