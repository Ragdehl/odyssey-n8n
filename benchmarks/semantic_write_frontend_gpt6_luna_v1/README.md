# GPT-6 Luna semantic WRITE comparison v1

This is a model-only comparison against the consumed semantic-write-frontend-v8 evidence. The prompt, provider schema, teaching examples, frozen 10 SWR cases, 3 generic sentinels, evaluator, reasoning effort (`low`), max output tokens, zero-retry policy, and complete 13-case diagnostic matrix are unchanged. The only provider variable is `gpt-5.6-luna` -> `gpt-6-luna`.

GPT-6 Luna pricing is pinned from the official OpenAI model page on 2026-09-29: $0.10/M input, $0.01/M cached input, $0.125/M cache writes, and $0.50/M output for Standard short-context processing. With the unchanged 52,024-byte conservative input bound and 2,048 max output tokens, the 13-call no-cache ceiling is `$0.0809432`.

The user explicitly authorized up to `$0.0809432` for this comparison. No retries, Sol calls, Odyssey writes, deployment, merge, or vault mutation are authorized.
