# Semantic WRITE frontend v6

This gate is permanently consumed. The user authorized the 13-case Luna/low gate at its `$0.166712`
conservative ceiling. It ran once at authorization commit `90f796e` and stopped fail-fast on SWR04
after four completed Luna/low calls, with zero retries and zero Sol calls. SWR01-SWR03 passed.

SWR04 (`Mi hijo mayor fue al cine con la amiga que vive en Lyon.`) incorrectly made authenticated
self the write owner and lowered both the child and friend as fact identities. The request instead
asserts a fact about the child; first-person possession only supplies identity evidence. The frozen
ownership oracle is retained.

The immutable artifact is `benchmarks/.live-results/semantic-write-frontend-v6-luna-gate.jsonl`,
SHA-256 `0a4b2524bda2605bcbcc6e4f7662090c0089e4c2cc264089ab83c3ecb9b0ab2e`. Usage-backed cost from the
checked-in pricing snapshot is `$0.00380722`. The v6 runner is permanently consumed at `$0.00`.
