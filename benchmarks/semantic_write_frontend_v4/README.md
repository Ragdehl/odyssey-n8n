# Semantic WRITE frontend v4

This is the consumed successor to the v3 gate. It reused the exact same hash-pinned ten active SWR
cases plus the same three READ/delegation/mixed-order sentinels and unchanged oracles.

The user authorized the 13-case Luna/low gate at its `$0.1657318` conservative ceiling. It ran once
and stopped fail-fast on SWR08 after eight completed Luna/low calls, with zero retries and zero Sol
calls. SWR01 through SWR07 passed. SWR08 preserved the relationship-bounded daughter target and the
full described companion, but left that companion globally described instead of preserving the
request's explicit existing dinner source as the companion identity's bounded candidate scope. The
unchanged oracle is retained.

The immutable artifact is `benchmarks/.live-results/semantic-write-frontend-v4-luna-gate.jsonl`,
SHA-256 `1963296cbcc857c0f07703b0b045ee411b3aabed826a4d689bf822ed9b975652`. Usage-backed cost from the
checked-in pricing snapshot is `$0.00631928`. The v4 runner is permanently consumed at `$0.00`; a
successor must use a new versioned runner and artifact path.
