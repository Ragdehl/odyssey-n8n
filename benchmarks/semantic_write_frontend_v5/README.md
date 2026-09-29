# Semantic WRITE frontend v5

This is the unexecuted successor to the consumed v4 gate. It reuses the exact same hash-pinned ten
active SWR cases plus the same three READ/delegation/mixed-order sentinels and unchanged oracles.

The only model-facing correction strengthens one existing generic teaching example: its separately
described fact participant now explicitly comes from an existing workshop roster and therefore carries
its own `EXISTING_DESCRIPTION` candidate scope. This demonstrates that a relationship-bounded target
and a separately relationship-bounded fact identity remain independent. No prompt rule, schema,
compiler, Core interface, or relationship taxonomy changes.

The gate permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Its provider-free
conservative input bound is 51,744 bytes per call and its no-cache ceiling is `$0.1664832`.
`MAX_COST_USD` is `$0.00`; execution requires fresh explicit human authorization.
