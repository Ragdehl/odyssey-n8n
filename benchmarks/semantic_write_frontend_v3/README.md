# Semantic WRITE frontend v3

This is the unexecuted successor to the consumed v2 gate. It reuses the exact same hash-pinned ten
active SWR cases plus the same three READ/delegation/mixed-order sentinels and unchanged oracles.

The only model-facing correction removes a contradictory teaching signal: the complete-set example
now explicitly names an existing Atlas project note before using `EXISTING_DESCRIPTION`. The prompt
rule itself is unchanged: descriptive or event context without a safely bounded canonical source stays
in the target description/query and must not be promoted into an invented existing source.

The gate permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Its provider-free
conservative input bound is 50,278 bytes per call and its no-cache ceiling is `$0.1626716`.
`MAX_COST_USD` is `$0.00`; execution requires fresh explicit human authorization.
