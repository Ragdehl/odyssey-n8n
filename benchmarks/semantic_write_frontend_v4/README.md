# Semantic WRITE frontend v4

This is the unexecuted successor to the consumed v3 Luna/low gate. It reuses the exact same
hash-pinned ten active SWR cases plus the same three READ/delegation/mixed-order sentinels and
unchanged oracles.

The only model-facing correction is one generic non-held-out teaching example for a
relationship-bounded target plus a separately described participant inside the new fact. The prompt
prose, semantic WRITE schema/compiler, Core interfaces, Sol fallback contract, and frozen gate cases
remain unchanged.

The gate permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Its provider-free
conservative input bound is 51,455 bytes per call and its no-cache ceiling is `$0.1657318`.
`MAX_COST_USD` is `$0.00`; the fresh non-overwriting artifact path is
`benchmarks/.live-results/semantic-write-frontend-v4-luna-gate.jsonl`. Execution requires fresh
explicit human authorization.
