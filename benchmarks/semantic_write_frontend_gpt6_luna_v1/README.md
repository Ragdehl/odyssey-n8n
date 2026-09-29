# GPT-6 Luna semantic WRITE comparison v1

This consumed model-only comparison reused the exact semantic-write-frontend-v8 prompt, provider schema, teaching examples, frozen 10 SWR cases, 3 generic sentinels, evaluator, `low` reasoning effort, 2,048 max output tokens, zero-retry policy, and complete 13-case matrix. The only provider variable was `gpt-5.6-luna` -> `gpt-6-luna`.

The user authorized up to `$0.0809432`. The run completed all 13 GPT-6 Luna calls with zero retries and zero Sol calls. **11/13 passed**. GPT-6 Luna fixed the v8 baseline's SWR07 candidate-scope miss, but regressed SWR08 and SWR10 by preserving the full participant descriptions while dropping their event-source candidate bounds. READ, delegate, mixed-order, ownership, escalation, and the remaining WRITE cases passed.

Artifact SHA-256: `896e73337a9a1ffbf2984b8db18c214d7dea03e8f705ad181b6950554a941628`. Usage-backed Standard short-context estimate: **`$0.00419596`**. GPT-5.6 Luna's directly comparable v8 matrix passed **12/13** at `$0.00912232`, so the current planner recommendation remains GPT-5.6 Luna: GPT-6 Luna is about 54% cheaper on this run but less accurate on the frozen regression matrix. No prompt tuning is justified from this comparison.

The gate is permanently consumed at `MAX_COST_USD=$0.00`. No deployment, merge, Odyssey write, or vault mutation occurred.
