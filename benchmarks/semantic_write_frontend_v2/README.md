# Semantic WRITE frontend v2

This is the consumed successor to semantic-write-frontend-v1. It reused the same hash-pinned ten
active SWR cases and the same three generic READ, delegation, and mixed-order sentinels; no held-out
case or oracle changed after the v1 failure.

The user authorized the 13-case gate at its `$0.162357` conservative ceiling. It ran once at
authorization commit `8caa17c` and stopped fail-fast on SWR03 after three completed Luna/low calls,
with zero retries and zero Sol calls. SWR01 and SWR02 passed. The immutable local artifact is
`benchmarks/.live-results/semantic-write-frontend-v2-luna-gate.jsonl`, SHA-256
`5b2cbe8fa4b1cdc6936968d9f54d9f1a377d3badcdaeeba388f97df5e1147edd`. The checked-in pricing
snapshot gives a usage-backed estimate of `$0.00308352`.

SWR03 preserved the full descriptive target and fact, but invented an existing source described as
`la cena de ayer`. The frozen oracle is correct: the request gives event context but does not establish
an existing canonical dinner source. The semantic prompt already says not to invent a source. The
contradiction came from a teaching example that itself modeled an implicit dinner event as an existing
source. The successor correction removes that contradiction rather than adding another prompt rule.

The v2 runner is permanently retired at `$0.00`; successor evidence must use a new versioned runner
and non-overwriting artifact path.
