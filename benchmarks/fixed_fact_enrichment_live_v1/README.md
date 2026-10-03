# Fixed-fact semantic enrichment live gate v1

This is the first focused live gate for the Core-owned, fixed-destination semantic enrichment used
by managed captures such as Calendar Day content. It exercises only the parts-only enrichment
contract. The model cannot choose a destination, note type destination, mutation, stable ID, path,
Markdown, or CREATE behavior.

The three cases check that a nickname-like person mention is exposed to Core identity resolution,
that a complete SELF relationship such as `mis hijos` preserves its complete-set candidate scope,
and that both survive together in canonically dated Day content. Exact source partition validation,
existing-only resolution, ambiguous/stale fallback, missing-role literal fallback, all-or-nothing set
grounding, persistence, and replay are covered provider-free rather than by this live gate.

The gate is one-shot, GPT-5.6 Luna low, zero-retry, and has no vault mutation authority.

- Maximum provider calls: `3`.
- Conservative ceiling: `$0.009069`; hard authorization cap: `$0.012`.
