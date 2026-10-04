# Tasks v0 live gate

Authorized one-shot gate for the first Tasks vertical. Scope: 14 provider calls maximum, no retries, no mutations, and no Sol fallback.

The live run consumed exactly 14 calls at an estimated regional cost of $0.00799348. Router passed 6/6, Tasks interpretation passed 4/4, and Temporal passed 2/2. Both shared-planner calls returned locally validated Task plans; the original result artifact records them as failures only because the gate oracle attempted to inspect the nonexistent `KnowledgeUnit.property_changes` attribute after `planner.plan()` had already returned successfully. The runner is corrected to inspect `KnowledgeUnit.properties`; no provider calls were repeated.
