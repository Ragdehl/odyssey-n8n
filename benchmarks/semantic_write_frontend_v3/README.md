# Semantic WRITE frontend v3

This is the consumed successor to the v2 gate. It reused the exact same hash-pinned ten active SWR
cases plus the same three READ/delegation/mixed-order sentinels and unchanged oracles.

The user authorized the 13-case Luna/low gate at its `$0.1626716` conservative ceiling. It ran once
and stopped fail-fast on SWR04 after four completed Luna/low calls, with zero retries and zero Sol
calls. SWR01, SWR02, and SWR03 passed. SWR04 (`Mi hijo mayor fue al cine con la amiga que vive en
Lyon.`) returned `ESCALATE` even though the semantic frontend can represent one relationship-bounded
target plus one independently described fact participant. The unchanged oracle is therefore retained.

The immutable artifact is `benchmarks/.live-results/semantic-write-frontend-v3-luna-gate.jsonl`,
SHA-256 `ff1c88f2cb29613009f943f73cba61cbcb2a00b613acca75207070771d93f8fc`. Usage-backed cost from the
checked-in pricing snapshot is `$0.00360986`. The v3 runner is permanently consumed at `$0.00`; a
successor must use a new versioned runner and artifact path.
