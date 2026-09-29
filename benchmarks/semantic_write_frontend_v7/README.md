# Semantic WRITE frontend v7

This is the unexecuted successor to the consumed v6 gate. It reuses the exact same hash-pinned ten
active SWR cases plus the same three READ/delegation/mixed-order sentinels and the evaluator hash
pinned by v6.

The v6 run regressed on SWR04 by writing a child-owned fact onto self. The v7 correction does not add
a prompt rule or another example. It clarifies the ownership lessons of the two existing generic
examples: self owns a relationship fact only when the request actually asserts participation with
self, while first-person possession may bound another target without transferring fact ownership.
The existing bounded-participant lesson is preserved.

The gate permits at most 13 Luna/low calls, zero retries, and zero Sol calls. Its provider-free
conservative input bound is 51,796 bytes per call and its no-cache ceiling is `$0.1666184`.
`MAX_COST_USD` is `$0.00`; execution requires fresh explicit human authorization.
