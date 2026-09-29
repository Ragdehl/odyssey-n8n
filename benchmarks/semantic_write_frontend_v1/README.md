# Semantic WRITE frontend v1

This is the unexecuted Luna/low live-gate lineage for the first semantic WRITE frontend checkpoint.
It reuses the ten active SWR cases by SHA-256 instead of copying or modifying their registry, then
adds three generic sentinels for unchanged READ, unchanged delegation, and exact mixed-action order.

The future gate has 13 logical cases and at most 13 Luna calls, with zero automatic retries and no
Sol fallback path. Its conservative provider-free ceiling is `$0.1594554` using a 49,041-byte input
bound. `MAX_COST_USD` remains `$0.00`, the non-overwriting artifact path is
`benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl`, and no provider call has been
made. Execution requires a fresh explicit authorization after deterministic and semantic review.
