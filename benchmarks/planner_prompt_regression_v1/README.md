# Planner prompt regression v1

This is the reusable small-matrix pattern for future planner model-facing changes. It reuses the 13 frozen Semantic WRITE frontend cases and adds three clarification-entry sentinels: an unspecified member of a SELF relationship, the same request after a related conversation turn, and the same semantics over `project` Notes rather than people.

The gate is prepared with **zero provider authority**. A future execution requires a fresh explicit bounded-cost authorization, a separate authorization commit, GPT-6 Luna first, followed by the currently deployed planner model while it remains different, complete-matrix collection, and permanent retirement after the first provider call. GPT-6 is comparative evidence unless a separate reviewed model switch is approved; the deployed planner configuration remains the merge authority for a prompt change.
