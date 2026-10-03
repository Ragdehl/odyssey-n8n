# Sol Journal fallback live gate v14

This one-shot focused gate exists because the canonical Journal schema description changed the production Sol fallback prompt as well as the Luna-first prompt. The global v2 regression gate accepted the new GPT-5.6 Luna low contract 16/16; v14 checks only the affected Sol fallback behavior rather than rerunning unrelated Sol coverage.

The single case requires `journal_entry` with exact `entry_date` target filtering and the same required property for create-safe behavior. The gate uses GPT-5.6 Sol low, zero retries, one provider call, no vault mutation, and refuses execution without explicit `ODYSSEY_RUN_PLANNER_SOL_JOURNAL_V14=1`. Conservative Standard authority is below $0.021.
