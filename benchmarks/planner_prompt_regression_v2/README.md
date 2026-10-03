# Planner prompt regression v2

This fresh final-pre-merge gate evaluates the complete frozen 16-case production planner regression matrix after the schema-driven Journal target-date contract changed the rendered Luna prompt. It preserves the v1 cases/oracles and reviewed safe-degradation policy; the focused Journal v13 gate separately proves the new same-day update/create behavior.

The gate is GPT-5.6 Luna low only, zero automatic retries, no Sol fallback, one call per case, and refuses execution without explicit `ODYSSEY_RUN_PLANNER_PROMPT_REGRESSION_V2=1`. The exact candidate prompt/provider-schema/teaching hashes and matrix hash are pinned. The conservative authorized ceiling is $0.215 for at most 16 provider calls.

No accepted-contract hashes may be updated from this candidate until the retained v2 evidence is reviewed and acceptable.
