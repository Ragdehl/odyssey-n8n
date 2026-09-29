# Semantic WRITE frontend v1

This is the consumed Luna/low live-gate lineage for the first semantic WRITE frontend checkpoint.
It reused the ten active SWR cases by SHA-256 instead of copying or modifying their registry, then
added three generic sentinels for unchanged READ, unchanged delegation, and exact mixed-action order.

The user authorized the 13-case gate at its `$0.1594554` conservative ceiling. It ran once at
authorization commit `6985314` and stopped fail-fast on SWR01 after exactly one completed Luna/low
call, with zero retries and zero Sol calls. The immutable one-row artifact is
`benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl`, SHA-256
`4431ba7ca547aa3c82070d20f4c391b2113cb4ce8b9754d88e0ddefb1018ebfa`. Usage was 9,073 input,
125 output, and 0 reasoning tokens; the checked-in pricing snapshot yields a usage-backed no-cache
estimate of `$0.0019646`.

The compiled result correctly selected authenticated self but kept both named participants inside
one literal fact, producing no identity parts, semantic references, or lookup-only units. The frozen
oracle is correct: safely selectable Odyssey identities mentioned by a fact must remain identity
parts so Core can resolve and link them. The v1 runner is permanently retired at `$0.00`; successor
evidence uses a new versioned runner and non-overwriting artifact path.
