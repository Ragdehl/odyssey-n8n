# Router bounded parallel interpretation — DEV phase (2026-10)

## Architecture challenge: PROCEED with a bounded first slice

Observed example: `Hoy tengo que ir al cine y mañana ire al teatro` was correctly split into
Tasks and Temporal routes. Real request telemetry showed 8.38 s Router and 15.28 s
subsequent sequential route work (25.71 s browser total). Parsing and preparing
independent route interpretations do not need access to canonical Markdown mutation.
Today `execute_routed_request()` executes complete routes sequentially. A naive thread
pool around that loop would run concurrent Core/Git writes and violate canonical
ordering/idempotence; it is prohibited.

**Approved aim:** Parallelize independent, model-only preparation while leaving one
serialized Core write authority. Do not redesign Router, Tasks, Temporal or Core.
**Slice 1:** Up to two concurrent application interpretation jobs for separately
validated Router spans. Each job receives its own exact span and immutable prior-turn
context. It may call the existing Tasks/Temporal interpreters, never Core execution,
repository/index reads, persistent state, Git, or pending-work writes. Results are
consumed in route order by the existing executors and aggregated under one delivery ID.
If an interpretation crosses midnight before its serial execution, discard it
and reinterpret at execution time with the new clock. No stale date interpretation
may reach Core. The feature is disabled by default and explicitly enabled only
in the isolated DEV service with `ODYSSEY_PARALLEL_ROUTE_PREPARATION=1`.
Every route still passes the same Core validator/mutation boundary. A route whose
preparation fails remains a bounded failed route; unrelated routes proceed as before.
Synchronous single-route and unsupported-route execution is unchanged. Tasks
interpretation can overlap Temporal interpretation in another route; a Tasks
route that itself needs Temporal calls Temporal in its serial executor, for now. Keep one request
lock and the existing route-local IDs, pending-work and Git semantics.

**Acceptance:** deterministic barrier test proves two interpretation jobs overlap and
commit callbacks remain ordered; failures are isolated; route/correlation validation,
fixed prior context, replay/clarification and disabled destinations are unchanged;
real Core/Calendar fixture persists two independent Day facts correctly; all existing
tests pass. A measured DEV replay of the actual user example determines real speedup
versus the same configuration sequentially. Do not advertise estimated speedup as measured.

**Out of scope for slice 1:** parallel Core planners/preflight/writers, concurrent writes,
provider prompt changes, complex route DAGs, new services, independent deliveries,
multiple concurrent clarifications, global HTTP/request concurrency changes.

**Later Core-related slice (separate decision):** Only after slice 1 is stable, define a
pure shared Core planning artifact and serial apply/revalidation contract. This would
allow concurrent Core planner API calls but requires new temporal/time snapshot rules,
provider telemetry, read-after-write semantics, index freshness and stale target guards.
It must not be simulated by concurrent execution of the current complete Core call.

**Rollback:** remove the optional preparation injection; existing synchronous routing
path remains authoritative. Keep the change on `dev` only until the DEV behavior is
verified. Never touch real vault files or production to benchmark.
