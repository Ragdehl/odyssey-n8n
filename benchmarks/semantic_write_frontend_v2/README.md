# Semantic WRITE frontend v2

This is the unexecuted successor to the consumed semantic-write-frontend-v1 Luna/low gate. It
reuses the same hash-pinned ten active SWR cases and the same three generic READ, delegation, and
mixed-order sentinels; no held-out case or oracle was changed after the v1 failure.

The only model-facing correction is one generic teaching example showing that several safely
selectable participants in one explicit-source relationship remain identity parts inside one
source-targeted operation. The existing prompt prose, semantic WRITE schema/compiler, downstream
Core interfaces, and Sol fallback contract are unchanged.

The gate permits at most 13 Luna/low calls, zero automatic retries, and zero Sol calls. Its
provider-free conservative input bound is 50,157 bytes per call and its no-cache ceiling is
`$0.162357`. `MAX_COST_USD` is `$0.00`; the fresh non-overwriting artifact path is
`benchmarks/.live-results/semantic-write-frontend-v2-luna-gate.jsonl`. Any execution requires fresh
explicit human authorization after offline review.
